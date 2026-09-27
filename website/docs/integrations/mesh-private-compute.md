---
title: "Mesh"
sidebar_label: "Mesh"
sidebar_position: 2
description: "Use the public Mesh or run inference across your own Mesh-LLM nodes"
---

# Mesh

The Mesh-LLM Hermes fork includes a first-class **Mesh** model provider. Hermes
can discover a published public Mesh automatically or connect directly to your
own Mesh with an invite token. In either mode Hermes keeps its normal agent
loop, tools, memory, CLI, gateway, and Desktop surfaces while inference runs
through an embedded Mesh client:

```text
Hermes agent loop
  → Mesh provider
  → mesh-llm Python SDK (in process)
  → encrypted Mesh transport
  → trusted local or remote inference nodes
```

There is no loopback OpenAI server or sidecar process. The provider maps
Hermes' OpenAI-shaped requests directly onto the Mesh SDK and preserves text,
reasoning, tool definitions and results, incremental tool-call arguments,
multimodal content, usage, and provider extension fields.

## Set up

Install a client-only `mesh-llm` Python wheel from
[Mesh-LLM/mesh-llm PR #2071](https://github.com/Mesh-LLM/mesh-llm/pull/2071).
Client-only wheels are sufficient for Hermes; the machine does not need a GPU
unless it will also contribute inference capacity.

Then start model setup:

```bash
hermes model
```

Select **Mesh**, then choose one of the two connection paths:

1. **Public Mesh** — Hermes discovers and connects to the best published
   community Mesh. No invite token is required.
2. **Private Mesh** — paste the invite token for your own Mesh.

You can also change or add a Mesh connection later with
`hermes auth add mesh`. The model picker queries the connected Mesh, so it
follows model additions and removals without a static Hermes catalog.

## Context requirement

Hermes requires a served context window of at least **64,000 tokens** for its
system prompt, tool schemas, working history, and reliable multi-step tool use.
Mesh reports each model's actual served `metadata.context_length`; Hermes uses
that value for token budgeting and refuses a model below 64,000 at startup.

This is the served window, not the model architecture's theoretical maximum.
If a legacy Mesh omits the metadata, Hermes applies Mesh's conservative 8,192-
token compatibility fallback, which deliberately fails the 64,000-token guard
instead of assuming the route is safe. Upgrade the Mesh server or configure its
served model with at least 64,000 tokens.

Hermes generates one Mesh owner identity per Hermes profile and stores it at
`$HERMES_HOME/mesh/owner-keypair.hex` with owner-only permissions. A private
Mesh invite token stays in Hermes' credential store; neither value is placed
in process arguments or logs.

## Agent behavior

The provider supports the same buffered and streaming Chat Completions contract
used by Hermes' other OpenAI-compatible providers. It works across the primary
agent loop and auxiliary tasks such as compression and title generation. One
embedded Mesh runtime is shared by the clients created inside a Hermes profile.

Closing or interrupting a Hermes stream cancels the native Mesh request,
including while the transport is blocked waiting for the next event. Mesh
connection and model-discovery failures remain provider failures, so Hermes'
normal retry and fallback policy can handle them.

## Privacy boundary

With your own Mesh, model inference is private to the machines admitted to it;
the operators of those machines are inside the compute trust boundary. A
public Mesh is community-operated, so its operators are inside that boundary.

Selecting Mesh does not change the privacy policy of Hermes tools. Web search,
browsers, external MCP servers, messaging platforms, and other integrations may
still send the data supplied to them to their respective services.
