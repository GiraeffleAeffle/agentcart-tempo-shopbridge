# woocommerce_compatibility_matrix_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:39Z
- Operator: Codex local verification session authorized by Max (GiraeffleAeffle)
- Command or source: required PHP 8.2 runtime matrix and both beta variance-profile smokes

## Evidence

The required `wp-latest-php82-woo-latest` matrix entry passed twice against
fresh Docker volumes using latest WordPress, PHP 8.2, latest stable WooCommerce,
and the current ShopBridge source. Both runs installed and activated
WooCommerce and ShopBridge, seeded the shop, waited for the capability endpoint,
created a final quote, validated manifest and registry documents, and removed
their containers and volumes. The baseline and restricted-stock results are
recorded in their dedicated evidence files. The complete repository gate also
passed official WordPress Plugin Check and PHPCS/WPCS checks.
