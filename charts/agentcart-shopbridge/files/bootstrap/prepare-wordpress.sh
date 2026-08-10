#!/bin/sh
set -eu
umask 027

site=/var/www/html
export HOME=/tmp/wp-cli-home
mkdir -p "$HOME"

wp() {
  php -d memory_limit=512M /usr/local/bin/wp "$@"
}

# The pod-local application tree is rebuilt from official sources on every
# pod start. Only uploads and the independently provisioned database persist.
wordpress_zip=/tmp/wordpress-7.0.3.zip
woocommerce_zip=/tmp/woocommerce-11.0.0.zip
extract_root=/tmp/agentcart-clean-source
rm -rf "$extract_root"
mkdir -p "$extract_root"
wget -q -O "$wordpress_zip" https://wordpress.org/wordpress-7.0.3.zip
printf '%s  %s\n' \
  '01c5afff226dbafe548f1138c016039d20e7337fd23f1b28b55f5a3f3fbff1aa' \
  "$wordpress_zip" | sha256sum -cs
wget -q -O "$woocommerce_zip" \
  https://downloads.wordpress.org/plugin/woocommerce.11.0.0.zip
printf '%s  %s\n' \
  'ba08c7fc58c98a11f22866269c5832d85c52b664806ec206036f09737ba21666' \
  "$woocommerce_zip" | sha256sum -cs
unzip -q "$wordpress_zip" -d "$extract_root"
unzip -q "$woocommerce_zip" -d "$extract_root"
find "$site" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -R "$extract_root/wordpress/." "$site/"
rm -rf "$site/wp-content/plugins/woocommerce"
cp -R "$extract_root/woocommerce" "$site/wp-content/plugins/woocommerce"
wp core verify-checksums --path="$site" --version=7.0.3 --allow-root

rm -rf "$site/wp-content/uploads"
ln -s /uploads "$site/wp-content/uploads"
mkdir -p "$site/wp-content/plugins"

cp /usr/local/bin/wp "$site/wp-cli.phar"
printf '%s\n' \
  '#!/bin/sh' \
  'exec php -d memory_limit=512M /var/www/html/wp-cli.phar "$@"' >"$site/wp"
chmod 0555 "$site/wp"
cp -RL /source/agentcart-shopbridge "$site/wp-content/plugins/agentcart-shopbridge"
chmod -R u=rwX,go=rX "$site/wp-content/plugins/agentcart-shopbridge"
rm -rf "$extract_root" "$wordpress_zip" "$woocommerce_zip"
