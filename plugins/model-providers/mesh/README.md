# Mesh

This provider embeds the Mesh-LLM Python SDK in Hermes. Agent prompts, streamed
text, reasoning, tool-call deltas, tool results, multimodal content, usage, and
provider extensions travel through the encrypted Mesh transport without a
loopback HTTP sidecar.

Install a client-only `mesh-llm` Python wheel from
[Mesh-LLM/mesh-llm PR #2071](https://github.com/Mesh-LLM/mesh-llm/pull/2071),
then choose the public Mesh or supply a private-Mesh invitation:

```bash
hermes auth add mesh
hermes model
```

Choose **Mesh**, then either **Public Mesh** for automatic discovery or
**Private Mesh** to enter an invite token. Pick one of the live models
advertised by the connected Mesh. Hermes generates one Mesh owner identity per
Hermes profile and stores it with owner-only permissions under that profile's
`mesh/` state directory.

Hermes requires at least 64,000 served context tokens. The Mesh SDK carries the
actual served `context_length` into Hermes for its existing startup guard. A
legacy Mesh that omits this metadata receives the conservative 8,192-token Mesh
fallback and is rejected rather than silently treated as a large-context route.

The connected Mesh workers are inside the inference trust boundary. A public
Mesh is community-operated; a private Mesh is controlled by its operator.
Hermes tools such as web search, browsers, and external MCP servers retain
their own data policies and are not made private by selecting this provider.
