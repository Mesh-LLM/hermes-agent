"""End-to-end provider-contract tests for embedded Mesh private compute."""

from __future__ import annotations

import asyncio
import stat
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest


class _Inference:
    def __init__(self) -> None:
        self.cancelled = asyncio.Event()
        self.blocked = threading.Event()

    async def list_models(self):
        return [SimpleNamespace(id="private-model", name="Private Model")]

    async def chat_completions(self, body):
        assert body["tools"][0]["function"]["name"] == "weather"
        return {
            "id": "chatcmpl-mesh",
            "created": 1,
            "model": body["model"],
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "private chain",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "weather", "arguments": '{"city":"Sydney"}'},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        }

    async def stream_chat_completions(self, body):
        try:
            yield SimpleNamespace(data=None)
            payload = {
                "id": "chatcmpl-mesh",
                "created": 1,
                "model": body["model"],
                "object": "chat.completion.chunk",
                "provider": "mesh-worker",
                "choices": [{
                    "index": 0,
                    "finish_reason": None,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "weather", "arguments": '{"city":"Syd'},
                        }],
                    },
                }],
            }
            yield SimpleNamespace(data="chunk", json=lambda: payload)
            self.blocked.set()
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


class _NativeClient:
    latest = None

    def __init__(self) -> None:
        self.inference = _Inference()
        _NativeClient.latest = self

    @classmethod
    def create(cls, **kwargs):
        assert kwargs["owner_keypair_hex"] == "ab" * 32
        assert kwargs["invite_token"] == "private-invite"
        return cls()

    async def start(self):
        return None

    async def stop(self):
        return None


@pytest.fixture
def mesh_profile(monkeypatch):
    fake = ModuleType("meshllm")
    fake.Client = _NativeClient
    fake.generate_owner_keypair_hex = lambda: "ab" * 32
    monkeypatch.setitem(sys.modules, "meshllm", fake)

    import model_tools  # noqa: F401
    import providers

    profile = providers.get_provider_profile("mesh")
    assert profile is not None
    provider_client = profile.create_client(api_key="private-invite")
    mesh_client = sys.modules[provider_client.__class__.__module__]

    mesh_client._shutdown_all_runtimes()
    yield profile, mesh_client
    mesh_client._shutdown_all_runtimes()


def test_mesh_profile_preserves_tools_for_sync_and_async_hermes(mesh_profile):
    from agent.transports.chat_completions import ChatCompletionsTransport

    profile, _ = mesh_profile
    client = profile.create_client(api_key="private-invite")
    request = {
        "model": "private-model",
        "messages": [{"role": "user", "content": "Weather?"}],
        "tools": [{"type": "function", "function": {"name": "weather", "parameters": {}}}],
    }

    sync_response = client.chat.completions.create(**request)
    assert sync_response.choices[0].message.tool_calls[0].function.name == "weather"
    normalized = ChatCompletionsTransport().normalize_response(sync_response)
    assert normalized.tool_calls[0].name == "weather"
    assert normalized.tool_calls[0].arguments == '{"city":"Sydney"}'
    assert normalized.provider_data["reasoning_content"] == "private chain"

    async def invoke():
        return await client.chat.completions.create(**request)

    async_response = asyncio.run(invoke())
    assert async_response.usage.total_tokens == 7


def test_mesh_stream_cancels_native_read_and_identity_is_profile_scoped(mesh_profile):
    profile, mesh_client = mesh_profile
    assert profile.fetch_models(api_key="private-invite", timeout=2) == ["private-model"]
    client = profile.create_client(api_key="private-invite")
    stream = client.chat.completions.create(
        model="private-model",
        messages=[{"role": "user", "content": "Weather?"}],
        tools=[{"type": "function", "function": {"name": "weather", "parameters": {}}}],
        stream=True,
    )

    chunk = next(stream)
    assert chunk.choices[0].delta.tool_calls[0].function.arguments == '{"city":"Syd'
    assert chunk.provider == "mesh-worker"
    blocked_errors = []

    def wait_for_next_chunk():
        try:
            next(stream)
        except BaseException as exc:
            blocked_errors.append(exc)

    blocked_next = threading.Thread(target=wait_for_next_chunk, daemon=True)
    blocked_next.start()
    assert _NativeClient.latest.inference.blocked.wait(timeout=2)
    client.cancel()
    blocked_next.join(timeout=2)
    assert not blocked_next.is_alive()
    assert blocked_errors
    assert mesh_client._runtime_for("private-invite").submit(
        _NativeClient.latest.inference.cancelled.wait()
    ).result(timeout=2) is True

    identity = mesh_client._identity_path(mesh_client._hermes_home())
    assert identity.read_text(encoding="ascii").strip() == "ab" * 32
    assert stat.S_IMODE(identity.stat().st_mode) == 0o600
