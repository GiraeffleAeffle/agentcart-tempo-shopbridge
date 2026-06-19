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

wp option update blogname "AgentCart Demo Shop" --allow-root
wp option update home "${WOO_PUBLIC_URL:-http://127.0.0.1:8098}" --allow-root
wp option update siteurl "${WOO_PUBLIC_URL:-http://127.0.0.1:8098}" --allow-root
wp option update woocommerce_store_address "Demo Street 1" --allow-root
wp option update woocommerce_default_country "DE:BB" --allow-root
wp option update woocommerce_currency "EUR" --allow-root
wp option update woocommerce_prices_include_tax "yes" --allow-root
wp option update woocommerce_calc_taxes "yes" --allow-root
wp option update woocommerce_store_postcode "10115" --allow-root
wp option update woocommerce_coming_soon "no" --allow-root
wp option update woocommerce_cod_settings \
  '{"enabled":"yes","title":"Manual demo checkout","description":"Browser-only fallback for the fake shop. AgentCart orders use household approval and Tempo MPP proof instead of this checkout.","instructions":"For the hackathon demo, use the AgentCart household-agent flow for payment proof."}' \
  --format=json \
  --allow-root
wp rewrite structure '/%postname%/' --allow-root
wp rewrite flush --hard --allow-root

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
  ensure_featured_image "$product_id" "$image_file" "$name"
}

product_description() {
  case "$1" in
    AGENT-TEA-HAZEL)
      printf '%s' '<p>A chocolate-hazelnut herbal tea refill for the household stock demo. The agent can read stock, VAT, shipping, delivery estimate, merchant identity, and checkout eligibility before asking for approval.</p><ul><li>100 g refill pack</li><li>Ships from the opt-in AgentCart demo merchant</li><li>Used for the favorite-tea purchase flow</li></ul>'
      ;;
    AGENT-SHAVER-1)
      printf '%s' '<p>A compact travel shaver used to prove that AgentCart is not tea-specific. The same WooCommerce plugin exposes final quote terms and lets AgentCart create a paid order after household approval.</p><ul><li>USB-C style travel kit</li><li>Small package suitable for standard shipping</li><li>Personal-care category allowed by household policy</li></ul>'
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
wp option update show_on_front page --allow-root
wp option update page_on_front "$home_page_id" --allow-root

echo "AgentCart WooCommerce demo shop is ready."
echo "Admin: ${WOO_ADMIN_USER:-merchant} / ${WOO_ADMIN_PASSWORD:-agentcart-demo-admin}"
echo "ShopBridge token: ${AGENTCART_SHOPBRIDGE_TOKEN:-agentcart-woo-demo-token}"
