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

Replace the hostnames with your local machine or compose network names:

- AgentCart dashboard: `http://agentcart.local:8099/`
- Pitch deck: `http://agentcart.local:8099/presentation.html`
- Architecture: `http://agentcart.local:8099/architecture.html`
- Buyer/shop onboarding: `http://agentcart.local:8099/onboarding.html`
- Protocol field map: `http://agentcart.local:8099/protocol-fields.html`
- Payment/refund options: `http://agentcart.local:8099/payment-options.html`
- Two-shop quote tournament: `http://agentcart.local:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=10115`
- Agent console fallback: `http://agentcart.local:8099/agent`
- Household OS chat: `http://household-os.local:8088/chat`
- WooCommerce admin: `http://localhost:8081/wp-admin/` when running `demo/woocommerce`

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
the README commands, then open the pages above.

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
5. The plugin exposes `/.well-known/agentcart.json`, catalog, quote, order,
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
