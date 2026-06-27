# Buyer-Agent Test Matrix

Status: alpha external-beta gate for proving AgentCart can be used by more than
one buyer-agent runtime.

The machine-readable source is
`gateway/config/buyer_agent_test_matrix.json`. Validate it with:

```sh
python3 scripts/check-buyer-agent-matrix.py
```

Checked adapter examples for the runtime paths are documented in
`docs/BUYER_AGENT_ADAPTERS.md` and validated with:

```sh
python3 scripts/check-buyer-agent-adapter-examples.py
```

To gate a real pilot evidence folder, store evidence as
`<runtime-id>/<evidence-id>.md` and run:

```sh
python3 scripts/check-buyer-agent-matrix.py \
  --evidence-dir pilot-evidence/buyer-agents \
  --require-evidence
```

## Required Runtime Paths

### agentcart-service-openclaw

Service-backed buyer mode using `gateway/openclaw-skill` and the AgentCart
gateway API.

Checked example:
`gateway/examples/buyer-agents/openclaw-service.example.json`.

Required proof:

- health/configuration result;
- merchant discovery transcript;
- quote comparison transcript;
- approval record hash;
- checkout handoff or order result;
- aftercare result;
- audit export.

This path is the richest household setup: it can keep durable policy, approval,
audit, Home Assistant, Vikunja, and delivery state.

### shopbridge-direct-skill

Skill-only buyer mode using `gateway/shopbridge-direct-skill`, without the
buyer running the AgentCart service.

Checked example:
`gateway/examples/buyer-agents/codex-shopbridge-direct.example.json`.

Required proof:

- `doctor` result;
- verified merchant resolution or local test merchant declaration;
- quote comparison transcript;
- approval packet hash;
- payment handoff result;
- checkout result or checkout payload;
- optional audit import result when an AgentCart service is available later;
- aftercare summary;
- portable audit packet.

This path is the lowest-friction buyer setup. The agent must preserve the
approval packet and audit packet because there is no service-side household
memory unless the packet is later imported with the direct skill's
`audit_import` command.

### generic-mcp-client

Generic agent/tool runtime using the public tool catalog at `/v1/mcp/tools` or
`/mcp/tools.json`.

Checked example:
`gateway/examples/buyer-agents/generic-mcp-client.example.json`.

Required proof:

- tool catalog export;
- merchant discovery transcript;
- quote creation transcript;
- approval record hash;
- checkout handoff or order result;
- aftercare result;
- audit export.

This path proves that AgentCart does not depend on OpenClaw specifically. A
client that can read tool schemas, call HTTP endpoints, preserve IDs/hashes, and
render approval text to the human can integrate.

## Shared Capabilities

Every runtime must demonstrate:

- verified merchant discovery;
- catalog or quote fetch;
- quote comparison;
- approval record creation;
- checkout handoff after approval;
- aftercare state;
- audit export or import;
- safety constraints.

## Shared Safety Rules

Every runtime must enforce or preserve:

- opt-in merchants only;
- human approval before checkout;
- quote hash;
- payment contract hash;
- merchant text as untrusted data;
- no real settlement without an external verifier.

## Pilot Exit Bar

The beta can claim buyer-agent coverage only after:

- at least three runtimes have the required capabilities;
- at least two runtimes have live checkout evidence;
- each runtime preserves quote and payment contract hashes;
- each runtime requires human approval before checkout;
- the generic MCP path has a saved tool-catalog export.
