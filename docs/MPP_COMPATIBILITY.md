# AgentCart MPP Compatibility Notes

Source checked: https://mpp.dev/llms-full.txt on 2026-06-18.

The MPP MCP server is registered locally for future Codex sessions:

```sh
codex mcp add mpp --url https://mpp.dev/api/mcp
```

The installed Codex CLI uses `--url` for streamable HTTP MCP servers. The
docs show `--transport http`, but that flag is not accepted by this local CLI
version.

## What Matches MPP

AgentCart checkout follows the MPP HTTP authentication control flow:

- unpaid checkout returns `402 Payment Required`
- response includes `WWW-Authenticate: Payment`
- client retries with `Authorization: Payment ...`
- successful checkout returns `Payment-Receipt`
- challenge IDs are single-use
- challenges expire
- checkout requires an idempotency key
- the challenge stores a SHA-256 digest of the request body and rejects retries
  with a different body
- unpaid checkout does not create the merchant order

The OpenAPI discovery document now uses the canonical MPP discovery shape:

```json
{
  "x-payment-info": {
    "offers": [
      {
        "amount": null,
        "currency": "EUR",
        "intent": "charge",
        "method": "demo"
      }
    ]
  }
}
```

The demo offer amount is `null` because AgentCart's demo provider does not move
funds and the final amount is quote-bound.

## Verified MPP Field Boundary

Official MPP is centered on payment authentication, not product checkout. The
fields we should treat as MPP-level are:

| Area | Fields or headers | Notes |
| --- | --- | --- |
| Discovery | `x-payment-info.offers[]`, `amount`, `currency`, `intent`, `method` | Advisory OpenAPI discovery. Runtime `402` challenges remain authoritative. |
| Challenge | `402 Payment Required`, `WWW-Authenticate: Payment`, `id`, `realm`, `method`, `intent`, encoded `request`, optional `opaque`, expiry | Method-specific `request` data can include amount, currency/asset, recipient, splits, Stripe method details, etc. |
| Credential | `Authorization: Payment`, echoed challenge, method-specific `payload` | Tempo, Stripe, Lightning, EVM, and custom methods define their own payload schemas. |
| Receipt | `Payment-Receipt`, method, status, reference, timestamp | Returned after the server verifies the credential. Method-specific receipts may carry transaction hashes, Stripe PaymentIntent references, or similar IDs. |
| Safety | challenge id, expiry, request binding/body digest, idempotency/replay protection | The protocol protects the paid request boundary. Product and order safety remain application responsibilities. |

AgentCart fields are deliberately outside the MPP core:

| Area | AgentCart / ShopBridge fields |
| --- | --- |
| Product | `product_id`, `sku`, `title`, `description`, `category`, `category_slugs`, `brand`, `unit_size`, `image_urls`, `price_cents`, `currency`, `stock`, `availability`, `shipping_regions`, `agentcart_policy`, `restricted_goods` |
| Quote | `items`, `subtotal_cents`, `shipping`, `vat_lines`, `total_cents`, `currency`, `delivery_window`, `merchant_of_record`, `quote_hash`, `expires_at`, `payment_requirements`, item-level `agentcart_policy` |
| Approval | `approval_id`, `quote_id`, `decision_token`, `decision_api`, `channel`, `delivery_channels`, `approver`, `decision_reason` |
| Order | `merchant_order_id`, `status_url`, `status_token`, `shipment`, `tracking`, `delivery_window`, `payment_receipt_id` |
| Audit | intent, product, quote, policy result, approval, payment receipt, merchant order, task/calendar sync |

The live visual version is served at:

```text
http://127.0.0.1:8099/protocol-fields.html
```

## Currency And Settlement

MPP itself is payment-method and currency agnostic. The official docs describe
support for stablecoins, cards, bank transfers, Lightning, and custom rails.

Tempo's built-in MPP payment method is a TIP-20 stablecoin rail. The official
docs describe USDC.e as the mainnet default and pathUSD as the testnet default.
So, in this hackathon demo:

- WooCommerce quotes the physical product in EUR.
- The attached Tempo proof is a USD-stablecoin testnet proof, currently pathUSD.
- This does not prove EUR settlement of the WooCommerce order.

For production with a German/EU WooCommerce shop, one of these must be true:

- the merchant accepts USD-stablecoin settlement and handles accounting/FX;
- a payment provider/verifier converts the EUR quote into a quote-bound
  USD-stablecoin amount before payment;
- the merchant uses a non-stablecoin MPP method such as Stripe/card settlement;
- an EUR stablecoin or custom MPP payment method is supported and configured.

## What Is AgentCart-Specific

MPP is the payment boundary. AgentCart does not need to extend the core MPP
protocol for product discovery. It adds the physical-commerce and household
safety layer around that boundary:

- merchant catalog discovery
- product normalization
- quote tournament and final VAT/shipping quote
- household policy checks
- portable human approval
- merchant order creation
- Vikunja task sync
- delivery calendar/status surfaces
- audit trail explaining why the purchase happened

These are not solved by MPP itself.

If we later need a new payment rail, escrow model, refund credential, or FX
settlement primitive, that would be an MPP payment-method or intent extension.
Catalog, quote, delivery, approval, and order state should remain a separate
commerce adapter/profile around MPP.

## Stripe/Card Or EUR-Compatible Settlement

The WooCommerce plugin can keep the same catalog, quote, and order APIs while
advertising additional MPP methods. Official MPP docs describe Stripe/card
support through Shared Payment Tokens and also allow custom payment methods.

Production options for an EU shop:

- `tempo.charge` with merchant acceptance of USD-stablecoin accounting;
- `tempo.charge` with quote-bound FX handled by a verifier or PSP;
- `stripe.charge` for card settlement, refunds, reporting, disputes, and
  multi-currency payouts through Stripe;
- a custom or future EUR-stablecoin MPP method.

The plugin should create a WooCommerce order only after the selected method's
verifier confirms the quote hash, amount, currency or settlement asset,
recipient, and payment reference. Human browser checkout still needs a normal
WooCommerce payment gateway; AgentCart's order endpoint is for agent checkout.

## Refunds

Refunds should be part of the production profile, but the hackathon demo should
not claim real refund execution unless the payment rail actually moves money
back.

Recommended production model:

- WooCommerce remains the merchant order and refund workflow.
- The AgentCart plugin stores the original payment receipt, rail, reference,
  quote hash, amount, currency/asset, and buyer payment source.
- A Woo refund event calls the configured payment verifier or PSP.
- For Stripe/card, the verifier uses Stripe refund APIs and records the Stripe
  refund id.
- For Tempo/stablecoin settlement, the verifier creates or validates a
  rail-specific refund transfer back to the source wallet and records the refund
  transaction reference.
- AgentCart emits an audit event and updates order status only after the rail
  refund is confirmed.

The current WooCommerce admin Refund button is useful to show that AgentCart
creates a real Woo order surface. In demo mode it is only a merchant workflow
signal, not proof that pathUSD or EUR was refunded.

## What Is Demo-Only

The built-in `demo` provider is not a production MPP payment method. It is an
HTTP 402 Payment-auth simulation for local testing.

The Tempo testnet proof uses official `mppx` against a paid resource and stores
the explorer reference as an external value proof. In the current WooCommerce
demo, the merchant order is still created through the trusted AgentCart gateway
token mode unless an external verifier is configured.

## Production Requirements

Before this becomes production MPP commerce, replace the demo/trusted-token
piece with an official payment method boundary:

- official `mppx` Tempo/Stripe/Lightning/custom method or equivalent verifier
- merchant-owned settlement recipient or PSP-managed payout account
- verifier response bound to quote hash, amount, currency, selected rail,
  rail-specific recipient/profile fields, and transaction reference
- replay protection for transaction references
- refund, chargeback, VAT, shipping, and consumer-rights handling in the
  merchant system
- no sensitive payment credentials in logs
