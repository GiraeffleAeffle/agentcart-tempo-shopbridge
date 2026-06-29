# External Beta Pilot Checklist

Status: P0 pilot-readiness gate for testing AgentCart with external merchants
and buyer agents.

The machine-readable source of this checklist is
`gateway/config/pilot_beta_checklist.json`. Validate it with:

```sh
python3 scripts/check-pilot-readiness.py
```

That command validates the checklist schema only. It is useful for development,
but it does not certify that an external beta is ready.

To gate a real pilot evidence folder, store evidence as
`<gate-id>/<evidence-id>.md` and run:

```sh
python3 scripts/check-pilot-readiness.py \
  --evidence-dir pilot-evidence/example-shop \
  --require-evidence
```

For an external beta/release decision, use the stricter gate. It requires pilot
evidence, buyer-agent runtime evidence, and a production-shaped payment profile:

```sh
python3 scripts/check-beta-release-readiness.py \
  --pilot-evidence-dir pilot-evidence/example-shop \
  --buyer-agent-evidence-dir pilot-evidence/buyer-agents \
  --payment-env-file deploy/home-server/.env
```

`./scripts/verify.sh` runs the schema checks by default. Set
`AGENTCART_BETA_RELEASE_GATE=1` plus `AGENTCART_PILOT_EVIDENCE_DIR`,
`AGENTCART_BUYER_AGENT_EVIDENCE_DIR`, and `AGENTCART_PAYMENT_ENV_FILE` only
when you want `verify.sh` to run the evidence-required external beta gate.

For removing a pilot merchant, revoking discovery, or rolling back a bad
plugin/gateway release, use `docs/MERCHANT_ROLLBACK_RUNBOOK.md`.

## Pilot Scope

Minimum scope before calling a beta useful:

- 2 external or staging merchants.
- 3 buyer-agent runtimes: AgentCart service, direct skill, and one generic
  MCP-style client.
- 10 successful approved checkouts.
- 14 calendar days of observation.

Allowed payment modes:

- sandbox verifier;
- trusted testnet flow;
- external verifier with real refunds disabled and clearly labeled.

Blocked payment modes:

- unaudited real settlement;
- refund claims without verifier evidence;
- public checkout that relies only on a merchant token.

## P0 Gates

### pilot-merchant-onboarding

Each beta merchant can install ShopBridge, publish discovery, expose only the
intended products, and pass sandbox quote/checkout checks.

Required evidence:

- plugin ZIP install screenshot or log;
- AgentCart settings readiness snapshot;
- catalog preview export;
- sandbox quote check result;
- sandbox checkout test result;
- live WooCommerce smoke result;
- WooCommerce compatibility matrix result;
- registry record or bundle URL.

Exit criteria:

- merchant id is stable;
- support email, terms, and returns URLs are public;
- AgentCart exposure mode is documented;
- tax and shipping rules match a manual WooCommerce checkout;
- sandbox checkout order is cancelled and stock hold is released.

### pilot-buyer-agent-setup

At least three buyer-agent paths can discover merchants, compare final quotes,
produce approval records, and create or hand off checkout payloads.

Required evidence:

- buyer-agent test matrix result;
- service-backed agent run log;
- skill-only agent run log;
- generic MCP client run log;
- approval record hash;
- audit packet or export.

Exit criteria:

- buyer-agent test matrix passes;
- agent does not scrape non-opt-in shops;
- approval is required before checkout;
- quote hash and payment contract hash are preserved;
- buyer aftercare message uses structured order state.

### pilot-payment-mode

The pilot payment mode is explicit, amount-bound, and honest about whether real
settlement or refunds are executed.

Required evidence:

- payment mode decision record;
- verifier health or fixture result;
- production payment profile check result;
- refund policy statement;
- sample payment contract hash.

Exit criteria:

- public checkout uses an external verifier or signed gateway;
- demo/testnet payments are labeled as not real settlement;
- real refund claims require verifier evidence;
- idempotency and replay checks are enabled.

### pilot-support-channel

Merchants and test buyers know where to report failures, how fast responses are
expected, and what diagnostic artifacts to share.

Required evidence:

- support contact;
- response SLA;
- diagnostic collection steps;
- incident owner.

Exit criteria:

- support channel is monitored;
- merchant can revoke the registry record;
- operator can find audit export;
- operator can disable public checkout.

### pilot-rollback

The team can remove a beta merchant or roll back a bad plugin/gateway release
without losing order audit evidence.

Required evidence:

- previous plugin ZIP;
- release manifest;
- rollback command or `docs/MERCHANT_ROLLBACK_RUNBOOK.md` incident evidence;
- registry revocation URL.

Exit criteria:

- plugin can be deactivated without deleting orders;
- registry record can be revoked;
- AgentCart gateway release can be rolled back;
- pilot test products can be disabled.

### pilot-safety-privacy

Pilot data handling is clear: no private demand on-chain, no raw payment
credentials in logs, and merchant text is treated as untrusted data.

Required evidence:

- privacy notice;
- ops event redaction sample;
- rate-limit smoke result;
- prompt-injection corpus result;
- prompt-injection review notes.

Exit criteria:

- registry contains public merchant metadata only;
- ops notifications exclude payment credentials and delivery addresses;
- merchant product text is not executed as an agent instruction;
- rate-limit abuse smoke passes against staging.

## Success Metrics

- Checkout success rate: at least 80%.
- Merchant setup time target: 30 minutes or less.
- Quote-to-checkout median: 180 seconds or less.
- Unresolved P0 incidents: 0.
- Refund claims without verifier evidence: 0.

## Exit Decision

Exit beta only after:

- minimum pilot scope is met;
- all P0 gates have evidence;
- success metrics meet thresholds;
- no blocking security or payment incidents remain unresolved;
- at least one merchant can complete setup from docs without help from the repo
  author.
