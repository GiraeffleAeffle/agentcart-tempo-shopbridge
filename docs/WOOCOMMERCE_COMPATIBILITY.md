# WooCommerce Compatibility Matrix

Status: alpha release gate for AgentCart ShopBridge.

The machine-readable runtime source is
`gateway/config/woocommerce_compatibility_matrix.json`. The frozen endpoint
contract is `gateway/config/shopbridge_endpoint_contract.json`. Validate them
with:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py
python3 scripts/check-shopbridge-endpoint-contract.py
```

Reset and reseed the bundled demo without removing volumes:

```sh
scripts/woocommerce-demo-reset.sh
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

## Merchant Variance Profiles

External beta needs two materially different WooCommerce merchant profiles. The
profile smoke commands below are Docker-backed and intentionally separate from
the fast source-level checks in `./scripts/verify.sh`.

Run the baseline EU tax/shipping profile:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py \
  --run-smoke \
  --merchant-variance-profile baseline-eu-tax-shipping
```

Expected pilot evidence:
`pilot/pilot-merchant-onboarding/woocommerce_baseline_eu_tax_shipping_result.md`.

This profile stresses:

- tax: EU VAT calculated from shipping destination with prices including tax;
- shipping: taxable `Tracked parcel` flat-rate shipping for Germany and nearby
  EU countries;
- stock: managed stock with soft quote stock holds and checkout-time
  revalidation;
- plugins: WooCommerce latest stable plus ShopBridge with no extra merchant
  policy plugins;
- checkout: quote-bound AgentCart checkout against the standard eligible tea
  SKU.

Run the restricted stock/policy profile:

```sh
python3 scripts/check-woocommerce-compatibility-matrix.py \
  --run-smoke \
  --merchant-variance-profile restricted-stock-policy
```

Expected pilot evidence:
`pilot/pilot-merchant-onboarding/woocommerce_restricted_stock_policy_result.md`.

This profile stresses:

- tax: the same EU VAT rules while product policies narrow the eligible
  checkout set;
- shipping: product-level country restrictions layered on top of the taxable
  tracked parcel zone;
- stock: low managed stock, per-product max quantity limits, and soft stock
  holds during quote and checkout;
- plugins: ShopBridge product exposure, restricted-goods, and aftercare
  metadata on top of WooCommerce latest stable;
- checkout: a capped tea SKU remains eligible for the smoke quote while blocked
  and restricted SKUs stay ineligible.

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
- Endpoint contract: manifest, catalog, quote, order creation, order status,
  refund, and cancellation fields are pinned by fixtures before release.
- Demo reset: `scripts/woocommerce-demo-reset.sh` clears AgentCart-owned demo
  state, reseeds products/tax/shipping/ShopBridge settings, and reruns the live
  quote smoke by default.

Optional runtime smoke:

- WordPress Docker image: `wordpress:php8.1-apache`.
- WP-CLI image: `wordpress:cli-php8.1`.
- Same latest stable WooCommerce archive and endpoint smoke.

The PHP 8.1 minimum is also covered by the PHPCS/WPCS compatibility gate using
PHPCompatibilityWP. Runtime PHP 8.1 should be run before broad external beta
claims when the official image is available.
