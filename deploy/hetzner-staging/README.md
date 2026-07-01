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
without pretending that real money moved. Refunds are expected to return a
`tempo_refund_adapter_missing` rejection until a real Tempo refund adapter is
implemented; do not treat that harness result as `real_refund_verified=true`.

The USD shop is for Tempo/pathUSD flow validation. Do not use it to claim EUR
settlement, EUR refunds, or production merchant readiness. The verifier still
needs the real Tempo refund adapter before `real_refund_verified=true` is a
production claim.

This is internal rehearsal evidence only. It does not replace the
non-maintainer walkthrough evidence required by
`docs/MERCHANT_SETUP_WALKTHROUGH.md`.
