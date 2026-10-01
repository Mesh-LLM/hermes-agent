"""Public and private Mesh LLM provider for the Mesh LLM Hermes fork."""

from __future__ import annotations

import uuid
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

from .client import (
    PUBLIC_MESH,
    MeshOpenAIClient,
    control_runtime,
    discover_model_context_length,
    discover_models,
    runtime_status,
)


def _auth_handler(action: str, args: Any) -> bool:
    from agent.credential_pool import AUTH_TYPE_API_KEY, PooledCredential, load_pool

    pool = load_pool("meshllm")
    if action == "add":
        invite_token = str(getattr(args, "api_key", "") or "").strip()
        label = str(getattr(args, "label", "") or "").strip()
        source = "manual:meshllm-private"
        if not invite_token:
            from hermes_cli.cli_output import line_input
            from hermes_cli.secret_prompt import masked_secret_prompt

            print("\nConnect Hermes to:")
            print("  1. Public Mesh LLM (discover a published community network automatically)")
            print("  2. Private Mesh LLM (connect using an invite token)")
            choice = line_input("Choice [1/2]: ").strip()
            if choice == "1":
                invite_token = PUBLIC_MESH
                label = label or "Public Mesh LLM"
                source = "manual:meshllm-public"
            elif choice == "2":
                invite_token = masked_secret_prompt("Private Mesh LLM invite token: ").strip()
                label = label or "Private Mesh LLM"
            else:
                raise SystemExit("No Mesh LLM connection selected.")
        if not invite_token:
            raise SystemExit("No Mesh LLM invite token provided.")
        if invite_token == PUBLIC_MESH:
            label = label or "Public Mesh LLM"
            source = "manual:meshllm-public"
        entry = pool.add_entry(PooledCredential(
            provider="meshllm",
            id=uuid.uuid4().hex[:6],
            label=label or "Private Mesh LLM",
            auth_type=AUTH_TYPE_API_KEY,
            priority=0,
            source=source,
            access_token=invite_token,
        ))
        print(f'Configured Mesh LLM connection "{entry.label}".')
        return True
    if action == "status":
        entries = pool.entries()
        public = sum(entry.access_token == PUBLIC_MESH for entry in entries)
        private = len(entries) - public
        print(f"meshllm: configured ({public} public, {private} private connection(s))")
        return True
    if action == "logout":
        count = len(pool.entries())
        for index in range(count, 0, -1):
            pool.remove_index(index)
        print(f"Removed {count} Mesh LLM connection(s).")
        return True
    return False


class MeshProfile(ProviderProfile):
    def desktop_status(self) -> dict[str, Any]:
        from agent.credential_pool import load_pool

        entry = load_pool("meshllm").select()
        return runtime_status(entry.runtime_api_key if entry else "")

    def desktop_control(self, action: str) -> dict[str, Any]:
        from agent.credential_pool import load_pool

        entry = load_pool("meshllm").select()
        connection = entry.runtime_api_key if entry else ""
        try:
            return control_runtime(connection, action)
        except Exception as exc:
            raise RuntimeError(str(exc).replace(connection, "[redacted]") if connection else str(exc)) from exc

    def create_client(self, **client_kwargs: Any) -> MeshOpenAIClient:
        return MeshOpenAIClient(str(client_kwargs.get("api_key") or ""))

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        del base_url
        return discover_models(api_key or "", timeout)

    def get_model_context_length(self, model: str) -> int | None:
        from agent.credential_pool import load_pool

        entry = load_pool("meshllm").select(model=model)
        connection = entry.runtime_api_key if entry else ""
        if not connection:
            return None
        return discover_model_context_length(connection, model)


meshllm = MeshProfile(
    name="meshllm",
    aliases=(),
    api_mode="chat_completions",
    display_name="Mesh LLM",
    description="Mesh LLM (public community inference or your own private network)",
    env_vars=(),
    base_url="",
    auth_type="oauth_external",
    auth_handler=_auth_handler,
    desktop_auth={"kind": "public_or_token", "public_value": PUBLIC_MESH},
    supports_health_check=False,
    supports_model_listing=True,
    supports_vision=True,
)

register_provider(meshllm)
