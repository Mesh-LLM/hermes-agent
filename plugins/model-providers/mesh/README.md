# Mesh Private Compute

This provider embeds the Mesh-LLM Python SDK in Hermes. Agent prompts, streamed
text, reasoning, tool-call deltas, tool results, multimodal content, usage, and
provider extensions travel through the encrypted Mesh transport without a
loopback HTTP sidecar.

Install a client-only `mesh-llm` Python wheel from
[Mesh-LLM/mesh-llm PR #2071](https://github.com/Mesh-LLM/mesh-llm/pull/2071),
then configure the private-mesh invitation:

```bash
hermes auth add mesh
hermes model
```

Choose **Mesh Private Compute** and one of the live models advertised by the
mesh. Hermes generates one Mesh owner identity per Hermes profile and stores it
with owner-only permissions under that profile's `mesh/` state directory.

The admitted Mesh workers are inside the inference trust boundary. Hermes tools
such as web search, browsers, and external MCP servers retain their own data
policies and are not made private by selecting this provider.
