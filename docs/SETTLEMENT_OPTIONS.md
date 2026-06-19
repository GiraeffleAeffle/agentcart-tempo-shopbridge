# Settlement Options

> Status: roadmap/design notes. The hackathon repo implements the demo slice; this document lists production work that is not complete yet.


AgentCart separates quote/order semantics from the payment rail. The merchant
quotes in the store currency, while the verifier proves that the payment rail
settled or authorized the exact quote.

## Supported Shapes

### Tempo MPP Stablecoin Proof

Useful for the hackathon and machine-payment demonstrations.

- Quote currency: usually merchant storefront currency, for example EUR.
- Tempo proof asset: network-specific stablecoin, for example pathUSD on
  testnet.
- Production requirement: bind FX rate, spread, expiry, recipient, and quote
  hash before marking a WooCommerce order paid.
- Merchant requirement: wallet/custodial recipient and operational handling for
  stablecoin settlement.

### Stripe/Card MPP

Best production story for normal WooCommerce merchants.

- Buyer/agent uses Stripe-compatible payment credential or shared payment token.
- Merchant keeps Stripe account, KYC, payouts, disputes, chargebacks, and card
  refund handling in the existing merchant stack.
- Verifier validates the credential, confirms amount/currency/merchant/quote
  hash, and returns a Stripe payment reference.
- WooCommerce order is created as paid only after verifier success.

### EUR-Compatible MPP Rail

Ideal future option for EU merchants.

- Quote and settlement currency can both be EUR.
- Verifier still must bind amount, recipient, quote hash, expiry, and replay
  protection.
- Merchant onboarding must explain payouts, refunds, disputes, and compliance.

## Verifier Contract

Payment verification request:

```json
{
  "operation": "charge",
  "quote_hash": "sha256...",
  "merchant_id": "merchant.example",
  "expected_amount_cents": 1480,
  "expected_currency": "EUR",
  "payment_method": "stripe-card-mpp",
  "payment_receipt": {
    "method": "stripe-card-mpp",
    "credential": "opaque-agent-payment-credential"
  }
}
```

Successful response:

```json
{
  "ok": true,
  "quote_hash": "sha256...",
  "amount_cents": 1480,
  "currency": "EUR",
  "rail": "stripe-card-mpp",
  "transaction_reference": "pi_...",
  "recipient": "acct_...",
  "real_settlement_verified": true
}
```

Refund verification request:

```json
{
  "operation": "refund",
  "merchant_order_id": "40",
  "original_transaction_reference": "pi_...",
  "amount_cents": 1480,
  "currency": "EUR",
  "reason": "customer requested refund"
}
```

Successful refund response:

```json
{
  "ok": true,
  "amount_cents": 1480,
  "currency": "EUR",
  "rail": "stripe-card-mpp",
  "refund_reference": "re_...",
  "real_refund_verified": true
}
```

## Fail-Closed Rules

- Reject mismatched amount, currency, merchant id, quote hash, recipient, or
  expired quote.
- Reject reused transaction references.
- Reject verifier responses that do not explicitly say `ok: true`.
- Never mark the WooCommerce order paid from a client-supplied receipt alone.
- Never claim EUR settlement when the proof is a USD-stablecoin testnet proof.
