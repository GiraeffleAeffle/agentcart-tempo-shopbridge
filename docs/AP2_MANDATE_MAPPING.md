# AP2-Style Mandate Mapping

AgentCart now emits an AP2-style field mapping from its existing approval and
payment handoff records. This is an adapter contract, not a claim that
AgentCart currently issues signed AP2 VDCs or participates in an AP2 network.

The goal is portability: the same human approval can be carried by the
AgentCart service, the direct buyer skill, or a future AP2 client without
changing the WooCommerce plugin core.

## What Is Implemented

`approval_record.ap2_style_mandate_mapping` contains:

- `checkout_mandate`: quote-bound merchant, items, subtotal, shipping, total,
  delivery, quote id, quote hash, and expiry.
- `payment_mandate`: approval-bound payment amount, currency, destination,
  rail, payment contract hash, quote hash, and expiry.
- `audit_bindings`: approval hash, quote hash, and payment contract hash.
- `safety`: explicit flags that human approval is required, merchant text is
  untrusted, and real settlement still needs an external verifier.
- `mapping_hash`: a deterministic hash of the mapping payload.

The direct buyer skill also includes
`payment_request.ap2_style_payment_mandate` in the payment handoff command, so
a wallet-capable or payment-capable agent can receive the payment mandate
without parsing the whole approval packet.

## Current Boundary

The mapping status is `unsigned_adapter_mapping`. That is deliberate.

AgentCart is binding the right commerce facts today:

- merchant of record;
- exact quote hash;
- total amount and currency;
- payment destination and payment contract hash;
- approval hash;
- expiry and delivery context.

Production AP2 support would add the AP2 runtime-specific envelope,
credential/signature format, conformance tests, and verifier/client fixtures.
Until that exists, docs and machine-readable config must keep the compliance
claim at `ap2_style_field_mapping_not_signed_ap2_vdc`.

## Checked Gate

The gate is tracked in `gateway/config/ap2_mandate_mapping.json` and validated
by:

```bash
python3 scripts/check-ap2-mandate-mapping.py --verify-test-refs
```

The checked runtime tests cover:

- AgentCart service approval records;
- direct buyer-skill approval packets;
- direct buyer-skill payment handoff requests.

This keeps `STD-002` useful now while leaving room for a proper signed AP2
adapter later.
