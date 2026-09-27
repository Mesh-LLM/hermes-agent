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
        return [
            SimpleNamespace(
                id="private-model",
                name="Private Model",
                context_length=131_072,
            )
        ]

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
    public_connections = 0

    def __init__(self) -> None:
        self.inference = _Inference()
        _NativeClient.latest = self

    @classmethod
    def create(cls, **kwargs):
        assert kwargs["owner_keypair_hex"] == "ab" * 32
        assert kwargs["invite_token"] == "private-invite"
        return cls()

    @classmethod
    async def connect_public(cls, **kwargs):
        assert kwargs["owner_keypair_hex"] == "ab" * 32
        cls.public_connections += 1
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
    assert profile.description.startswith("Mesh (")
    provider_client = profile.create_client(api_key="private-invite")
    mesh_client = sys.modules[provider_client.__class__.__module__]
    mesh_plugin = sys.modules[profile.__class__.__module__]

    mesh_client._shutdown_all_runtimes()
    _NativeClient.public_connections = 0
    yield profile, mesh_client, mesh_plugin
    mesh_client._shutdown_all_runtimes()


def test_mesh_profile_preserves_tools_for_sync_and_async_hermes(mesh_profile):
    from agent.transports.chat_completions import ChatCompletionsTransport

    profile, _, _ = mesh_profile
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
    profile, mesh_client, _ = mesh_profile
    assert profile.fetch_models(api_key=mesh_client.PUBLIC_MESH, timeout=2) == ["private-model"]
    assert _NativeClient.public_connections == 1
    client = profile.create_client(api_key=mesh_client.PUBLIC_MESH)
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
    assert mesh_client._runtime_for(mesh_client.PUBLIC_MESH).submit(
        _NativeClient.latest.inference.cancelled.wait()
    ).result(timeout=2) is True

    identity = mesh_client._identity_path(mesh_client._hermes_home())
    assert identity.read_text(encoding="ascii").strip() == "ab" * 32
    assert stat.S_IMODE(identity.stat().st_mode) == 0o600


def test_mesh_auth_handler_offers_public_or_private_connections(mesh_profile, monkeypatch):
    from agent.credential_pool import load_pool

    profile, mesh_client, mesh_plugin = mesh_profile
    assert profile.auth_type == "oauth_external"

    monkeypatch.setattr("hermes_cli.cli_output.line_input", lambda prompt: "1")
    assert profile.auth_handler("add", SimpleNamespace(provider="mesh")) is True
    assert load_pool("mesh").select().access_token == mesh_client.PUBLIC_MESH

    profile.auth_handler("logout", SimpleNamespace(provider="mesh"))
    monkeypatch.setattr("hermes_cli.cli_output.line_input", lambda prompt: "2")
    monkeypatch.setattr("hermes_cli.secret_prompt.masked_secret_prompt", lambda prompt: "private-invite")
    assert mesh_plugin._auth_handler("add", SimpleNamespace(provider="mesh")) is True
    assert load_pool("mesh").select().access_token == "private-invite"


def test_mesh_context_length_uses_served_capacity_and_rejects_missing_metadata(
    mesh_profile, monkeypatch,
):
    from agent.credential_pool import AUTH_TYPE_API_KEY, PooledCredential
    from agent.model_metadata import get_model_context_length

    _, mesh_client, _ = mesh_profile
    monkeypatch.setattr(
        "agent.credential_pool.CredentialPool.select",
        lambda self, **kwargs: PooledCredential(
            provider="mesh",
                id="private",
                label="Private Mesh",
                auth_type=AUTH_TYPE_API_KEY,
                priority=0,
                source="test",
                access_token="private-invite",
        ),
    )

    assert get_model_context_length("private-model", provider="mesh") == 131_072
    _NativeClient.latest.inference.list_models = lambda: _missing_context_models()
    assert (
        get_model_context_length("private-model", provider="mesh")
        == mesh_client.UNKNOWN_CONTEXT_LENGTH
    )


async def _missing_context_models():
    return [SimpleNamespace(id="private-model", name="Private Model", context_length=None)]
