#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
SECRETS_ENV_FILE="$ROOT_DIR/.secrets/agentcart-staging.env"
SECRETS_YAML_FILE="$ROOT_DIR/.secrets/agentcart-staging.yml"

mkdir -p "$ROOT_DIR/.secrets"
chmod 700 "$ROOT_DIR/.secrets"

if [ -f "$SECRETS_ENV_FILE" ] && [ -f "$SECRETS_YAML_FILE" ]; then
  printf 'staging secrets already exist: %s\n' "$SECRETS_ENV_FILE"
  exit 0
fi

random_hex() {
  openssl rand -hex "$1"
}

domain="woo-staging.agentcart.eu"
admin_user="merchant"
admin_password="$(random_hex 18)"
admin_email="merchant@agentcart.eu"
db_password="$(random_hex 24)"
db_root_password="$(random_hex 24)"
shopbridge_token="$(random_hex 32)"
merchant_id="agentcart-staging-shop"
merchant_name="AgentCart Staging Shop"
tempo_recipient_address="0x0000000000000000000000000000000000a6e7c"
payment_verifier_token="$(random_hex 32)"
stripe_sandbox_secret_key="sk_test_agentcart_staging_demo_not_real"
stripe_profile_id="agentcart_staging_demo_profile"
mpp_secret_key="$(openssl rand -base64 32 | tr -d '\n')"

cat > "$SECRETS_ENV_FILE" <<EOF
STAGING_DOMAIN=woo-staging.agentcart.eu
STAGING_WOO_ADMIN_USER=merchant
STAGING_WOO_ADMIN_PASSWORD=$admin_password
STAGING_WOO_ADMIN_EMAIL=merchant@agentcart.eu
STAGING_DB_PASSWORD=$db_password
STAGING_DB_ROOT_PASSWORD=$db_root_password
STAGING_SHOPBRIDGE_TOKEN=$shopbridge_token
STAGING_MERCHANT_ID=agentcart-staging-shop
STAGING_MERCHANT_NAME=AgentCart Staging Shop
STAGING_TEMPO_RECIPIENT_ADDRESS=$tempo_recipient_address
STAGING_PAYMENT_VERIFIER_TOKEN=$payment_verifier_token
STAGING_STRIPE_SANDBOX_SECRET_KEY=$stripe_sandbox_secret_key
STAGING_STRIPE_PROFILE_ID=$stripe_profile_id
STAGING_MPP_SECRET_KEY=$mpp_secret_key
EOF

cat > "$SECRETS_YAML_FILE" <<EOF
staging:
  domain: "$domain"
  woo_admin_user: "$admin_user"
  woo_admin_password: "$admin_password"
  woo_admin_email: "$admin_email"
  db_password: "$db_password"
  db_root_password: "$db_root_password"
  shopbridge_token: "$shopbridge_token"
  merchant_id: "$merchant_id"
  merchant_name: "$merchant_name"
  tempo_recipient_address: "$tempo_recipient_address"
  payment_verifier_token: "$payment_verifier_token"
  stripe_sandbox_secret_key: "$stripe_sandbox_secret_key"
  stripe_profile_id: "$stripe_profile_id"
  mpp_secret_key: "$mpp_secret_key"
EOF

chmod 600 "$SECRETS_ENV_FILE" "$SECRETS_YAML_FILE"
printf 'created staging secrets: %s\n' "$SECRETS_ENV_FILE"
