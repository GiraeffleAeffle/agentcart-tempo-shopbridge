# AgentCart Home-Server Package

This package is the target self-hosted stack for a NUC, mini PC, or Dappnode-like
home server. It packages the household side of the demo, not a production
merchant service.

## Services

- AgentCart gateway
- Household OS chat bridge
- Vikunja + Postgres
- optional Home Assistant container
- optional demo WooCommerce shop

OpenClaw is currently expected to run separately or on the same network. Install
the AgentCart OpenClaw skill from `gateway/openclaw-skill`.

If the buyer does not need the AgentCart service, use the skill-only path
instead:

```sh
../../scripts/package-shopbridge-direct-skill.sh
```

That creates `dist/shopbridge-direct-skill.zip` from the repo root. See
`../../docs/BUYER_SETUP.md` for the skill-only and service-backed buyer setup
paths.

## Quick Start

From the repo root:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Then open:

- AgentCart: `http://localhost:8099/?token=replace-with-random-agentcart-token`
- Demo cockpit: `http://localhost:8099/demo?token=replace-with-random-agentcart-token`
- Household OS: `http://localhost:8088/chat`
- Vikunja: `http://localhost:3456`
- optional Home Assistant: `http://localhost:8123`
- optional Woo demo: `http://localhost:8098`

The AgentCart token value is `AGENTCART_TOKEN` from `.env`. Open AgentCart with
`?token=...` once; the gateway stores it in a local same-origin cookie for the
browser demo pages.

Start optional services with profiles:

```sh
perl -0pi -e 's/WOOCOMMERCE_MODE=disabled/WOOCOMMERCE_MODE=plugin/' .env
docker-compose --profile homeassistant --profile woocommerce-demo up -d --build
```

After starting the Woo demo, install WooCommerce, activate ShopBridge, and seed
demo products through the bundled `wpcli` service:

```sh
docker-compose --profile woocommerce-demo run --rm woocommerce-seed
```

WooCommerce admin defaults come from `.env`: `WOO_ADMIN_USER` and
`WOO_ADMIN_PASSWORD`. AgentCart aftercare defaults for the demo shop are also
set from `.env`: `AGENTCART_RETURNS_URL`, `AGENTCART_SUBSTITUTION_POLICY`, and
`AGENTCART_CANCELLATION_WINDOW_MINUTES`.

## Registry Monitor Alerts

AgentCart can run the hosted merchant registry monitor manually with
`POST /v1/registry/monitor/run` or on a schedule with
`AGENTCART_REGISTRY_MONITOR_INTERVAL_SECONDS`. To deliver new or resolved
registry alert deltas, set `AGENTCART_REGISTRY_ALERT_WEBHOOK_URL`, or enable
`AGENTCART_REGISTRY_ALERT_HOMEASSISTANT_ENABLED=true` with `HOMEASSISTANT_URL`,
`HOMEASSISTANT_TOKEN`, and `HA_NOTIFY_SERVICES`. For email delivery, set
`AGENTCART_REGISTRY_ALERT_EMAIL_TO`, `AGENTCART_REGISTRY_ALERT_EMAIL_FROM`, and
`AGENTCART_REGISTRY_ALERT_SMTP_HOST`; optional SMTP username/password and
STARTTLS settings support authenticated providers or a local relay.

## Commerce Ops Events

AgentCart can also send redacted commerce lifecycle notifications for quote,
checkout, refund, and delivery-exception events. Configure
`AGENTCART_OPS_EVENT_WEBHOOK_URL`, or enable
`AGENTCART_OPS_EVENT_HOMEASSISTANT_ENABLED=true` with `HOMEASSISTANT_URL`,
`HOMEASSISTANT_TOKEN`, and `HA_NOTIFY_SERVICES`. Email delivery uses the
`AGENTCART_OPS_EVENT_EMAIL_*` and `AGENTCART_OPS_EVENT_SMTP_*` variables. These
payloads include ids, hashes, rail/status metadata, and delivery-exception
state; they do not include payment credentials, raw request bodies, or delivery
addresses.

## Files Expected In Repo Root

```text
gateway/
household-os/
demo/woocommerce/
woocommerce-shopbridge/
deploy/home-server/
```

For LAN, homelab, or Tailscale exposure, set the relevant `*_HOST_BIND` values
to `0.0.0.0` or a specific interface in `.env`. The defaults bind to
`127.0.0.1` so a clean local run is not accidentally exposed.

## Production Caveat

The package is for household-agent experimentation. It is not a compliant
payment, medical, tax, or consumer-protection product by itself. Public merchant
orders require an external payment verifier and merchant legal review.
