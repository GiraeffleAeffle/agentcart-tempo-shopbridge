# Hetzner WooCommerce Staging

This deploys a small staging WooCommerce shop for AgentCart ShopBridge internal
rehearsal before asking a real non-maintainer merchant to test onboarding.

Default target:

- Hetzner Cloud project: `agentcart`
- Server type: `cx23`
- Location: `fsn1`
- Image: `ubuntu-24.04`
- Domain: `woo-staging.agentcart.eu`

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
```

Wait until this resolves:

```sh
dig +short woo-staging.agentcart.eu
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

This is internal rehearsal evidence only. It does not replace the
non-maintainer walkthrough evidence required by
`docs/MERCHANT_SETUP_WALKTHROUGH.md`.
