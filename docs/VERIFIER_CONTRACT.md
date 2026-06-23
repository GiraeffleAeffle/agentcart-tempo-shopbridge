# Payment Verifier Contract

The hackathon demo has two payment modes:

- `trusted_agentcart_token`: demo mode. A trusted AgentCart gateway creates the
  WooCommerce order after its own approval and MPP-shaped checkout. This is not
  production settlement.
- `external_verifier`: production shape. ShopBridge calls an external verifier
  before creating a paid WooCommerce order or recording a rail-verified refund.

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
  "payment_receipt": {},
  "agentcart_order_id": "order_...",
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "merchant_id": "woocommerce-demo-shop",
    "rail": "tempo-mpp",
    "tempo_network": "testnet",
    "tempo_recipient": "0x...",
    "stripe_profile_id": "acct_..."
  }
}
```

The canonical Stripe/card MPP fixture is checked in at
`docs/fixtures/verifier/payment-request.stripe-card-mpp.json`.

The verifier must reject the payment unless it can prove:

- the payment credential or receipt is valid for the selected rail;
- the payment is bound to the exact `quote_hash`;
- amount and currency match the quote, or an explicit quote-bound FX conversion
  record exists;
- selected rail matches the receipt and merchant setup;
- Tempo recipient and network match the merchant configuration for Tempo rails;
- Stripe profile matches the merchant configuration for Stripe/card rails;
- the transaction reference has not been used before;
- the payment was not expired, revoked, or already refunded.

Expected success response:

```json
{
  "ok": true,
  "quote_hash": "sha256...",
  "amount_cents": 1480,
  "currency": "EUR",
  "rail": "tempo-mpp",
  "network": "testnet",
  "recipient": "0x...",
  "transaction_reference": "0x...",
  "real_settlement_verified": true
}
```

The canonical Stripe/card MPP success fixture is checked in at
`docs/fixtures/verifier/payment-success.stripe-card-mpp.json`.

ShopBridge rejects mismatched quote hash, amount, currency, rail, rail-specific
merchant recipient/profile fields, or missing transaction reference. It also
rejects reused payment transaction references.

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
    "requested_reference": "refund-order-123-1"
  },
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "quote_hash": "sha256...",
    "original_transaction_reference": "0x..."
  }
}
```

The canonical Stripe/card MPP refund request fixture is checked in at
`docs/fixtures/verifier/refund-request.stripe-card-mpp.json`.

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
  "real_refund_verified": true
}
```

The canonical Stripe/card MPP refund success fixture is checked in at
`docs/fixtures/verifier/refund-success.stripe-card-mpp.json`.

Negative contract fixtures are checked in at `docs/fixtures/verifier/negative/`.
They cover amount mismatch, quote-hash mismatch, Stripe profile mismatch,
payment reference replay, refund original-reference mismatch, missing refund
requested reference, and refund reference replay.

ShopBridge requires a refund idempotency key before calling the verifier. It
rejects refund amounts above the remaining refundable amount, exact idempotent
replays return the existing WooCommerce refund, and conflicting replays fail
closed. ShopBridge also rejects mismatched `quote_hash`, original transaction
reference, rail, amount, currency, missing refund reference, or a reused refund
reference already recorded on the same order. Production verifier
implementations should also reject reused refund references globally for the
payment rail/account.

## Current Demo Scope

The repo implements the commerce flow, the verifier contract, and a Stripe/card
MPP sandbox verifier for Link CLI testing. A production verifier still belongs
to the selected payment rail or payment provider deployment because it must
carry provider credentials, refund authority, replay protection, and operational
monitoring.

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
`/health` exposes replay-store kind, whether durable replay is required and
configured, lock mode, bucket counts, and replay-store read errors. Provider
failures are classified in JSON with `provider_error_class`, `provider_status`,
`provider_code`, `request_id`, and `retryable` fields.

For production, use a durable store with transactional uniqueness constraints
for payment transaction references, refund requested references, and refund
references. The checked-in lockfile store is suitable for sandbox and local
self-hosted testing; it is not a managed payment-provider ledger.
