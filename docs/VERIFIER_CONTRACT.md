# Payment Verifier Contract

ShopBridge has two payment verification modes:

- `external_verifier`: production shape. ShopBridge calls an external verifier
  before creating a paid WooCommerce order or recording a rail-verified refund.
- `trusted_agentcart_token`: local/private mode. A trusted AgentCart gateway
  creates the WooCommerce order after its own approval and MPP-shaped checkout.
  This is not production settlement.

For production order creation, ShopBridge should also be configured with
checkout mode `external_verifier_only`. That keeps the merchant token available
for private gateway/admin operations without allowing token-authenticated demo
checkout to mark a WooCommerce order paid.

The verifier is intentionally a separate module because the checks are
rail-specific. Tempo stablecoin, Stripe/card MPP, Lightning, bank, or custom
rails should not change the catalog, quote, approval, order, delivery, and audit
flow.

## Payment Verification Request

ShopBridge sends:

```json
{
  "operation": "payment",
  "quote": {},
  "quote_hash": "sha256...",
  "payment_contract": {},
  "payment_contract_hash": "sha256...",
  "payment_receipt": {},
  "agentcart_order_id": "order_...",
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "merchant_id": "woocommerce-demo-shop",
    "rail": "tempo-mpp",
    "payment_contract_hash": "sha256...",
    "tempo_network": "testnet",
    "tempo_recipient": "0x...",
    "stripe_profile_id": "acct_...",
    "x402_network": "eip155:84532",
    "x402_asset": "0x...",
    "x402_pay_to": "0x...",
    "x402_max_amount_required": "14800000"
  }
}
```

The canonical Stripe/card MPP fixture is checked in at
`docs/fixtures/verifier/payment-request.stripe-card-mpp.json`.
The canonical Tempo MPP fixture is checked in at
`docs/fixtures/verifier/payment-request.tempo-mpp.json`.

The verifier must reject the payment unless it can prove:

- the payment credential or receipt is valid for the selected rail;
- the payment is bound to the exact `quote_hash`;
- the `payment_contract_hash` matches every supplied copy in the quote,
  receipt, request, and verifier response;
- amount and currency match the quote, or an explicit quote-bound FX conversion
  record exists;
- selected rail matches the receipt and merchant setup;
- Tempo recipient and network match the merchant configuration for Tempo rails;
- Stripe profile matches the merchant configuration for Stripe/card rails;
- x402 network, token asset, payTo address, and atomic amount match the
  quote-bound `PAYMENT-REQUIRED` document for x402-compatible rails;
- the transaction reference has not been used before;
- the payment was not expired, revoked, or already refunded.

Expected success response:

```json
{
  "ok": true,
  "quote_hash": "sha256...",
  "payment_contract_hash": "sha256...",
  "amount_cents": 1480,
  "currency": "EUR",
  "rail": "tempo-mpp",
  "network": "testnet",
  "recipient": "0x...",
  "payer_address": "0x...",
  "payer_source": "did:pkh:eip155:...",
  "asset": "0x...",
  "pay_to": "0x...",
  "max_amount_required": "14800000",
  "transaction_reference": "0x...",
  "replay_reference": "0x...",
  "replay_request_hash": "sha256...",
  "real_settlement_verified": true
}
```

The canonical Stripe/card MPP success fixture is checked in at
`docs/fixtures/verifier/payment-success.stripe-card-mpp.json`.
The canonical Tempo MPP success fixture is checked in at
`docs/fixtures/verifier/payment-success.tempo-mpp.json`.

ShopBridge rejects mismatched quote hash, payment contract hash, amount,
currency, rail, rail-specific merchant recipient/profile fields, or missing
transaction reference. Exact verifier retries may return
`idempotent_replay: true` with the same transaction reference. Reused payment
references with different amount, currency, quote hash, payment contract hash,
rail, or destination/profile fail closed with `replay_conflict: true`.

## Refund Verification Request

ShopBridge sends:

```json
{
  "operation": "refund",
  "merchant": {},
  "order": {
    "id": "123",
    "agentcart_order_id": "order_...",
    "quote_hash": "sha256...",
    "transaction_reference": "0x...",
    "payment_verification": {}
  },
  "refund": {
    "amount_cents": 1480,
    "currency": "EUR",
    "reason": "Customer requested refund",
    "rail": "stripe-card-mpp",
    "requested_reference": "refund-order-123-1",
    "recipient": "0x...",
    "asset": "pathUSD"
  },
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "quote_hash": "sha256...",
    "original_transaction_reference": "0x...",
    "refund_recipient": "0x...",
    "asset": "pathUSD"
  }
}
```

The canonical Stripe/card MPP refund request fixture is checked in at
`docs/fixtures/verifier/refund-request.stripe-card-mpp.json`.
The canonical Tempo MPP refund request fixture is checked in at
`docs/fixtures/verifier/refund-request.tempo-mpp.json`.

The verifier must execute or verify the refund through the original rail and
return:

```json
{
  "ok": true,
  "amount_cents": 1480,
  "currency": "EUR",
  "quote_hash": "sha256...",
  "original_transaction_reference": "0x...",
  "rail": "stripe-card-mpp",
  "refund_reference": "re_...",
  "replay_reference": "re_...",
  "replay_request_hash": "sha256...",
  "real_refund_verified": true
}
```

The canonical Stripe/card MPP refund success fixture is checked in at
`docs/fixtures/verifier/refund-success.stripe-card-mpp.json`.
The canonical Tempo MPP refund success fixture is checked in at
`docs/fixtures/verifier/refund-success.tempo-mpp.json`.

Tempo refund fixtures are deliberately USD/pathUSD denominated. A Tempo refund
success response must bind the refund transfer to the original transaction
reference, merchant recipient, source/refund recipient, network, asset, quote
hash, and replay reference before `real_refund_verified=true` is accepted. Do
not claim EUR settlement or EUR refunds from a pathUSD proof unless a separate
quote-bound FX verifier fixture is added.

Negative contract fixtures are checked in at `docs/fixtures/verifier/negative/`.
They cover amount mismatch, quote-hash mismatch, payment-contract mismatch,
Stripe profile mismatch, payment reference replay, payment replay conflict,
refund original-reference mismatch, missing refund requested reference, and
refund reference replay.

ShopBridge requires a refund idempotency key before calling the verifier. It
rejects refund amounts above the remaining refundable amount, exact idempotent
replays return the existing WooCommerce refund, and conflicting replays fail
closed. ShopBridge also rejects mismatched `quote_hash`, original transaction
reference, rail, amount, currency, missing refund reference, or a reused refund
reference already recorded on the same order. A configured external verifier
must return `real_refund_verified=true`; otherwise ShopBridge does not create a
WooCommerce refund record for that verifier response. AgentCart also validates
provider reference, verifier mode/state, amount, currency, and rail before it
marks its own refund record as `real_refund_verified`. Production verifier
implementations should also reject reused refund references globally for the
payment rail/account.

## Current Demo Scope

The repo implements the commerce flow, the verifier contract, a Stripe/card MPP
sandbox verifier for Link CLI testing, and a guarded Tempo refund adapter. A
production verifier still belongs to the selected payment rail or payment
provider deployment because it must carry provider credentials, refund
authority, replay protection, and operational monitoring.

Tempo, x402, or other CLI proof helpers are value-proof artifacts only. Even on
a successful mainnet command, AgentCart does not set `real_settlement` from CLI
success alone. Latest `mppx` checked on 2026-07-01 is `0.8.1`; the repo had
`0.7.0` pinned before this research. The newer package adds hardening and
x402/EVM surface work, but still does not expose a one-time Tempo refund API for
completed WooCommerce orders. Session-channel `refundedToPayer` receipts cover
unused session deposits, not refunding a completed one-time shop order. Real
settlement and refund claims require the external verifier response to bind
amount, currency or FX policy, merchant recipient/profile, quote hash, payment
contract hash, and a non-replayed transaction or refund reference.

For Tempo charge-flow settlement, configure the verifier with
`AGENTCART_TEMPO_SETTLEMENT_MODE=verify` and the matching token/asset settings.
The verifier must wait for the Tempo transaction receipt and require an ERC-20
`Transfer` from the proof payer to the merchant recipient for the exact quote
amount before returning `real_settlement_verified=true`. With settlement mode
disabled, the verifier may accept a demo proof for staging, but it must return
`real_settlement_verified=false` and must not make a refund eligible for live
rail execution.

For Tempo charge-flow refunds, configure the verifier with
`AGENTCART_TEMPO_REFUND_MODE=live`,
`AGENTCART_TEMPO_REFUND_PRIVATE_KEY`, and the matching token/asset settings.
The refund private key must resolve to the original payment recipient, and the
refund recipient must match the original payer address. With refund mode
disabled or a wallet mismatch, the verifier fails closed and ShopBridge does not
record a rail-verified refund.

The current EUR stablecoin decision fixture is
`docs/fixtures/verifier/euro-stablecoin-rail-plan.json`. It pins the first
Tempo staging shop as USD/pathUSD and treats EURC or Monerium EURe as x402/EVM
rail candidates that need facilitator support plus the same verifier/refund
contract before WooCommerce can mark settlement or refunds real.

Validate the checked-in fixtures and the WooCommerce plugin payload field names:

```sh
python3 scripts/verify-verifier-fixtures.py
```

The Stripe sandbox verifier supports lock-protected file-backed replay
protection with `AGENTCART_VERIFIER_REPLAY_STORE_PATH` or
`STRIPE_MPP_REPLAY_STORE_PATH`. If no path is configured, it keeps an in-memory
replay store for the running process. Set
`AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true` for production-shaped verifier
runs; `/health` then fails closed unless a replay store path is configured.
`AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS` controls the local lock timeout.
Optionally set `AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH` or
`STRIPE_MPP_REPLAY_JOURNAL_PATH` to append sanitized
`agentcart.verifierReplayJournal.v1` events for accepted claims, exact
idempotent retries, and replay conflicts. Set
`AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL=true` when support/audit operations
must fail closed unless that journal is writable.
`/health` exposes replay-store kind, whether durable replay is required and
configured, lock mode, writeability, bucket counts, replay-store read/write
errors, replay-journal writeability, entry count, and journal errors. Each
accepted replay entry stores a `request_hash` over the replay bucket, provider
reference, and quote/payment/refund fields. Exact repeats are marked as
idempotent; changed repeats are rejected as replay conflicts. The journal hashes
the rail reference instead of writing raw payment or refund references.
Provider failures are classified in JSON with `provider_error_class`,
`provider_status`, `provider_code`, `request_id`, and `retryable` fields.
The sandbox verifier also exposes `/metrics` with process-local operation,
rail, status, rejection, provider-error, latency, replay, settlement, and refund
counters plus replay-journal appended/failed counters, and emits structured
`agentcart.verifierEvent.v1` request logs with a correlation id.
When `AGENTCART_VERIFIER_ALERT_WEBHOOK_URL` is configured, rejected or failed
verifier requests also emit `agentcart.verifier_alert_notification.v1` webhook
events with severity, code, operation, rail, status, quote hash, payment
contract hash, retryability, and correlation id. Repeated alert fingerprints are
throttled by `AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS`.

For production, use a durable store with transactional uniqueness constraints
for payment transaction references, refund requested references, and refund
references. The checked-in lockfile store plus append-only journal is suitable
for sandbox, local self-hosted testing, and support diagnostics; it is not a
managed payment-provider ledger.
