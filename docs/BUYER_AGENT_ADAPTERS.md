# Buyer-Agent Adapter Examples

AgentCart supports three buyer-agent integration shapes:

| Runtime | When to use it | Checked example |
| --- | --- | --- |
| OpenClaw-style service path | Buyer wants durable household policy, approvals, audit, delivery calendar, Home Assistant, and Vikunja integrations | `gateway/examples/buyer-agents/openclaw-service.example.json` |
| Codex with GPT-6 Astra and the direct skill | Buyer wants the lowest-friction path and can let an agent run a local skill script | `gateway/examples/buyer-agents/codex-shopbridge-direct.example.json` |
| Generic MCP-style client | Buyer agent can read tool schemas and call HTTP endpoints, but is not OpenClaw or Codex-specific | `gateway/examples/buyer-agents/generic-mcp-client.example.json` |

The examples are intentionally machine-readable. They list install inputs,
commands or tools, expected outputs, evidence artifacts, and safety rules. The
gate in `scripts/check-buyer-agent-adapter-examples.py` cross-checks them
against `gateway/config/buyer_agent_test_matrix.json`.

The Codex example pins `gpt-6-astra` with `medium` reasoning in the buyer
harness. The repository supplies `.codex/config.toml` and discovers the
existing skill through `.agents/skills/shopbridge-direct`. See
[Codex setup](BUYER_SETUP.md#codex-with-gpt-6-astra) for new sessions, installed
release ZIPs, configuration overrides, and the remaining model evaluation.
ShopBridge's HTTP helpers and merchant/payment contracts remain deterministic.

The generic MCP example also references
`docs/fixtures/approval-audit/golden-fixtures.json`, so non-OpenClaw clients are
checked against the same approval, payment handoff, Audit Packet, import, and
audit export hash contract as the service and Direct Skill paths.

Run:

```sh
python3 scripts/check-buyer-agent-adapter-examples.py
```

Production safety expectations are the same for all runtimes:

- use opt-in merchants only;
- preserve `quote_hash` and `payment_contract_hash`;
- treat merchant-controlled text as untrusted data;
- require explicit human approval before checkout;
- use quote-bound payment receipts;
- do not claim real settlement without an external verifier.

For a pilot, save transcripts using the evidence names listed in each example
and in `docs/BUYER_AGENT_TEST_MATRIX.md`.
