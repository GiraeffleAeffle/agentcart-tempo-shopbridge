# AgentCart Hackathon

AgentCart is a household-safe bridge between personal agents and opt-in
WooCommerce merchants. It demonstrates the missing commerce layer around MPP:
product discovery, final quote, household policy, human approval, payment proof,
WooCommerce order creation, delivery visibility, refund metadata, and audit.

## What Is In This Repo

```text
gateway/                  AgentCart API, household demo, pitch/architecture pages
household-os/             Home Assistant / Vikunja / OpenClaw chat bridge
woocommerce-shopbridge/   WordPress/WooCommerce plugin
demo/woocommerce/         Local WooCommerce demo shop compose files and seed script
deploy/home-server/       NUC/home-server compose package
docs/                     Hackathon story, runbook, production tracks, protocol notes
```

## Demo Flow

1. Household agent receives: "Please buy my favourite tea".
2. AgentCart resolves the household preference to Hazel's Chocolate Tea.
3. AgentCart discovers two opt-in shops and runs a private quote tournament.
4. The best quote is selected by final price, delivery, policy, and manifest
   integrity.
5. User approves the exact quote.
6. Checkout follows an MPP-shaped HTTP 402 payment flow and attaches a Tempo
   testnet proof.
7. The WooCommerce ShopBridge plugin creates the merchant order.
8. AgentCart updates Vikunja, delivery calendar, and audit state.

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

## Home-Server Package

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Optional profiles:

```sh
docker-compose --profile homeassistant --profile woocommerce-demo up -d --build
```

This starts AgentCart, Household OS, Vikunja, and optional Home Assistant /
WooCommerce demo services. OpenClaw is expected to run separately or on the same
network with the provided skills installed.

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

## Production Tracks

- `docs/PRODUCTION_NEXT_STEPS.md`
- `docs/WOOCOMMERCE_PRODUCTION_HARDENING.md`
- `docs/SETTLEMENT_OPTIONS.md`
- `docs/MERCHANT_REGISTRY.md`
- `docs/DELIVERY_AND_REFUNDS.md`

These are not marketing placeholders. They define the concrete work required to
move from hackathon demo to production candidate.

## Verification

```sh
cd gateway
python3 -m unittest discover -s tests
```

```sh
cd household-os
python3 -m unittest discover -s tests
```

Use `docs/HACKATHON_DEMO.md` for the full presentation runbook and
`docs/PROJECT_STORY.md` for the Devpost story.
