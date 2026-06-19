# AgentCart Hackathon Demo Runbook

This is the public demo path for the Futura Camp Tempo MPP Hackathon.
See `docs/DEMO_RECORDING_PLAN.md` for the 3-minute recording script.

## What To Show

AgentCart does not claim to replace Tempo MPP or x402. It shows the missing
commerce layer around payment for normal small shops and household agents:

- machine-readable catalog and merchant manifest;
- final quote with VAT, shipping, delivery estimate, stock, and merchant of record;
- household policy check and explicit approval;
- HTTP 402/MPP-shaped checkout with a Tempo testnet proof;
- WooCommerce order creation through the ShopBridge plugin;
- Vikunja task update, delivery calendar event, and audit log.

## Demo Surfaces

Default local judging URLs:

- AgentCart dashboard: `http://localhost:8099/`
- Demo cockpit: `http://localhost:8099/demo`
- Pitch deck: `http://localhost:8099/presentation.html`
- Architecture: `http://localhost:8099/architecture.html`
- Buyer/shop onboarding: `http://localhost:8099/onboarding.html`
- Protocol field map: `http://localhost:8099/protocol-fields.html`
- Payment/refund options: `http://localhost:8099/payment-options.html`
- Two-shop quote tournament: `http://localhost:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=10115`
- Agent console fallback: `http://localhost:8099/agent`
- Household OS chat: `http://localhost:8088/chat`
- WooCommerce admin: `http://localhost:8098/wp-admin/` when running `demo/woocommerce`

If `AGENTCART_TOKEN` is configured, open AgentCart browser pages once with the
token from `.env`, for example:

```text
http://localhost:8099/demo?token=replace-with-random-agentcart-token
```

## Preflight

```sh
cd gateway
python3 -m unittest discover -s tests

cd ../household-os
python3 -m unittest discover -s tests

cd ../deploy/home-server
docker-compose --env-file .env.example config
```

For a local recording, start the gateway and optional WooCommerce demo shop with
the README commands. If using the home-server Woo profile, seed it with:

```sh
docker-compose --profile woocommerce-demo run --rm woocommerce-seed
```

Then open the pages above.

## Primary Prompt

Use this in the household chat or the AgentCart console:

```text
Please buy my favourite tea. Discover shops, choose the best final quote, and
ask me for approval before checkout.
```

Expected flow:

1. AgentCart resolves `my favourite tea` to `Hazel's Chocolate Tea` from the
   household preference profile.
2. AgentCart discovers two opt-in merchants.
3. The quote tournament ranks offers by final price, delivery, policy, and
   manifest integrity.
4. The WooCommerce ShopBridge merchant wins when it has the best final quote.
5. The user approves the exact quote in chat, Home Assistant, or the approval URL.
6. AgentCart completes checkout and attaches a Tempo testnet proof.
7. WooCommerce admin shows the created paid order.
8. Vikunja receives `Tea ordered: 1x Hazel's Chocolate Tea`.
9. The order proof page shows delivery estimate, payment proof, merchant order,
   approval, and audit trail.

## Shop Owner View

Show `WooCommerce -> AgentCart` and explain the shop setup:

1. Install the plugin into `wp-content/plugins/agentcart-shopbridge`.
2. Activate it in WordPress.
3. Configure support contact, merchant identity, shipping countries, Tempo
   recipient or verifier settings, and optional Stripe/card profile.
4. Add normal WooCommerce products, stock, VAT/tax, and shipping rules.
5. Enable `Expose through AgentCart` only on products agents may discover and buy, or use the settings-page bulk action for the current published simple-product catalog.
6. The plugin exposes `/.well-known/agentcart.json`, catalog, quote, order,
   status, and refund endpoints for agents.

The merchant remains merchant of record. AgentCart should never scrape or proxy
non-opt-in shops.

## What Not To Claim

- Do not claim a real tea merchant fulfilled the demo order.
- Do not claim real EUR settlement occurred. The demo quotes in EUR and attaches
  a Tempo testnet/pathUSD proof artifact.
- Do not claim the WooCommerce refund button moves money in the demo. Production
  refunds must execute through the original payment rail.
- Do not claim AgentCart extends core MPP. AgentCart adds catalog, quote,
  policy, approval, delivery, refund metadata, and audit fields around MPP.
- Do not claim carrier tracking unless a real carrier/shipment plugin is wired.

## Close

The practical gap is not "can an agent pay?" Tempo MPP already covers machine
payment. The gap is the bridge that lets an ordinary shop safely expose products
to household agents, receive quote-bound payment proof, and create real merchant
orders without browser automation.
