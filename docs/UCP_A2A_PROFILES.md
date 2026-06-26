# UCP And A2A Profiles

`STD-003` adds a checked mapping profile for UCP-style checkout sessions and
A2A-style agent handoffs.

This is not a native UCP transport implementation and not an A2A JSON-RPC
server. The profile intentionally uses the compliance claim
`mapping_profiles_not_native_ucp_or_a2a`.

## Why This Exists

AgentCart already has the commerce pieces that external agent protocols need:

- verified merchant discovery;
- final quote with tax, shipping, stock, delivery, `quote_hash`, and expiry;
- explicit human approval;
- payment handoff bound to quote and approval;
- WooCommerce order, refund, delivery, aftercare, and audit state.

The profile makes that mapping explicit so future UCP or A2A adapters can be
thin translators around the AgentCart commerce core instead of separate
checkout implementations.

## Published Document

The AgentCart service serves the checked profile at:

```text
/.well-known/agentcart-standards.json
/v1/standards/profiles
```

These are AgentCart-specific discovery documents. They are deliberately not
`/.well-known/ucp` or `/.well-known/agent.json`, because those would imply
native protocol behavior that is not implemented yet.

## UCP Mapping

The UCP-style profile maps:

- discovery to `/v1/registry`, `/v1/catalog/search`, and
  `/v1/quote-tournament`;
- checkout-session quote creation to `/v1/quotes`;
- buyer authorization to `/v1/approvals` and
  `/v1/approvals/{approval_id}/decision`;
- payment and order submission to `/v1/checkout`;
- fulfillment, refund, and aftercare to order, refund, and audit endpoints.

Required invariants stay the same as native AgentCart:

- preserve `quote_hash`;
- preserve merchant of record;
- treat merchant-controlled text as untrusted;
- require human approval before checkout;
- require a verifier for real settlement/refund claims.

## A2A Mapping

The A2A-style profile maps capability and task handoff concepts to existing
AgentCart surfaces:

- capability discovery through `/.well-known/agentcart.json` and
  `/.well-known/agentcart-standards.json`;
- service use through `/v1/mcp/tools` and normal HTTP endpoints;
- skill-only use through the packaged ShopBridge direct skill;
- task stages for quote, approval, payment handoff, aftercare, refund, and
  audit.

Native A2A support should wait until AgentCart implements an Agent Card,
JSON-RPC task lifecycle, auth story, and streaming/update semantics cleanly.

## Checked Gate

The profile is tracked in `gateway/config/ucp_a2a_profiles.json` and validated
by:

```bash
python3 scripts/check-ucp-a2a-profiles.py --verify-test-refs
```

`scripts/verify.sh` runs this gate next to the AP2 mandate mapping gate.

## References

- UCP homepage: https://ucp.dev/
- UCP core concepts: https://ucp.dev/documentation/core-concepts/
- Google UCP native checkout guide:
  https://developers.google.com/merchant/ucp/guides/checkout/native
- A2A project: https://github.com/a2aproject/A2A
- Google A2A purchasing concierge codelab:
  https://codelabs.developers.google.com/intro-a2a-purchasing-concierge
