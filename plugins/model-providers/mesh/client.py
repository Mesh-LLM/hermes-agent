"""OpenAI-compatible Hermes facade over the asynchronous Mesh Python SDK."""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import contextlib
import hashlib
import os
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypeVar


_T = TypeVar("_T")
_RUNTIMES: dict[str, "_MeshRuntime"] = {}
_RUNTIMES_LOCK = threading.Lock()
PUBLIC_MESH = "mesh://public"
UNKNOWN_CONTEXT_LENGTH = 8_192


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def _identity_path(home: Path) -> Path:
    return home / "mesh" / "owner-keypair.hex"


def _load_or_create_identity(home: Path, generate: Any) -> str:
    path = _identity_path(home)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.parent.chmod(0o700)
    try:
        value = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        value = str(generate()).strip()
        if not value:
            raise RuntimeError("Mesh generated an empty owner identity")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            value = path.read_text(encoding="ascii").strip()
        else:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(value + "\n")
    if not value:
        raise RuntimeError(f"Mesh owner identity is empty: {path}")
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return value


class _LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="hermes-mesh", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, awaitable: Awaitable[_T]) -> concurrent.futures.Future[_T]:
        async def wait() -> _T:
            return await awaitable

        return asyncio.run_coroutine_threadsafe(wait(), self.loop)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Mesh event loop did not stop within 5 seconds")
        self.loop.close()


class _MeshRuntime:
    def __init__(self, connection: str, home: Path, start_timeout: float) -> None:
        try:
            import meshllm
        except ImportError as exc:
            raise RuntimeError(
                "Mesh needs the mesh-llm Python SDK. "
                "Install the wheel built by Mesh-LLM/mesh-llm PR #2071."
            ) from exc

        owner_keypair = _load_or_create_identity(home, meshllm.generate_owner_keypair_hex)
        self._invite_fingerprint = b""
        self._runner = _LoopThread()
        try:
            if connection == PUBLIC_MESH:
                connecting = self._runner.submit(meshllm.Client.connect_public(
                    owner_keypair_hex=owner_keypair,
                ))
                self.client = connecting.result(timeout=start_timeout)
            else:
                self.client = meshllm.Client.create(
                    owner_keypair_hex=owner_keypair,
                    invite_token=connection,
                )
            start = self._runner.submit(self.client.start())
            start.result(timeout=start_timeout)
        except BaseException:
            if "connecting" in locals():
                connecting.cancel()
            if "start" in locals():
                start.cancel()
                with contextlib.suppress(BaseException):
                    start.result(timeout=5)
            self._runner.stop()
            raise

    def submit(self, awaitable: Awaitable[_T]) -> concurrent.futures.Future[_T]:
        return self._runner.submit(awaitable)

    def model_metadata(self, timeout: float) -> list[Any]:
        return self.submit(self.client.inference.list_models()).result(timeout=timeout)

    def models(self, timeout: float) -> list[str]:
        models = self.model_metadata(timeout)
        return [str(model.id) for model in models if str(getattr(model, "id", "")).strip()]

    def model_context_length(self, model_id: str, timeout: float) -> int | None:
        target = model_id.strip()
        for model in self.model_metadata(timeout):
            if str(getattr(model, "id", "")).strip() != target:
                continue
            raw = getattr(model, "context_length", None)
            if type(raw) is int and raw > 0:
                return raw
            # Mesh launchers use the same conservative 8K fallback for legacy
            # servers that omit served-context metadata. This intentionally
            # stays below Hermes' 64K floor so agent startup refuses the route.
            return UNKNOWN_CONTEXT_LENGTH
        return None

    def close(self) -> None:
        stop = self.submit(self.client.stop())
        try:
            stop.result(timeout=5)
        except BaseException:
            stop.cancel()
            with contextlib.suppress(BaseException):
                stop.result(timeout=5)
            raise
        finally:
            self._runner.stop()


def _runtime_for(connection: str, start_timeout: float = 30.0) -> _MeshRuntime:
    token = connection.strip()
    if not token or token == "no-key-required":
        raise RuntimeError("Mesh is not configured. Run `hermes auth add mesh`.")
    home = _hermes_home()
    key = str(home.resolve())
    fingerprint = hashlib.sha256(token.encode("utf-8")).digest()
    with _RUNTIMES_LOCK:
        current = _RUNTIMES.get(key)
        if current is not None and current._invite_fingerprint == fingerprint:
            return current
        if current is not None:
            current.close()
        runtime = _MeshRuntime(token, home, start_timeout)
        runtime._invite_fingerprint = fingerprint
        _RUNTIMES[key] = runtime
        return runtime


def _shutdown_all_runtimes() -> None:
    with _RUNTIMES_LOCK:
        runtimes = tuple(_RUNTIMES.values())
        _RUNTIMES.clear()
    for runtime in runtimes:
        with contextlib.suppress(Exception):
            runtime.close()


atexit.register(_shutdown_all_runtimes)


def discover_models(invite_token: str, timeout: float) -> list[str] | None:
    try:
        return _runtime_for(invite_token, start_timeout=timeout).models(timeout)
    except Exception:
        return None


def discover_model_context_length(
    invite_token: str, model_id: str, timeout: float = 8.0,
) -> int | None:
    try:
        runtime = _runtime_for(invite_token, start_timeout=timeout)
        return runtime.model_context_length(model_id, timeout)
    except Exception:
        return None


def _request_body(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(kwargs)
    extra_body = body.pop("extra_body", None)
    if isinstance(extra_body, Mapping):
        body.update(extra_body)
    for client_only in ("extra_headers", "extra_query", "timeout"):
        body.pop(client_only, None)
    return body


def _chat_completion(payload: Mapping[str, Any]) -> Any:
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(dict(payload))


def _chat_chunk(payload: Mapping[str, Any]) -> Any:
    from openai.types.chat import ChatCompletionChunk

    return ChatCompletionChunk.model_validate(dict(payload))


async def _buffered(runtime: _MeshRuntime, body: dict[str, Any]) -> Any:
    payload = await runtime.client.inference.chat_completions(body)
    return _chat_completion(payload)


async def _streaming(runtime: _MeshRuntime, body: dict[str, Any]) -> AsyncGenerator[Any, None]:
    stream = runtime.client.inference.stream_chat_completions(body)
    close = getattr(stream, "aclose", None)
    try:
        async for event in stream:
            data = getattr(event, "data", None)
            if data is None or data == "[DONE]":
                continue
            parse = getattr(event, "json", None)
            if not callable(parse):
                continue
            payload = parse()
            if isinstance(payload, Mapping):
                yield _chat_chunk(payload)
    finally:
        if callable(close):
            await close()


class _HybridCompletion:
    def __init__(self, future: concurrent.futures.Future[Any]) -> None:
        self._future = future

    def __await__(self):
        return asyncio.wrap_future(self._future).__await__()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._future.result(), name)


class _HybridStream(Iterator[Any], AsyncIterator[Any]):
    response = None

    def __init__(self, runtime: _MeshRuntime, body: dict[str, Any], release: Any) -> None:
        self._runtime = runtime
        self._events = _streaming(runtime, body)
        self._release = release
        self._closed = False
        self._released = False
        self._pending: concurrent.futures.Future[Any] | None = None
        self._pending_lock = threading.Lock()

    def _next_future(self) -> concurrent.futures.Future[Any]:
        with self._pending_lock:
            if self._closed:
                raise StopAsyncIteration
            future = self._runtime.submit(self._events.__anext__())
            self._pending = future
        return future

    def _clear_pending(self, future: concurrent.futures.Future[Any]) -> None:
        with self._pending_lock:
            if self._pending is future:
                self._pending = None

    def __iter__(self) -> "_HybridStream":
        return self

    def __next__(self) -> Any:
        future = self._next_future()
        try:
            return future.result()
        except StopAsyncIteration as exc:
            self._finish()
            raise StopIteration from exc
        finally:
            self._clear_pending(future)

    def __aiter__(self) -> "_HybridStream":
        return self

    async def __anext__(self) -> Any:
        future = self._next_future()
        try:
            return await asyncio.wrap_future(future)
        except StopAsyncIteration:
            self._finish()
            raise
        finally:
            self._clear_pending(future)

    def __await__(self):
        async def ready() -> "_HybridStream":
            return self

        return ready().__await__()

    def close(self) -> None:
        with self._pending_lock:
            if self._closed:
                return
            self._closed = True
            pending = self._pending
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(
                concurrent.futures.CancelledError,
                StopAsyncIteration,
                concurrent.futures.TimeoutError,
            ):
                pending.result(timeout=5)
        try:
            self._runtime.submit(self._events.aclose()).result(timeout=5)
        except RuntimeError as exc:
            if "already running" not in str(exc):
                raise
        finally:
            self._finish()

    async def aclose(self) -> None:
        with self._pending_lock:
            if self._closed:
                return
            self._closed = True
            pending = self._pending
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await asyncio.wrap_future(pending)
        try:
            await asyncio.wrap_future(self._runtime.submit(self._events.aclose()))
        except RuntimeError as exc:
            if "already running" not in str(exc):
                raise
        finally:
            self._finish()

    def _finish(self) -> None:
        with self._pending_lock:
            self._closed = True
            if self._released:
                return
            self._released = True
        self._release(self)


class MeshOpenAIClient:
    """Duck-compatible sync + async OpenAI client backed by one embedded Mesh runtime."""

    HERMES_SKIP_TRANSPORT_WRAP = True
    HERMES_SKIP_ASYNC_WRAP = True

    def __init__(self, invite_token: str) -> None:
        self._invite_token = invite_token
        self._active_streams: set[_HybridStream] = set()
        self._streams_lock = threading.Lock()
        self.api_key = "mesh-private-compute"
        self.base_url = "mesh://embedded"
        self.is_closed = False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        runtime = _runtime_for(self._invite_token)
        body = _request_body(kwargs)
        if body.pop("stream", False):
            stream = _HybridStream(runtime, body, self._release_stream)
            with self._streams_lock:
                self._active_streams.add(stream)
            return stream
        return _HybridCompletion(runtime.submit(_buffered(runtime, body)))

    def _release_stream(self, stream: _HybridStream) -> None:
        with self._streams_lock:
            self._active_streams.discard(stream)

    def cancel(self) -> None:
        with self._streams_lock:
            streams = tuple(self._active_streams)
        for stream in streams:
            stream.close()

    def close(self) -> None:
        self.cancel()
        self.is_closed = True
