# Buyer Setup

> Status: alpha setup path for testers. Use the skill-only path for the lowest
> friction buyer integration. Use the AgentCart service path when the buyer
> needs durable household policy, approval state, audit, and local integrations.

## Choose A Buyer Mode

| Mode | Install | Best for | Tradeoff |
| --- | --- | --- | --- |
| Skill-only ShopBridge | Install `dist/shopbridge-direct-skill.zip` or copy `gateway/shopbridge-direct-skill` into the agent's skill folder | A buyer agent that can run local scripts and talk directly to verified ShopBridge merchants | Approval and audit are local to the agent chat unless the agent provides persistence |
| AgentCart service | Run `deploy/home-server` and install `gateway/openclaw-skill` | Household policy, Home Assistant/Vikunja/calendar/audit integrations, durable approvals | More moving parts and a local service to operate |

Both modes only use opt-in ShopBridge merchants. Do not scrape normal shop
websites or infer checkout endpoints from merchant prose.

## Skill-Only Setup

Build the installable skill bundle:

```sh
./scripts/package-shopbridge-direct-skill.sh
```

This creates:

```text
dist/shopbridge-direct-skill.zip
```

Install by extracting the ZIP into the buyer agent's skills directory, or by
copying this folder directly:

```text
gateway/shopbridge-direct-skill
```

The skill has no long-running service dependency. It needs `python3` and network
access to the merchant's ShopBridge origin.

For a known single merchant, set:

```sh
export SHOPBRIDGE_BASE_URL=http://127.0.0.1:8098
```

For production-style multi-merchant discovery, pass verified registry records to
the skill commands instead of relying on `SHOPBRIDGE_BASE_URL`. A verified
record binds the merchant domain, manifest URL, payment destination, proof URL,
and revocation URL before the skill calls catalog or quote.

For a normal skill-only install, configure one trusted registry source once:

```sh
export SHOPBRIDGE_REGISTRY_URL=https://registry.example/agentcart.json
```

For local/self-hosted testing without a public registry:

```sh
export SHOPBRIDGE_REGISTRY_PATH=/path/to/merchant-registry.json
```

The direct skill rejects records with missing/invalid timestamps, records dated
more than 10 minutes in the future, and records older than
`SHOPBRIDGE_REGISTRY_MAX_AGE_DAYS` days. The default is `180`; use `0` only for
local fixtures where you intentionally want to disable the freshness window.

Smoke test a known merchant:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"readiness","args":{"base_url":"http://127.0.0.1:8098","format":"toon"}}
JSON
```

Quote and approval packet:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"quote","args":{"base_url":"http://127.0.0.1:8098","product_id":"woo_10","quantity":1}}
JSON
```

For groceries, prefer whole-basket discovery:

```sh
python3 gateway/shopbridge-direct-skill/scripts/shopbridge-command.py <<'JSON'
{"command":"discover_basket_quotes","args":{"basket":[{"query":"tea","quantity":1},{"query":"filters","quantity":2}],"country":"DE","postal_code":"10115","payment_rail":"stripe-card-mpp","format":"toon"}}
JSON
```

That command uses `SHOPBRIDGE_REGISTRY_URL` or `SHOPBRIDGE_REGISTRY_PATH`.
Alternatively, pass `registry_records`, `registry_url`, or `registry_path` in the
command args for one-off tests.

Checkout safety:

- Always create or inspect an `approval_packet` before checkout.
- Do not call `checkout` until the human approves the exact merchant, items,
  total, delivery window, quote hash, and payment destination.
- After approval, call `payment_handoff` to get the structured payment request
  for the wallet, payment-capable agent, or provider. The request is not a
  secret and does not move money; it says exactly which rail, amount, currency,
  quote hash, and merchant profile/recipient the resulting receipt must bind.
- Pass only the resulting quote-bound `payment_receipt` to `checkout`.
- Treat aftercare actions such as refund or cancellation as request drafts
  unless the buyer is using a trusted AgentCart gateway with merchant
  authorization. ShopBridge cancellation changes Woo order state only; paid
  orders still need a separate rail-verified refund.
- Production checkout must supply a verifier/payment receipt bound to amount,
  currency, quote hash, merchant recipient/profile, and transaction reference.
- The Tempo demo proof is sandbox/testnet proof, not production EUR settlement.

Skill-only production sequence:

```text
resolve_merchant -> catalog/quote -> approval_packet -> human approval
  -> payment_handoff -> external payment receipt -> checkout -> order_status
```

`resolve_merchant` must reject stale records, failed domain proofs, off-domain
endpoints, and matching merchant-hosted revocation documents.

## AgentCart Service Setup

Use the home-server package when the buyer wants durable state and integrations:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Open:

```text
http://localhost:8099/?token=replace-with-random-agentcart-token
http://localhost:8088/chat
```

Install the service-backed agent skill from:

```text
gateway/openclaw-skill
```

Configure the agent environment:

```sh
AGENTCART_URL=http://localhost:8099
AGENTCART_TOKEN=replace-with-random-agentcart-token
```

For OpenClaw-style deployments, the helper also reads:

```text
/etc/openclaw/agentcart.env
```

## Local Merchant For Independent Testing

A tester can run the optional WooCommerce demo shop without your homelab:

```sh
scripts/woocommerce-demo-smoke.sh
```

That command starts the demo WooCommerce stack, seeds products/tax/shipping, and
verifies the public ShopBridge manifest, catalog, and WooCommerce-backed quote
totals. Manual startup is also available:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose --profile woocommerce-demo up -d --build
docker-compose --profile woocommerce-demo run --rm woocommerce-seed
```

Then install or activate the packaged plugin:

```text
dist/agentcart-shopbridge.zip
```

Open the local ShopBridge endpoints:

```text
http://localhost:8098/.well-known/agentcart.json
http://localhost:8098/wp-json/agentcart/v1/catalog
```

## Network Notes

Defaults bind to `127.0.0.1`. For LAN or Tailscale testing, change the relevant
`*_HOST_BIND` values in `deploy/home-server/.env` to `0.0.0.0` or a specific
interface. Do not expose the demo stack publicly without a real payment
verifier, TLS, host-level rate limits, and merchant legal review.
