#!/bin/bash
set -euo pipefail
umask 077

site=/var/www/html
export PATH="$site:$PATH"

wp config create \
  --path="$site" \
  --dbname="$WORDPRESS_DB_NAME" \
  --dbuser="$WORDPRESS_DB_USER" \
  --dbpass="$WORDPRESS_DB_PASSWORD" \
  --dbhost="$WORDPRESS_DB_HOST" \
  --skip-check \
  --skip-salts \
  --force \
  --allow-root >/dev/null

set_string() { wp config set "$1" "$2" --path="$site" --allow-root >/dev/null; }
set_raw() { wp config set "$1" "$2" --raw --path="$site" --allow-root >/dev/null; }

set_string AUTH_KEY "$WORDPRESS_AUTH_KEY"
set_string SECURE_AUTH_KEY "$WORDPRESS_SECURE_AUTH_KEY"
set_string LOGGED_IN_KEY "$WORDPRESS_LOGGED_IN_KEY"
set_string NONCE_KEY "$WORDPRESS_NONCE_KEY"
set_string AUTH_SALT "$WORDPRESS_AUTH_SALT"
set_string SECURE_AUTH_SALT "$WORDPRESS_SECURE_AUTH_SALT"
set_string LOGGED_IN_SALT "$WORDPRESS_LOGGED_IN_SALT"
set_string NONCE_SALT "$WORDPRESS_NONCE_SALT"
set_raw DISALLOW_FILE_EDIT true
set_raw DISALLOW_FILE_MODS true
set_raw AUTOMATIC_UPDATER_DISABLED true
set_raw WP_AUTO_UPDATE_CORE false
set_string WP_ENVIRONMENT_TYPE "${WP_ENVIRONMENT_TYPE:-staging}"
set_raw WP_DEBUG false
set_raw WP_POST_REVISIONS 3
set_raw FORCE_SSL_ADMIN true
set_string AGENTCART_SHOPBRIDGE_TOKEN "$AGENTCART_SHOPBRIDGE_TOKEN"
set_string AGENTCART_MERCHANT_ID "$AGENTCART_MERCHANT_ID"
set_string AGENTCART_TEMPO_NETWORK "$AGENTCART_TEMPO_NETWORK"
set_string AGENTCART_TEMPO_RECIPIENT_ADDRESS "$AGENTCART_TEMPO_RECIPIENT_ADDRESS"
set_string AGENTCART_PAYMENT_VERIFIER_URL ""
set_string AGENTCART_PAYMENT_VERIFIER_TOKEN ""
set_raw AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL false
set_string AGENTCART_CHECKOUT_MODE "$AGENTCART_CHECKOUT_MODE"
set_string AGENTCART_SIGNED_REQUEST_MODE "$AGENTCART_SIGNED_REQUEST_MODE"
set_string AGENTCART_SIGNED_REQUEST_SECRET "$AGENTCART_SIGNED_REQUEST_SECRET"

seed_log=/tmp/agentcart-seed.log
if ! /bin/bash /bootstrap/seed-products.sh >"$seed_log" 2>&1; then
  sed -E \
    -e 's/^(Admin:).*/\1 <redacted>/' \
    -e 's/^(ShopBridge token:).*/\1 <redacted>/' \
    "$seed_log" >&2
  exit 1
fi
rm -f "$seed_log"

wp core verify-checksums --version=7.0.3 --allow-root >/dev/null
[[ "$(wp core version --allow-root)" == '7.0.3' ]]
[[ "$(wp plugin get woocommerce --field=version --allow-root)" == '11.0.0' ]]
wp plugin verify-checksums woocommerce --allow-root >/dev/null
[[ "$(wp plugin get agentcart-shopbridge --field=version --allow-root)" == '0.1.0' ]]
touch "$site/.agentcart-seeded"
