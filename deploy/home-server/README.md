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

## Quick Start

From the clean hackathon repo root:

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Then open:

- AgentCart: `http://localhost:8099`
- Household OS: `http://localhost:8088/chat`
- Vikunja: `http://localhost:3456`
- optional Home Assistant: `http://localhost:8123`
- optional Woo demo: `http://localhost:8098`

Start optional services with profiles:

```sh
perl -0pi -e 's/WOOCOMMERCE_MODE=disabled/WOOCOMMERCE_MODE=plugin/' .env
docker-compose --profile homeassistant --profile woocommerce-demo up -d --build
```

After starting the Woo demo, seed demo products from the repo root:

```sh
demo/woocommerce/seed-products.sh
```

## Files Expected In Repo Root

```text
gateway/
household-os/
demo/woocommerce/
woocommerce-shopbridge/
deploy/home-server/
```

If `household-os/` is not present yet, copy it from the homelab source before
publishing the clean repo.

## Production Caveat

The package is for household-agent experimentation. It is not a compliant
payment, medical, tax, or consumer-protection product by itself. Public merchant
orders require an external payment verifier and merchant legal review.
