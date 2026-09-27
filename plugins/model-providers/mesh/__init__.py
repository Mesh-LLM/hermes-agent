"""Mesh Private Compute provider for the Mesh-LLM Hermes fork."""

from __future__ import annotations

from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

from .client import MeshOpenAIClient, discover_models


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


mesh = MeshProfile(
    name="mesh",
    aliases=("mesh-llm", "meshllm"),
    api_mode="chat_completions",
    display_name="Mesh Private Compute",
    description="Private inference across your trusted Mesh-LLM nodes",
    env_vars=("MESH_INVITE_TOKEN",),
    base_url="",
    auth_type="api_key",
    supports_health_check=False,
    supports_model_listing=True,
    supports_vision=True,
)

register_provider(mesh)
