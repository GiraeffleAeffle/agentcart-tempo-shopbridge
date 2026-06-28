#!/usr/bin/env bash
set -euo pipefail

cd /var/www/html

for _ in $(seq 1 60); do
  if wp core is-installed --allow-root >/dev/null 2>&1; then
    break
  fi
  if wp core install \
    --url="${WOO_PUBLIC_URL:-http://127.0.0.1:8098}" \
    --title="AgentCart Demo Shop" \
    --admin_user="${WOO_ADMIN_USER:-merchant}" \
    --admin_password="${WOO_ADMIN_PASSWORD:-agentcart-demo-admin}" \
    --admin_email="${WOO_ADMIN_EMAIL:-merchant@example.test}" \
    --skip-email \
    --allow-root >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

wp core is-installed --allow-root
if wp plugin is-installed woocommerce --allow-root; then
  wp plugin activate woocommerce --allow-root
else
  if [ ! -f /tmp/woocommerce.latest-stable.zip ]; then
    curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 \
      -o /tmp/woocommerce.latest-stable.zip \
      https://downloads.wordpress.org/plugin/woocommerce.latest-stable.zip
  fi
  wp plugin install /tmp/woocommerce.latest-stable.zip --activate --allow-root
fi
wp plugin activate agentcart-shopbridge --allow-root

reset_agentcart_demo_state() {
  wp eval "$(cat <<'PHP'
if (!class_exists('WooCommerce')) {
    return;
}

$deleted_orders = 0;
$order_statuses = array_keys(wc_get_order_statuses());
$orders = wc_get_orders([
    'limit' => -1,
    'return' => 'objects',
    'type' => 'shop_order',
    'status' => $order_statuses,
    'meta_query' => [
        'relation' => 'OR',
        [
            'key' => '_agentcart_order_id',
            'compare' => 'EXISTS',
        ],
        [
            'key' => '_agentcart_sandbox_checkout_test',
            'compare' => 'EXISTS',
        ],
    ],
]);
foreach ($orders as $order) {
    if ($order instanceof WC_Order && $order->delete(true)) {
        $deleted_orders++;
    }
}

$reset_options = [
    'agentcart_shopbridge_registry_public_check',
    'agentcart_shopbridge_registry_connection_status',
    'agentcart_shopbridge_registry_health_check',
    'agentcart_shopbridge_registry_revoked_records',
    'agentcart_shopbridge_sandbox_quote_check',
    'agentcart_shopbridge_sandbox_checkout_test',
    'agentcart_shopbridge_product_exposure_preview',
    'agentcart_shopbridge_product_exposure_snapshot',
    'agentcart_shopbridge_stock_holds',
    'agentcart_shopbridge_signed_request_audit',
];
foreach ($reset_options as $option) {
    delete_option($option);
}

global $wpdb;
$prefixes = [
    'agentcart_shopbridge_checkout_lock_',
    'agentcart_shopbridge_quote_lock_',
    'agentcart_shopbridge_refund_lock_',
    'agentcart_shopbridge_cancellation_lock_',
    '_transient_agentcart_shopbridge_quote_',
    '_transient_timeout_agentcart_shopbridge_quote_',
    '_transient_agentcart_shopbridge_rate_',
    '_transient_timeout_agentcart_shopbridge_rate_',
    '_transient_agentcart_shopbridge_signed_nonce_',
    '_transient_timeout_agentcart_shopbridge_signed_nonce_',
];
foreach ($prefixes as $prefix) {
    $wpdb->query(
        $wpdb->prepare(
            "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s",
            $wpdb->esc_like($prefix) . '%'
        )
    );
}

$demo_skus = [
    'AGENT-TEA-HAZEL',
    'AGENT-SHAVER-1',
    'AGENT-DETERGENT-1',
    'AGENT-COFFEE-1',
];
$reset_product_meta = [
    '_agentcart_checkout_blocked',
    '_agentcart_max_quantity',
    '_agentcart_shipping_countries',
    '_agentcart_perishable',
    '_agentcart_deposit_possible',
    '_agentcart_final_sale',
    '_agentcart_substitution_sensitive',
    '_agentcart_restricted_goods_allowed',
];
foreach ($demo_skus as $sku) {
    $product_id = wc_get_product_id_by_sku($sku);
    if (!$product_id) {
        continue;
    }
    foreach ($reset_product_meta as $meta_key) {
        delete_post_meta($product_id, $meta_key);
    }
    update_post_meta($product_id, '_agentcart_enabled', 'yes');
}

wp_cache_flush();
printf("AgentCart demo reset cleared %d AgentCart-created orders and ephemeral ShopBridge state.\n", $deleted_orders);
PHP
)" --allow-root
}

if [ "${AGENTCART_DEMO_RESET:-0}" = "1" ]; then
  reset_agentcart_demo_state
fi

wp option update blogname "AgentCart Demo Shop" --allow-root
wp option update home "${WOO_PUBLIC_URL:-http://127.0.0.1:8098}" --allow-root
wp option update siteurl "${WOO_PUBLIC_URL:-http://127.0.0.1:8098}" --allow-root
wp option update woocommerce_store_address "Demo Street 1" --allow-root
wp option update woocommerce_default_country "DE:BB" --allow-root
wp option update woocommerce_currency "EUR" --allow-root
wp option update woocommerce_prices_include_tax "yes" --allow-root
wp option update woocommerce_calc_taxes "yes" --allow-root
wp option update woocommerce_store_postcode "10115" --allow-root
AGENTCART_DEMO_COUNTRIES_JSON='["DE","AT","NL","BE","LU","FR"]'
wp option update woocommerce_allowed_countries "specific" --allow-root
wp option update woocommerce_specific_allowed_countries "$AGENTCART_DEMO_COUNTRIES_JSON" --format=json --allow-root
wp option update woocommerce_ship_to_countries "specific" --allow-root
wp option update woocommerce_specific_ship_to_countries "$AGENTCART_DEMO_COUNTRIES_JSON" --format=json --allow-root
wp option update woocommerce_coming_soon "no" --allow-root
wp option update woocommerce_cod_settings \
  '{"enabled":"yes","title":"Manual demo checkout","description":"Browser-only fallback for the fake shop. AgentCart orders use household approval and Tempo MPP proof instead of this checkout.","instructions":"For local demos, use the AgentCart household-agent flow for payment proof."}' \
  --format=json \
  --allow-root
wp rewrite structure '/%postname%/' --allow-root
wp rewrite flush --hard --allow-root

configure_demo_tax_shipping() {
  wp eval "$(cat <<'PHP'
if (!class_exists('WooCommerce')) {
    return;
}

update_option('woocommerce_calc_taxes', 'yes');
update_option('woocommerce_prices_include_tax', 'yes');
update_option('woocommerce_tax_based_on', 'shipping');
update_option('woocommerce_shipping_tax_class', 'inherit');
update_option('woocommerce_default_customer_address', 'base');

$countries = ['DE', 'AT', 'NL', 'BE', 'LU', 'FR'];
update_option('woocommerce_allowed_countries', 'specific');
update_option('woocommerce_specific_allowed_countries', $countries);
update_option('woocommerce_ship_to_countries', 'specific');
update_option('woocommerce_specific_ship_to_countries', $countries);

function agentcart_upsert_tax_rate($country, $rate) {
    global $wpdb;
    $table = $wpdb->prefix . 'woocommerce_tax_rates';
    $rate_id = $wpdb->get_var($wpdb->prepare(
        "SELECT tax_rate_id FROM {$table} WHERE tax_rate_country = %s AND tax_rate_class = '' LIMIT 1",
        $country
    ));
    $payload = [
        'tax_rate_country' => $country,
        'tax_rate_state' => '',
        'tax_rate' => number_format((float) $rate, 4, '.', ''),
        'tax_rate_name' => 'VAT',
        'tax_rate_priority' => 1,
        'tax_rate_compound' => 0,
        'tax_rate_shipping' => 1,
        'tax_rate_order' => 0,
        'tax_rate_class' => '',
    ];
    if ($rate_id) {
        $wpdb->update($table, $payload, ['tax_rate_id' => (int) $rate_id]);
    } else {
        $wpdb->insert($table, $payload);
        $rate_id = $wpdb->insert_id;
    }
    WC_Cache_Helper::incr_cache_prefix('taxes');
    return (int) $rate_id;
}

foreach (['DE' => 19.0, 'AT' => 20.0, 'NL' => 21.0, 'BE' => 21.0, 'LU' => 17.0, 'FR' => 20.0] as $country => $rate) {
    agentcart_upsert_tax_rate($country, $rate);
}

$zone = null;
foreach (WC_Shipping_Zones::get_zones() as $zone_data) {
    $candidate = new WC_Shipping_Zone((int) $zone_data['zone_id']);
    if ($candidate->get_zone_name() === 'AgentCart EU Demo') {
        $zone = $candidate;
        break;
    }
}
if (!$zone) {
    $zone = new WC_Shipping_Zone();
    $zone->set_zone_name('AgentCart EU Demo');
    $zone->set_zone_order(0);
    $zone->save();
}
$zone->clear_locations();
foreach ($countries as $country) {
    $zone->add_location($country, 'country');
}
$zone->save();

$flat_rate = null;
foreach ($zone->get_shipping_methods(false) as $method) {
    if ($method->id === 'flat_rate') {
        $flat_rate = $method;
        break;
    }
}
if (!$flat_rate) {
    $instance_id = $zone->add_shipping_method('flat_rate');
    $methods = $zone->get_shipping_methods(false);
    $flat_rate = $methods[$instance_id] ?? null;
}
if ($flat_rate) {
    update_option($flat_rate->get_instance_option_key(), [
        'title' => 'Tracked parcel',
        'tax_status' => 'taxable',
        'cost' => '4.117647',
        'class_costs' => '',
        'type' => 'class',
    ]);
    update_option('woocommerce_' . $flat_rate->id . '_' . $flat_rate->instance_id . '_settings', [
        'title' => 'Tracked parcel',
        'tax_status' => 'taxable',
        'cost' => '4.117647',
        'class_costs' => '',
        'type' => 'class',
    ]);
}
WC_Cache_Helper::get_transient_version('shipping', true);
PHP
)" --allow-root
}

configure_demo_tax_shipping

generate_product_images() {
  mkdir -p /tmp/agentcart-product-images
  php <<'PHP'
<?php
$dir = '/tmp/agentcart-product-images';
if (!is_dir($dir)) {
    mkdir($dir, 0777, true);
}
$font = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';
if (!file_exists($font)) {
    $font = null;
}

function ac_color($image, $hex) {
    $hex = ltrim($hex, '#');
    return imagecolorallocate(
        $image,
        hexdec(substr($hex, 0, 2)),
        hexdec(substr($hex, 2, 2)),
        hexdec(substr($hex, 4, 2))
    );
}

function ac_text($image, $font, $text, $size, $x, $y, $color, $align = 'left') {
    $lines = explode("\n", $text);
    foreach ($lines as $index => $line) {
        $line_y = $y + ($index * ($size + 14));
        if ($font) {
            $box = imagettfbbox($size, 0, $font, $line);
            $width = $box[2] - $box[0];
            $line_x = $align === 'center' ? (int) ($x - ($width / 2)) : $x;
            imagettftext($image, $size, 0, $line_x, $line_y, $color, $font, $line);
        } else {
            imagestring($image, 5, $x, $line_y, $line, $color);
        }
    }
}

function ac_gradient($image, $top, $bottom) {
    $top = sscanf(ltrim($top, '#'), '%02x%02x%02x');
    $bottom = sscanf(ltrim($bottom, '#'), '%02x%02x%02x');
    for ($y = 0; $y < 1200; $y++) {
        $ratio = $y / 1199;
        $r = (int) ($top[0] * (1 - $ratio) + $bottom[0] * $ratio);
        $g = (int) ($top[1] * (1 - $ratio) + $bottom[1] * $ratio);
        $b = (int) ($top[2] * (1 - $ratio) + $bottom[2] * $ratio);
        imageline($image, 0, $y, 1199, $y, imagecolorallocate($image, $r, $g, $b));
    }
}

function ac_round_rect($image, $x1, $y1, $x2, $y2, $radius, $color) {
    imagefilledrectangle($image, $x1 + $radius, $y1, $x2 - $radius, $y2, $color);
    imagefilledrectangle($image, $x1, $y1 + $radius, $x2, $y2 - $radius, $color);
    imagefilledellipse($image, $x1 + $radius, $y1 + $radius, $radius * 2, $radius * 2, $color);
    imagefilledellipse($image, $x2 - $radius, $y1 + $radius, $radius * 2, $radius * 2, $color);
    imagefilledellipse($image, $x1 + $radius, $y2 - $radius, $radius * 2, $radius * 2, $color);
    imagefilledellipse($image, $x2 - $radius, $y2 - $radius, $radius * 2, $radius * 2, $color);
}

function ac_packshot($product, $font, $dir) {
    $image = imagecreatetruecolor(1200, 1200);
    imageantialias($image, true);
    ac_gradient($image, $product['bg_top'], $product['bg_bottom']);
    $shadow = imagecolorallocatealpha($image, 0, 0, 0, 88);
    $paper = ac_color($image, '#fffaf0');
    $ink = ac_color($image, '#1f2933');
    $muted = ac_color($image, '#5b6470');
    $pack = ac_color($image, $product['pack']);
    $accent = ac_color($image, $product['accent']);

    imagefilledellipse($image, 600, 965, 620, 120, $shadow);
    ac_round_rect($image, 330, 210, 870, 950, 42, $pack);
    ac_round_rect($image, 380, 290, 820, 790, 34, $paper);
    imagefilledrectangle($image, 380, 290, 820, 365, $accent);
    imagefilledellipse($image, 600, 525, 190, 190, $accent);
    imagefilledellipse($image, 600, 525, 128, 128, $paper);

    ac_text($image, $font, 'AGENTCART', 28, 600, 345, $ink, 'center');
    ac_text($image, $font, $product['title'], 48, 600, 620, $ink, 'center');
    ac_text($image, $font, $product['kind'], 26, 600, 740, $muted, 'center');
    ac_text($image, $font, $product['badge'], 22, 600, 870, $paper, 'center');

    imagepng($image, $dir . '/' . $product['file']);
    imagedestroy($image);
}

$products = [
    [
        'file' => 'hazels-chocolate-tea.png',
        'title' => "Hazel's\nChocolate",
        'kind' => '100 g herbal tea',
        'badge' => 'Demo Tea',
        'bg_top' => '#f5e6d6',
        'bg_bottom' => '#8b4a5b',
        'pack' => '#44281e',
        'accent' => '#e5b76a',
    ],
    [
        'file' => 'travel-electric-shaver.png',
        'title' => "Travel\nShaver",
        'kind' => 'compact grooming kit',
        'badge' => 'Personal Care',
        'bg_top' => '#e6f2f7',
        'bg_bottom' => '#386070',
        'pack' => '#263743',
        'accent' => '#9ed7e5',
    ],
    [
        'file' => 'laundry-detergent-refill.png',
        'title' => "Laundry\nRefill",
        'kind' => '1.5 L household supply',
        'badge' => 'Refill Pack',
        'bg_top' => '#edf7ee',
        'bg_bottom' => '#4b7f5f',
        'pack' => '#244735',
        'accent' => '#b9e08f',
    ],
    [
        'file' => 'morning-coffee-beans.png',
        'title' => "Morning\nCoffee",
        'kind' => '250 g whole beans',
        'badge' => 'Coffee',
        'bg_top' => '#f3e6d8',
        'bg_bottom' => '#6f4933',
        'pack' => '#3b2b23',
        'accent' => '#d5a15f',
    ],
];

foreach ($products as $product) {
    ac_packshot($product, $font, $dir);
}
PHP
}

generate_product_images

ensure_category() {
  local slug="$1"
  local name="$2"
  if ! wp term get product_cat "$slug" --by=slug --allow-root >/dev/null 2>&1; then
    wp term create product_cat "$name" --slug="$slug" --allow-root >/dev/null
  fi
}

ensure_product() {
  local sku="$1"
  local name="$2"
  local price="$3"
  local stock="$4"
  local category_slug="$5"
  local short_description="$6"
  local weight="${7:-unit}"
  local image_file="${8:-}"
  local category_id
  category_id="$(wp term get product_cat "$category_slug" --by=slug --field=term_id --allow-root)"
  local description
  description="$(product_description "$sku")"
  local product_id
  product_id="$(wp wc product list --sku="$sku" --user="${WOO_ADMIN_USER:-merchant}" --allow-root --format=ids | head -n 1 || true)"
  if [ -z "$product_id" ]; then
    wp wc product create \
      --user="${WOO_ADMIN_USER:-merchant}" \
      --name="$name" \
      --type=simple \
      --regular_price="$price" \
      --sku="$sku" \
      --manage_stock=true \
      --stock_quantity="$stock" \
      --weight="$weight" \
      --short_description="$short_description" \
      --description="$description" \
      --categories="[{\"id\":${category_id}}]" \
      --allow-root >/dev/null
    product_id="$(wp wc product list --sku="$sku" --user="${WOO_ADMIN_USER:-merchant}" --allow-root --format=ids | head -n 1)"
  else
    wp wc product update "$product_id" \
      --user="${WOO_ADMIN_USER:-merchant}" \
      --name="$name" \
      --regular_price="$price" \
      --manage_stock=true \
      --stock_quantity="$stock" \
      --weight="$weight" \
      --short_description="$short_description" \
      --description="$description" \
      --categories="[{\"id\":${category_id}}]" \
      --allow-root >/dev/null
  fi
  wp post meta update "$product_id" _agentcart_enabled yes --allow-root >/dev/null
  ensure_featured_image "$product_id" "$image_file" "$name"
}

product_description() {
  case "$1" in
    AGENT-TEA-HAZEL)
      printf '%s' '<p>A chocolate-hazelnut herbal tea refill for the household stock demo. The agent can read stock, VAT, shipping, delivery estimate, merchant identity, and checkout eligibility before asking for approval.</p><ul><li>100 g refill pack</li><li>Ships from the opt-in AgentCart demo merchant</li><li>Used for the favorite-tea purchase flow</li></ul>'
      ;;
    AGENT-SHAVER-1)
      printf '%s' '<p>A compact travel shaver used to prove that AgentCart works across ordinary product categories. The same WooCommerce plugin exposes final quote terms and lets AgentCart create a paid order after household approval.</p><ul><li>USB-C style travel kit</li><li>Small package suitable for standard shipping</li><li>Personal-care category allowed by household policy</li></ul>'
      ;;
    AGENT-DETERGENT-1)
      printf '%s' '<p>A household detergent refill for recurring stock automation demos. It shows how non-food household supplies can be discovered, quoted, approved, paid, ordered, and added to Vikunja.</p><ul><li>1.5 L refill pack</li><li>Reusable household supply SKU</li><li>Agent-readable stock and delivery estimate</li></ul>'
      ;;
    AGENT-COFFEE-1)
      printf '%s' '<p>Whole bean morning coffee for a realistic household restock scenario. The product is intentionally ordinary: the interesting part is the agent-compatible merchant interface around it.</p><ul><li>250 g whole beans</li><li>Recurring pantry item</li><li>Visible in both WooCommerce and the AgentCart catalog API</li></ul>'
      ;;
    *)
      printf '%s' '<p>AgentCart demo product exposed through the WooCommerce ShopBridge plugin.</p>'
      ;;
  esac
}

ensure_featured_image() {
  local product_id="$1"
  local image_file="$2"
  local image_title="$3"
  if [ -z "$image_file" ] || [ ! -f "/tmp/agentcart-product-images/$image_file" ]; then
    return
  fi
  local image_slug="${image_file%.png}"
  local attachment_id
  attachment_id="$(wp post list --post_type=attachment --name="$image_slug" --field=ID --allow-root | head -n 1 || true)"
  if [ -z "$attachment_id" ]; then
    attachment_id="$(wp media import "/tmp/agentcart-product-images/$image_file" \
      --post_id="$product_id" \
      --title="$image_slug" \
      --porcelain \
      --allow-root)"
    wp post update "$attachment_id" --post_name="$image_slug" --post_title="$image_title" --allow-root >/dev/null
  fi
  wp post meta update "$product_id" _thumbnail_id "$attachment_id" --allow-root >/dev/null
}

ensure_category tea "Tea"
ensure_category personal-care "Personal Care"
ensure_category household "Household Supplies"
ensure_category coffee "Coffee"

ensure_product AGENT-TEA-HAZEL "Hazel's Chocolate Tea" "9.90" 12 tea "Chocolate-hazelnut herbal tea for the household restock demo." "100 g" "hazels-chocolate-tea.png"
ensure_product AGENT-SHAVER-1 "Travel Electric Shaver" "24.90" 4 personal-care "Compact shaver exposed through the AgentCart WooCommerce plugin." "1 unit" "travel-electric-shaver.png"
ensure_product AGENT-DETERGENT-1 "Laundry Detergent Refill" "8.40" 9 household "Household detergent refill with agent-readable checkout." "1.5 L" "laundry-detergent-refill.png"
ensure_product AGENT-COFFEE-1 "Morning Coffee Beans" "13.50" 8 coffee "Whole bean coffee for recurring household stock." "250 g" "morning-coffee-beans.png"

ensure_page() {
  local slug="$1"
  local title="$2"
  local content="$3"
  local page_id
  page_id="$(wp post list --post_type=page --name="$slug" --field=ID --allow-root | head -n 1 || true)"
  if [ -z "$page_id" ]; then
    page_id="$(wp post create \
      --post_type=page \
      --post_status=publish \
      --post_name="$slug" \
      --post_title="$title" \
      --post_content="$content" \
      --porcelain \
      --allow-root)"
  else
    wp post update "$page_id" \
      --post_status=publish \
      --post_title="$title" \
      --post_content="$content" \
      --allow-root >/dev/null
  fi
  echo "$page_id"
}

home_page_id="$(ensure_page agentcart-products "AgentCart Demo Shop" '[products columns="4" limit="12" orderby="title"]')"
terms_page_id="$(ensure_page terms "Terms" '<p>AgentCart demo terms for quote-bound household-agent checkout. The WooCommerce merchant remains merchant of record and fulfills physical orders after payment verification.</p>')"
returns_page_id="$(ensure_page returns "Returns and Refunds" '<p>Demo returns page. Real production merchants must publish their own return, refund, cancellation, and support policies. AgentCart refund records can be created through WooCommerce after merchant approval.</p>')"
wp option update show_on_front page --allow-root
wp option update page_on_front "$home_page_id" --allow-root
wp option update woocommerce_terms_page_id "$terms_page_id" --allow-root

configure_shopbridge_demo_settings() {
  local public_url="${WOO_PUBLIC_URL:-http://127.0.0.1:8098}"
  wp option update agentcart_shopbridge_merchant_id "${AGENTCART_MERCHANT_ID:-woocommerce-demo-shop}" --allow-root
  wp option update agentcart_shopbridge_token "${AGENTCART_SHOPBRIDGE_TOKEN:-agentcart-woo-demo-token}" --allow-root
  wp option update agentcart_shopbridge_support_email "${WOO_ADMIN_EMAIL:-merchant@example.test}" --allow-root
  wp option update agentcart_shopbridge_returns_url "${AGENTCART_RETURNS_URL:-${public_url}/returns}" --allow-root
  wp option update agentcart_shopbridge_substitution_policy "${AGENTCART_SUBSTITUTION_POLICY:-approval_required}" --allow-root
  wp option update agentcart_shopbridge_cancellation_window_minutes "${AGENTCART_CANCELLATION_WINDOW_MINUTES:-30}" --allow-root
  wp option update agentcart_shopbridge_tempo_network "${AGENTCART_TEMPO_NETWORK:-testnet}" --allow-root
  wp option update agentcart_shopbridge_tempo_recipient "${AGENTCART_TEMPO_RECIPIENT_ADDRESS:-}" --allow-root
  wp option update agentcart_shopbridge_stripe_profile_id "${AGENTCART_STRIPE_PROFILE_ID:-}" --allow-root
  wp option update agentcart_shopbridge_payment_verifier_url "${AGENTCART_PAYMENT_VERIFIER_URL:-}" --allow-root
  wp option update agentcart_shopbridge_payment_verifier_token "${AGENTCART_PAYMENT_VERIFIER_TOKEN:-}" --allow-root
  wp option update agentcart_shopbridge_checkout_mode "${AGENTCART_CHECKOUT_MODE:-trusted_token_or_verifier}" --allow-root
  wp option update agentcart_shopbridge_signed_request_mode "${AGENTCART_SIGNED_REQUEST_MODE:-off}" --allow-root
  wp option update agentcart_shopbridge_product_exposure_mode "${AGENTCART_PRODUCT_EXPOSURE_MODE:-manual}" --allow-root
  wp option update agentcart_shopbridge_product_exposure_tag "${AGENTCART_PRODUCT_EXPOSURE_TAG:-agentcart-safe}" --allow-root
  wp option update agentcart_shopbridge_product_exposure_categories "${AGENTCART_PRODUCT_EXPOSURE_CATEGORIES:-}" --allow-root
  wp option update agentcart_shopbridge_product_blocked_categories "${AGENTCART_PRODUCT_BLOCKED_CATEGORIES:-}" --allow-root
  wp option update agentcart_shopbridge_stock_hold_mode "${AGENTCART_STOCK_HOLD_MODE:-soft}" --allow-root
  wp option update agentcart_shopbridge_stock_hold_minutes "${AGENTCART_STOCK_HOLD_MINUTES:-15}" --allow-root
  wp option delete agentcart_shopbridge_registry_public_check --allow-root >/dev/null 2>&1 || true
  wp option delete agentcart_shopbridge_registry_connection_status --allow-root >/dev/null 2>&1 || true
  wp option delete agentcart_shopbridge_registry_health_check --allow-root >/dev/null 2>&1 || true
}

configure_shopbridge_demo_settings

wp eval "$(cat <<'PHP'
if (class_exists('WooCommerce')) {
    foreach (wc_get_orders(['limit' => 20, 'return' => 'objects', 'meta_key' => '_agentcart_order_id']) as $order) {
        if (!$order->get_meta('_tracking_number', true)) {
            $tracking_number = 'AC-DEMO-' . $order->get_order_number();
            $order->update_meta_data('_tracking_provider', 'AgentCart Demo Parcel');
            $order->update_meta_data('_tracking_number', $tracking_number);
            $order->update_meta_data('_tracking_url', home_url('/?agentcart_demo_tracking=' . rawurlencode($tracking_number)));
            $order->add_order_note('AgentCart demo tracking metadata attached by the seed script.');
            $order->save();
        }
    }
}
PHP
)" --allow-root

echo "AgentCart WooCommerce demo shop is ready."
echo "Admin: ${WOO_ADMIN_USER:-merchant} / ${WOO_ADMIN_PASSWORD:-agentcart-demo-admin}"
echo "ShopBridge token: ${AGENTCART_SHOPBRIDGE_TOKEN:-agentcart-woo-demo-token}"
