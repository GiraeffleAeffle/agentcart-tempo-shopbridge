# Hetzner WooCommerce Staging

This deploys a small staging WooCommerce shop for AgentCart ShopBridge internal
rehearsal before asking a real non-maintainer merchant to test onboarding.

Default target:

- Hetzner Cloud project: `agentcart`
- Server type: `cx23`
- Location: `fsn1`
- Image: `ubuntu-24.04`
- Domain: `woo-staging.agentcart.eu`
- USD Tempo staging domain: `woo-usd.agentcart.eu`

## Local Secrets

The Hetzner token and generated credentials must stay outside git:

```sh
mkdir -p .secrets
chmod 700 .secrets
cat > .secrets/hetzner.env <<'EOF'
HCLOUD_TOKEN=replace-with-hetzner-cloud-project-token
EOF
chmod 600 .secrets/hetzner.env
ssh-keygen -t ed25519 -f .secrets/agentcart_staging_ed25519 -C agentcart-staging
```

Generate the staging application secrets:

```sh
deploy/hetzner-staging/scripts/generate-staging-secrets.sh
```

The generated secrets include a non-real Tempo testnet recipient and an
internal verifier bearer token. Staging uses these to exercise quote-bound
public checkout with replay protection; the verifier still reports Tempo demo
payments as not real settlement evidence.

Generate a second, isolated secret set for the USD Tempo staging shop:

```sh
deploy/hetzner-staging/scripts/generate-usd-staging-secrets.sh
```

This writes `.secrets/agentcart-staging-usd.env` and
`.secrets/agentcart-staging-usd.yml`. The USD shop uses a separate WordPress
database volume, ShopBridge token, verifier replay store, and merchant id.

## Provision Server

Run Terraform through Docker so no local Terraform installation is required:

```sh
source .secrets/hetzner.env
docker run --rm \
  -e HCLOUD_TOKEN \
  -v "$PWD:/workspace" \
  -w /workspace/deploy/hetzner-staging/terraform \
  hashicorp/terraform:1.9 init
docker run --rm \
  -e HCLOUD_TOKEN \
  -v "$PWD:/workspace" \
  -w /workspace/deploy/hetzner-staging/terraform \
  hashicorp/terraform:1.9 apply
```

The output prints the server IPv4 address.
Terraform state is stored locally at
`.secrets/terraform/hetzner-staging.tfstate`, not in the module directory.

## DNS

Create this DNS record in Hetzner DNS or the domain DNS UI:

```text
A  woo-staging  <terraform server_ipv4 output>
A  woo-usd      <terraform server_ipv4 output>
```

The Hetzner Cloud token used by Terraform provisions servers. It does not
necessarily grant Hetzner DNS API access. If the DNS API is not separately
configured, add the `woo-usd` record in the Console DNS UI.

Wait until this resolves:

```sh
dig +short woo-staging.agentcart.eu
dig +short woo-usd.agentcart.eu
```

## Deploy WooCommerce

After DNS points at the server:

```sh
ansible-playbook \
  -i "$(cd deploy/hetzner-staging/terraform && docker run --rm -e HCLOUD_TOKEN -v "$PWD/../../..:/workspace" -w /workspace/deploy/hetzner-staging/terraform hashicorp/terraform:1.9 output -raw server_ipv4)," \
  -u root \
  --private-key .secrets/agentcart_staging_ed25519 \
  deploy/hetzner-staging/ansible/playbook.yml
```

Open:

```text
https://woo-staging.agentcart.eu/wp-admin/
```

Admin credentials are stored locally in `.secrets/agentcart-staging.env`.
If you intentionally rotate `STAGING_DB_PASSWORD` after the first deploy, reset
the staging database volume before rerunning Ansible:

```sh
ssh -i .secrets/agentcart_staging_ed25519 root@<server-ip> \
  'cd /opt/agentcart-woocommerce-staging && docker compose down -v'
```

## Smoke Test

```sh
python3 scripts/woocommerce-shopbridge-smoke.py \
  --base-url https://woo-staging.agentcart.eu \
  --require-shipping \
  --require-vat-lines
```

The public buyer-skill checkout path is configured for
`external_verifier_only` mode. The WordPress container calls the internal
`verifier` service at `http://verifier:4260/agentcart/verify`; the verifier is
not exposed through Caddy.

## Deploy USD Tempo Staging Shop

After the base `woo-staging` stack is deployed and
`woo-usd.agentcart.eu` points to the same server IPv4:

```sh
deploy/hetzner-staging/scripts/generate-usd-staging-secrets.sh
ansible-playbook \
  -i "$(cd deploy/hetzner-staging/terraform && docker run --rm -e HCLOUD_TOKEN -v "$PWD/../../..:/workspace" -w /workspace/deploy/hetzner-staging/terraform hashicorp/terraform:1.9 output -raw server_ipv4)," \
  -u root \
  --private-key .secrets/agentcart_staging_ed25519 \
  deploy/hetzner-staging/ansible/usd-shop.yml
```

The USD playbook keeps the EUR staging shop intact. It deploys a second
WordPress/database/verifier stack under `/opt/agentcart-woocommerce-usd`, joins
the existing Caddy Docker network, and adds a Caddy route for
`woo-usd.agentcart.eu`.

Smoke-test the USD quote path:

```sh
scripts/woocommerce-usd-staging-smoke.sh
```

Run the mutable endpoint harness after checking that the shop can be reset:

```sh
scripts/woocommerce-usd-staging-smoke.sh --endpoint-harness
```

The USD endpoint harness uses a quote-bound demo Tempo proof so checkout,
status, cancellation, idempotency, and verifier replay behavior can be tested
without pretending that real money moved. Refunds return a
`tempo_refund_adapter_missing` rejection while
`STAGING_TEMPO_REFUND_MODE=disabled`; do not treat that harness result as
`real_refund_verified=true`.

To exercise a real `mppx` testnet payment proof instead of the synthetic proof,
the USD staging shop must advertise a syntactically valid Tempo/EVM recipient
address that you control for testnet. For fresh secrets, set
`AGENTCART_TEMPO_RECIPIENT_ADDRESS` before running the generator. For an
existing deployment, update `STAGING_TEMPO_RECIPIENT_ADDRESS` in
`/opt/agentcart-woocommerce-usd/.env` and recreate the WordPress container.

Then create and fund a local mppx testnet account:

```sh
cd gateway
npm run mpp:account:create
npm run mpp:account:fund
cd ..
scripts/woocommerce-usd-mppx-settlement-smoke.sh
```

This starts the local AgentCart MPP paid resource, pays it with `mppx`, submits
the resulting `payment-receipt` proof to the USD staging checkout, and then
cleans up the local paid-resource process. A successful run proves the staging
checkout accepts a quote-bound Tempo testnet value-transfer proof. It is still
not a production settlement claim unless the recipient is a distinct merchant
wallet and the refund wallet is configured for live testnet transfers.

To test real Tempo/pathUSD settlement and refund on testnet, configure the USD
staging secrets with a merchant-controlled recipient, on-chain settlement
verification, and the matching refund wallet:

```yaml
staging:
  tempo_recipient_address: "0x..."
  tempo_settlement_mode: "verify"
  tempo_settlement_asset: "pathUSD"
  tempo_settlement_token_address: "0x20c0000000000000000000000000000000000000"
  tempo_refund_mode: "live"
  tempo_refund_private_key: "0x..."
  tempo_refund_asset: "pathUSD"
  tempo_refund_token_address: "0x20c0000000000000000000000000000000000000"
```

With settlement mode `verify`, the verifier waits for the Tempo transaction
receipt and requires an ERC-20 `Transfer` from the proof payer to
`tempo_recipient_address` for the exact quote amount before it returns
`real_settlement_verified=true`.

The refund private key must belong to the original
`tempo_recipient_address`; the verifier rejects mismatches and only marks a
refund as `real_refund_verified=true` after a successful on-chain transfer
receipt.

The USD shop is for Tempo/pathUSD flow validation. Do not use it to claim EUR
settlement, EUR refunds, or production merchant readiness.

This is internal rehearsal evidence only. It does not replace the
non-maintainer walkthrough evidence required by
`docs/MERCHANT_SETUP_WALKTHROUGH.md`.
