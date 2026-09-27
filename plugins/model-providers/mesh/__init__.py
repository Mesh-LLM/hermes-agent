"""Public and private Mesh provider for the Mesh-LLM Hermes fork."""

from __future__ import annotations

import uuid
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

from .client import (
    PUBLIC_MESH,
    MeshOpenAIClient,
    discover_model_context_length,
    discover_models,
)


def _auth_handler(action: str, args: Any) -> bool:
    from agent.credential_pool import AUTH_TYPE_API_KEY, PooledCredential, load_pool

    pool = load_pool("mesh")
    if action == "add":
        invite_token = str(getattr(args, "api_key", "") or "").strip()
        label = str(getattr(args, "label", "") or "").strip()
        source = "manual:mesh-private"
        if not invite_token:
            from hermes_cli.cli_output import line_input
            from hermes_cli.secret_prompt import masked_secret_prompt

            print("\nConnect Hermes to:")
            print("  1. Public Mesh (discover a published community Mesh automatically)")
            print("  2. Private Mesh (connect using an invite token)")
            choice = line_input("Choice [1/2]: ").strip()
            if choice == "1":
                invite_token = PUBLIC_MESH
                label = label or "Public Mesh"
                source = "manual:mesh-public"
            elif choice == "2":
                invite_token = masked_secret_prompt("Private Mesh invite token: ").strip()
                label = label or "Private Mesh"
            else:
                raise SystemExit("No Mesh connection selected.")
        if not invite_token:
            raise SystemExit("No Mesh invite token provided.")
        if invite_token == PUBLIC_MESH:
            label = label or "Public Mesh"
            source = "manual:mesh-public"
        entry = pool.add_entry(PooledCredential(
            provider="mesh",
            id=uuid.uuid4().hex[:6],
            label=label or "Private Mesh",
            auth_type=AUTH_TYPE_API_KEY,
            priority=0,
            source=source,
            access_token=invite_token,
        ))
        print(f'Configured Mesh connection "{entry.label}".')
        return True
    if action == "status":
        entries = pool.entries()
        public = sum(entry.access_token == PUBLIC_MESH for entry in entries)
        private = len(entries) - public
        print(f"mesh: configured ({public} public, {private} private connection(s))")
        return True
    if action == "logout":
        count = len(pool.entries())
        for index in range(count, 0, -1):
            pool.remove_index(index)
        print(f"Removed {count} Mesh connection(s).")
        return True
    return False


class MeshProfile(ProviderProfile):
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

        entry = load_pool("mesh").select(model=model)
        connection = entry.runtime_api_key if entry else ""
        if not connection:
            return None
        return discover_model_context_length(connection, model)


mesh = MeshProfile(
    name="mesh",
    aliases=("mesh-llm", "meshllm"),
    api_mode="chat_completions",
    display_name="Mesh",
    description="Mesh (public community inference or your own private Mesh)",
    env_vars=(),
    base_url="",
    auth_type="oauth_external",
    auth_handler=_auth_handler,
    supports_health_check=False,
    supports_model_listing=True,
    supports_vision=True,
)

register_provider(mesh)
