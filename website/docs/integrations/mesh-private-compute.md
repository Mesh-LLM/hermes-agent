---
title: "Mesh Private Compute"
sidebar_label: "Mesh Private Compute"
sidebar_position: 2
description: "Run Hermes inference privately across trusted Mesh-LLM nodes"
---

# Mesh Private Compute

The Mesh-LLM Hermes fork includes a first-class **Mesh Private Compute** model
provider. Hermes keeps its normal agent loop, tools, memory, CLI, gateway, and
Desktop surfaces while inference runs through an embedded Mesh client:

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

Then add the private-mesh invitation and choose a live model:

```bash
hermes auth add mesh
hermes model
```

Select **Mesh Private Compute**. The model picker queries the connected mesh,
so it follows model additions and removals without a static Hermes catalog.

Hermes generates one Mesh owner identity per Hermes profile and stores it at
`$HERMES_HOME/mesh/owner-keypair.hex` with owner-only permissions. The invite
token stays in Hermes' normal secret store as `MESH_INVITE_TOKEN`; neither
secret is placed in process arguments or logs.

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

Mesh makes model inference private to the machines admitted to that mesh. The
operators of those machines are inside the compute trust boundary.

Selecting Mesh does not change the privacy policy of Hermes tools. Web search,
browsers, external MCP servers, messaging platforms, and other integrations may
still send the data supplied to them to their respective services.
