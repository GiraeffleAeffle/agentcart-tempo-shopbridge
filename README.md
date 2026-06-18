# AgentCart Hackathon

AgentCart is a household-safe bridge between personal agents and opt-in
WooCommerce merchants. It demonstrates the missing commerce layer around MPP:
product discovery, final quote, household policy, human approval, payment proof,
WooCommerce order creation, delivery visibility, refund metadata, and audit.

## What Is In This Repo

```text
gateway/                  AgentCart API, household demo, pitch/architecture pages
woocommerce-shopbridge/   WordPress/WooCommerce plugin
demo/woocommerce/         Local WooCommerce demo shop compose files and seed script
docs/                     Hackathon runbook, MPP compatibility, review prompt
```

## Demo Flow

1. Household agent receives: "buy my favorite tea, Hazel's Chocolate".
2. AgentCart discovers two opt-in shops and runs a private quote tournament.
3. The best quote is selected by final price, delivery, policy, and manifest
   integrity.
4. User approves the exact quote.
5. Checkout follows an MPP-shaped HTTP 402 payment flow and attaches a Tempo
   testnet proof.
6. The WooCommerce ShopBridge plugin creates the merchant order.
7. AgentCart updates task/calendar/audit state.
8. Optional refund demo records a WooCommerce refund object while clearly
   stating whether a real Stripe/card or Tempo refund was verified.

## Important Boundary

MPP handles payment challenge, credential, and receipt. AgentCart does not
extend core MPP for products. ShopBridge adds the commerce profile around MPP:
catalog, quote, VAT, shipping, merchant of record, order, delivery, refund, and
audit fields.

The hackathon demo uses EUR product quotes and a pathUSD Tempo testnet proof.
That is not real EUR settlement. Production needs one of:

- merchant acceptance of stablecoin settlement and accounting;
- quote-bound FX through a verifier/payment provider;
- Stripe/card MPP settlement;
- a future EUR-compatible MPP rail.

## Local Gateway

```sh
cd gateway
AGENTCART_BIND=127.0.0.1 AGENTCART_PORT=8099 python3 agentcart.py
```

Open:

```text
http://127.0.0.1:8099/presentation.html
http://127.0.0.1:8099/onboarding.html
http://127.0.0.1:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=15344
```

## WooCommerce Plugin

Install `woocommerce-shopbridge/agentcart-shopbridge` into:

```text
wp-content/plugins/agentcart-shopbridge
```

Then activate it in WordPress and open `WooCommerce -> AgentCart`.

The plugin exposes:

- `/.well-known/agentcart.json`
- `/wp-json/agentcart/v1/catalog`
- `/wp-json/agentcart/v1/quote`
- `/wp-json/agentcart/v1/orders`
- `/wp-json/agentcart/v1/orders/{id}/status`
- `/wp-json/agentcart/v1/orders/{id}/refunds`

## Verification

```sh
cd gateway
python3 -m unittest discover -s tests
npx mppx discover validate http://127.0.0.1:8099/openapi.json
```

Use `docs/HACKATHON_DEMO.md` for the full presentation runbook.
