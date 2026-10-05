# WordPress.org Plugin Directory Submission

Status: preparation checklist for listing AgentCart ShopBridge in the
WordPress.org Plugin Directory.

## What WordPress.org Requires

The Plugin Directory is not just a ZIP host. Submission starts by uploading a
production-ready plugin ZIP from the WordPress.org add-plugin page. The ZIP must
be installable through the normal WordPress `Upload Plugin` flow, under 10 MB,
complete, free of development tooling, and ready for manual review.

Official references:

- https://developer.wordpress.org/plugins/wordpress-org/plugin-developer-faq/
- https://developer.wordpress.org/plugins/wordpress-org/detailed-plugin-guidelines/
- https://developer.wordpress.org/plugins/wordpress-org/how-your-readme-txt-works/
- https://developer.wordpress.org/plugins/plugin-basics/header-requirements/
- https://developer.wordpress.org/plugins/wordpress-org/common-issues/

## Slug Decision

WordPress.org generates the plugin slug from the `Plugin Name` header in the
main plugin PHP file during first submission. The slug then controls:

- public URL under `wordpress.org/plugins/...`;
- installed folder name under `wp-content/plugins/...`;
- SVN repository path;
- text domain expected by translation tooling.

Current main plugin name:

```text
AgentCart ShopBridge
```

That should produce the shorter slug `agentcart-shopbridge`, matching the
package folder and text domain. Keep the WooCommerce dependency in the
description and `Requires Plugins: woocommerce` header. If we decide the public
directory title must include `for WooCommerce`, make that change deliberately
before submission and update the package folder/text domain expectations.

Do this before first submission. Once approved, the slug is effectively a
permanent product identity.

## Current Package Readiness

The generated package is:

```sh
dist/agentcart-shopbridge.zip
```

The local package check is:

```sh
./scripts/check-wordpress-plugin-package.py --zip dist/agentcart-shopbridge.zip
```

The local review-risk check is:

```sh
./scripts/check-wordpress-plugin-review.py
```

The official-tool gate is:

```sh
./scripts/check-wordpress-official-gates.py
```

It validates that the repo carries WordPress Coding Standards tooling config in
`woocommerce-shopbridge/composer.json` and `woocommerce-shopbridge/phpcs.xml.dist`.
When `phpcs` is available globally or through `woocommerce-shopbridge/vendor/bin`,
the script runs PHPCS/WPCS against the packaged plugin source. To require those
external tools on a release machine, run:

```sh
cd woocommerce-shopbridge
composer install
cd ..
./scripts/check-wordpress-official-gates.py --strict
```

Strict mode also runs `scripts/run-wordpress-plugin-check.sh` when no custom
Plugin Check command is configured. That script starts the bundled local
WordPress/WooCommerce demo stack on `127.0.0.1:18098`, installs the official
Plugin Check plugin, and fails unless Plugin Check reports `No errors found`.
Set `AGENTCART_PLUGIN_CHECK_KEEP_STACK=1` if you want to inspect the temporary
WordPress stack after the run.

For a separate prepared WordPress install, point the gate at the exact command
for that environment:

```sh
AGENTCART_WORDPRESS_PLUGIN_CHECK_COMMAND='wp plugin check agentcart-shopbridge --path=/path/to/wordpress' \
  AGENTCART_WORDPRESS_OFFICIAL_TOOLS_REQUIRED=1 \
  ./scripts/check-wordpress-official-gates.py
```

The package check verifies:

- ZIP exists and is under 10 MB;
- all files live under the expected plugin folder;
- plugin entry file, `readme.txt`, and `uninstall.php` exist;
- main plugin headers include WordPress/PHP requirements, WooCommerce
  dependency, GPL-compatible license, and text domain;
- readme stable tag matches plugin version;
- readme has 1 to 5 slug-like tags;
- readme documents external service calls;
- the ZIP does not include obvious development, platform, or secret-looking
  files.

The review-risk check verifies project-specific patterns that WordPress Plugin
Check or PHPCS would otherwise catch later:

- `$_POST` values are unslashed before sanitization;
- `$_SERVER` values are unslashed before use;
- custom admin POST actions have nonce fields and nonce checks;
- outbound HTTP calls cover the configured payment/refund verifier, opt-in
  hosted registry, this shop's public endpoint checks, and administrator-initiated
  pinned registry RPC reads; they use WordPress HTTP APIs, bounded responses,
  timeouts, response-code checks, and error handling;
- admin badge HTML escapes generated attributes and labels.
- public REST and `.well-known` discovery/registry endpoints are covered by the
  baseline rate limiter and return retry metadata.

These checks are not substitutes for WordPress Plugin Check, PHPCS, or manual
review. They are project-specific guards for this plugin and generated package;
the official-tool gate above is the bridge to strict WPCS/Plugin Check runs.

## External Service Disclosure

ShopBridge does not call external services on installation or for public
manifest/catalog/quote browsing. A merchant-configured payment verifier is called
during paid-order creation, verified refund recording, and scheduled retries of
interrupted checkout or manager-approved compensation. The hosted registry URL
defaults to empty; explicitly saved URLs and wp-config.php overrides remain
usable only through administrator-initiated bundle submission, revocation, or
health/monitor/onchain-event checks. Installs relying on the previous implicit
hosted default must explicitly save the desired URL after upgrading.

The built-in `https://rpc.moderato.tempo.xyz` destination is called only by
"Check registry health" with valid configured public onchain identity. It receives
standard read-only JSON-RPC parameters for chain/block/bytecode, public registry
contract/controller/record/hash, hostname hashing, and state reads. No key,
signature, buyer, order, or payment data is sent. Operator-managed v2 deployments
instead use configured primary and witness RPCs, including admission-state reads.
The packaged readme already provides Tempo terms/privacy links; terms/privacy
links for merchant-selected verifiers, hosted registries, and witness providers
are not supplied by the repository and must be reviewed by the operator.

The separate public endpoint check fetches this shop's own manifest, proof,
revocation, and bundle URLs. The plugin never contacts an x402 facilitator.
x402 v2 exact Base Sepolia USDC is offered for USD quotes only after the merchant
uses the nonce-protected "Check verifier capabilities" action. That authenticated
call sends only the operation and bearer token; its local snapshot has no TTL and
is invalidated when the verifier URL or x402 destination changes. Without confirmation
the rail reports `verifier_x402_support_unconfirmed`. No capability calls occur on
manifest/quote paths. Only the verifier contacts its operator-configured facilitator
and Base RPC; the plugin does not. x402 refunds remain unsupported_manual_only.
Checkout and refund entrypoints also reject caller-selected unavailable rails
before verifier calls or local acceptance; checkout binds all contract-hash
claims to the intact stored quote advertisement. Admin sandbox dry checkout
uses its quoted sandbox contract rather than bypassing these checks.

The WordPress.org readme needs to disclose this because the verifier can receive
quote, order/refund, payment receipt, merchant id, rail, destination, amount,
currency, quote hash, and idempotency/reference fields. The plugin cannot know
the verifier provider's terms or privacy policy because the merchant configures
that URL, so the readme must make that responsibility explicit.

The readme also needs to disclose the registry connection because it can receive
the generated registry record, record hash, manifest URL, registry bundle URL,
domain proof document, revocation document, public endpoint check result,
merchant id, shop domain, and idempotency key. The health check can receive the
merchant's IP/server request metadata and registry bearer token if private
monitor status is enabled.

## Submission Steps

1. Decide the permanent plugin name and slug.
2. Create or choose the official WordPress.org account that should own the
   plugin. Use an organization account/email if submitting as AgentCart.
3. Run the full local release check:

   ```sh
   ./scripts/verify.sh
   ```

4. Run strict WordPress official gates locally:

   ```sh
   cd woocommerce-shopbridge
   composer install
   cd ..
   ./scripts/check-wordpress-official-gates.py --strict
   ```

   Treat warnings about escaping, sanitization, nonces, HTTP calls, text
   domains, licensing, and external services as blockers.
5. Upload `dist/agentcart-shopbridge.zip` at the WordPress.org add-plugin page.
6. Watch the email address on the submitting account. Review is manual; respond
   in the existing review thread rather than resubmitting for ordinary fixes.
7. After approval, release through the WordPress.org SVN repository:
   - put plugin files directly in `trunk/`;
   - keep the root plugin file and `readme.txt` at trunk root;
   - copy releases to numeric version tags under `tags/`;
   - put banner/icon/screenshot assets in the SVN `assets/` directory.

## Before Public Listing

These items are still important before submitting for broad merchant use:

- add at least one screenshot for the settings/readiness page;
- verify the package on a clean WordPress + WooCommerce install with `WP_DEBUG`
  enabled;
- confirm the final public plugin name and slug;
- review trademark wording around WooCommerce and Stripe;
- decide where merchant-facing verifier terms/privacy examples live;
- add a stable support channel and security contact.
