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
- outbound HTTP calls are limited to the configured payment/refund verifier and
  hosted registry connection wrappers and use WordPress HTTP APIs, JSON headers,
  timeouts, response-code checks, and error handling;
- admin badge HTML escapes generated attributes and labels.

These checks are not substitutes for WordPress Plugin Check, PHPCS, or manual
review. They are project-specific guards for this plugin and generated package.

## External Service Disclosure

ShopBridge does not call external services for catalog or quote browsing. It
can call a merchant-configured payment verifier URL during paid-order creation
or verified refund recording. It can also call a merchant-configured hosted
registry connection URL when an admin explicitly submits a registry bundle or
revocation request from `WooCommerce -> AgentCart`.

The WordPress.org readme needs to disclose this because the verifier can receive
quote, order/refund, payment receipt, merchant id, rail, destination, amount,
currency, quote hash, and idempotency/reference fields. The plugin cannot know
the verifier provider's terms or privacy policy because the merchant configures
that URL, so the readme must make that responsibility explicit.

The readme also needs to disclose the registry connection because it can receive
the generated registry record, record hash, manifest URL, registry bundle URL,
domain proof document, revocation document, public endpoint check result,
merchant id, shop domain, and idempotency key.

## Submission Steps

1. Decide the permanent plugin name and slug.
2. Create or choose the official WordPress.org account that should own the
   plugin. Use an organization account/email if submitting as AgentCart.
3. Run the full local release check:

   ```sh
   ./scripts/verify.sh
   ```

4. Run WordPress Plugin Check and PHPCS/WordPress Coding Standards locally when
   added to the project. Treat warnings about escaping, sanitization, nonces,
   HTTP calls, text domains, licensing, and external services as blockers.
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

- run Plugin Check against the packaged plugin;
- add at least one screenshot for the settings/readiness page;
- verify the package on a clean WordPress + WooCommerce install with `WP_DEBUG`
  enabled;
- confirm the final public plugin name and slug;
- review trademark wording around WooCommerce and Stripe;
- decide where merchant-facing verifier terms/privacy examples live;
- add a stable support channel and security contact.
