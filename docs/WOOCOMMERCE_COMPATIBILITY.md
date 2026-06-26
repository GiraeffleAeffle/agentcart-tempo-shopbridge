# WooCommerce Compatibility Matrix

Status: alpha release gate for AgentCart ShopBridge.

The machine-readable source is
`gateway/config/woocommerce_compatibility_matrix.json`. Validate it with:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py
```

Run the required Docker runtime smoke:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py --run-smoke
```

Run a single entry:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py \
  --run-smoke \
  --entry wp-latest-php82-woo-latest
```

Run optional entries too:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py \
  --run-smoke \
  --include-optional
```

## Release Baseline

Declared plugin metadata:

- WordPress: 6.4 or newer.
- PHP: 8.1 or newer.
- Required plugin: WooCommerce.

Required runtime smoke:

- WordPress Docker image: `wordpress:php8.2-apache`.
- WP-CLI image: `wordpress:cli-php8.2`.
- WooCommerce: latest stable archive downloaded by the demo setup.
- Live checks: capability, manifest, registry bundle/proof/revocation, catalog,
  final quote, shipping, and VAT lines.

Optional runtime smoke:

- WordPress Docker image: `wordpress:php8.1-apache`.
- WP-CLI image: `wordpress:cli-php8.1`.
- Same latest stable WooCommerce archive and endpoint smoke.

The PHP 8.1 minimum is also covered by the PHPCS/WPCS compatibility gate using
PHPCompatibilityWP. Runtime PHP 8.1 should be run before broad external beta
claims when the official image is available.
