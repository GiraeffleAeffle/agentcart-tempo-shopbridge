# Payment Verifier Contract

The hackathon demo has two payment modes:

- `trusted_agentcart_token`: demo mode. A trusted AgentCart gateway creates the
  WooCommerce order after its own approval and MPP-shaped checkout. This is not
  production settlement.
- `external_verifier`: production shape. ShopBridge calls an external verifier
  before creating a paid WooCommerce order or recording a rail-verified refund.

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
    "rail": "stripe-card-mpp"
  },
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "quote_hash": "sha256...",
    "original_transaction_reference": "0x..."
  }
}
```

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

ShopBridge rejects mismatched `quote_hash`, original transaction reference,
rail, amount, currency, or missing refund reference. Production verifier
implementations should also reject reused refund references.

## Current Demo Scope

The repo implements the commerce flow, the verifier contract, and a Stripe/card
MPP sandbox verifier for Link CLI testing. A production verifier still belongs
to the selected payment rail or payment provider deployment because it must
carry provider credentials, refund authority, replay protection, and operational
monitoring.
