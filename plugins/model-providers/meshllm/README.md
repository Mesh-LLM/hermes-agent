# Mesh LLM

This provider embeds the Mesh LLM Python SDK in Hermes. Agent prompts, streamed
text, reasoning, tool-call deltas, tool results, multimodal content, usage, and
provider extensions travel through the encrypted Mesh LLM transport without a
loopback HTTP sidecar.

Install a client-only `mesh-llm` Python wheel from
[Mesh-LLM/mesh-llm PR #2071](https://github.com/Mesh-LLM/mesh-llm/pull/2071),
then choose a public network or supply a private Mesh LLM invitation:

```bash
hermes auth add meshllm
hermes model
```

Choose **Mesh LLM**, then either **Public network** for automatic discovery or
**Private network** to enter an invite token. Pick one of the live models
advertised by the connected network. Hermes generates one Mesh LLM owner identity per
Hermes profile and stores it with owner-only permissions under that profile's
`meshllm/` state directory.

In Desktop, **Settings → Providers → Mesh LLM** shows the client connection,
connected peer count, and advertised models. Start, Stop, and Restart control
the client for the selected Hermes profile. Stop keeps the saved connection but
prevents model discovery and inference until Start or Restart is selected.

Hermes requires at least 64,000 served context tokens. The Mesh LLM SDK carries the
actual served `context_length` into Hermes for its existing startup guard. A
legacy server that omits this metadata receives the conservative 8,192-token Mesh LLM
fallback and is rejected rather than silently treated as a large-context route.

The connected workers are inside the inference trust boundary. A public Mesh LLM
network is community-operated; a private network is controlled by its operator.
Hermes tools such as web search, browsers, and external MCP servers retain
their own data policies and are not made private by selecting this provider.
