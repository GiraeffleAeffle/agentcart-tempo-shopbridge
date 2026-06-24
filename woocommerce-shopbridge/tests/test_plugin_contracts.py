from __future__ import annotations

import pathlib
import re
import unittest


PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "agentcart-shopbridge" / "agentcart-shopbridge.php"
PLUGIN_DIR = PLUGIN.parent
SOURCE = PLUGIN.read_text()
README_TXT = PLUGIN_DIR / "readme.txt"
UNINSTALL = PLUGIN_DIR / "uninstall.php"


def function_body(name: str) -> str:
    match = re.search(rf"private static function {re.escape(name)}\([^)]*\) \{{", SOURCE)
    if not match:
        match = re.search(rf"public static function {re.escape(name)}\([^)]*\) \{{", SOURCE)
    if not match:
        raise AssertionError(f"function not found: {name}")
    start = match.end()
    depth = 1
    index = start
    while index < len(SOURCE) and depth:
        char = SOURCE[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth:
        raise AssertionError(f"function body not closed: {name}")
    return SOURCE[start:index - 1]


class ShopBridgePluginContractTests(unittest.TestCase):
    def test_wordpress_release_metadata_files_are_present(self) -> None:
        self.assertTrue(README_TXT.exists(), "WordPress plugin readme.txt is required for release packaging")
        self.assertTrue(UNINSTALL.exists(), "uninstall.php documents and enforces cleanup policy")

        readme = README_TXT.read_text()
        for field in [
            "Plugin Name: AgentCart ShopBridge",
            "Version: 0.1.0",
            "Requires at least: 6.4",
            "Requires PHP: 8.1",
            "Requires Plugins: woocommerce",
            "License: GPLv2 or later",
            "License URI: https://www.gnu.org/licenses/gpl-2.0.html",
            "Text Domain: agentcart-shopbridge",
        ]:
            self.assertIn(field, SOURCE)
        for field in [
            "=== AgentCart ShopBridge ===",
            "Requires at least:",
            "Requires PHP:",
            "Requires Plugins: woocommerce",
            "Stable tag: 0.1.0",
            "License:",
            "Tags: woocommerce, agents, checkout, machine-payments, mpp",
            "== External Services ==",
            "== Installation ==",
            "== Changelog ==",
        ]:
            self.assertIn(field, readme)
        self.assertIn("Payment verifier URL", readme)
        self.assertIn("AGENTCART_PAYMENT_VERIFIER_URL", readme)
        for endpoint in [
            "/.well-known/agentcart.json",
            "/.well-known/agentcart-registry-proof.json",
            "/.well-known/agentcart-registry-revocations.json",
            "/.well-known/agentcart-registry-bundle.json",
            "/wp-json/agentcart/v1/catalog",
            "/wp-json/agentcart/v1/quote",
            "/wp-json/agentcart/v1/orders",
            "/wp-json/agentcart/v1/orders/{id}/status",
            "/wp-json/agentcart/v1/orders/{id}/refunds",
            "/wp-json/agentcart/v1/orders/{id}/cancellations",
        ]:
            self.assertIn(endpoint, readme)

    def test_uninstall_cleanup_preserves_commerce_audit_metadata(self) -> None:
        uninstall = UNINSTALL.read_text()

        self.assertIn("WP_UNINSTALL_PLUGIN", uninstall)
        self.assertIn("agentcart_shopbridge_token", uninstall)
        self.assertIn("agentcart_shopbridge_stock_holds", uninstall)
        self.assertIn("agentcart_shopbridge_registry_public_check", uninstall)
        self.assertIn("agentcart_shopbridge_signed_request_mode", uninstall)
        self.assertIn("agentcart_shopbridge_signed_request_secret", uninstall)
        self.assertIn("agentcart_shopbridge_signed_nonce_", uninstall)
        self.assertIn("agentcart_shopbridge_x402_network", uninstall)
        self.assertIn("agentcart_shopbridge_x402_pay_to", uninstall)
        self.assertIn("agentcart_shopbridge_quote_", uninstall)
        self.assertIn("agentcart_shopbridge_rate_", uninstall)
        self.assertIn("preserves WooCommerce order, refund, cancellation, payment", uninstall)
        for preserved_meta in [
            "_agentcart_order_id",
            "_agentcart_payment_verification",
            "_agentcart_refunds",
            "_agentcart_cancellations",
            "_agentcart_enabled",
            "_agentcart_checkout_blocked",
        ]:
            self.assertNotIn(preserved_meta, uninstall)

    def test_refund_endpoint_requires_idempotency_key(self) -> None:
        body = function_body("create_refund")

        self.assertIn("refund_idempotency_key", body)
        self.assertIn("agentcart_refund_idempotency_key_required", body)
        self.assertIn("find_existing_refund", body)
        self.assertIn("validate_existing_refund_replay", body)
        self.assertIn("acquire_refund_lock", body)

    def test_refund_amount_above_remaining_is_rejected_not_clamped(self) -> None:
        body = function_body("create_refund")

        self.assertIn("agentcart_refund_amount_exceeds_remaining", body)
        self.assertNotIn("min($amount_cents, $remaining_cents)", body)

    def test_refund_idempotency_key_is_persisted_on_refund_record(self) -> None:
        body = function_body("create_refund")

        self.assertIn("REFUND_IDEMPOTENCY_KEY_META", SOURCE)
        self.assertIn("$refund->update_meta_data(self::REFUND_IDEMPOTENCY_KEY_META, $refund_idempotency_key)", body)

    def test_external_refund_reference_is_replay_checked_before_refund_record_creation(self) -> None:
        body = function_body("create_refund")

        self.assertIn("refund_reference_used", body)
        self.assertIn("agentcart_refund_replay", body)
        self.assertLess(
            body.index("refund_reference_used"),
            body.index("wc_create_refund"),
        )

    def test_external_payment_references_are_replay_checked_before_paid_order_creation(self) -> None:
        body = function_body("call_payment_verifier")

        self.assertIn("_agentcart_payment_transaction_reference", body)
        self.assertIn("agentcart_payment_replay", body)
        self.assertLess(
            body.index("_agentcart_payment_transaction_reference"),
            body.index("return ["),
        )

    def test_checkout_consumes_merchant_quote_under_quote_lock(self) -> None:
        self.assertIn("QUOTE_LOCK_PREFIX", SOURCE)

        order_body = function_body("create_order")
        self.assertIn("acquire_quote_lock", order_body)
        self.assertIn("release_quote_lock", order_body)
        self.assertIn("find_existing_quote_order", order_body)
        self.assertIn("agentcart_quote_already_consumed", order_body)
        self.assertLess(order_body.index("acquire_quote_lock"), order_body.index("get_transient"))
        self.assertLess(order_body.index("acquire_quote_lock"), order_body.index("verify_payment_receipt"))
        self.assertLess(order_body.index("acquire_quote_lock"), order_body.index("wc_create_order"))
        self.assertLess(order_body.index("delete_transient"), order_body.index("release_quote_lock"))

    def test_merchant_quote_id_is_stored_from_normalized_request_value(self) -> None:
        order_body = function_body("create_order")
        quote_lookup_body = function_body("find_existing_quote_order")

        self.assertIn("merchant_quote_id_from_body", order_body)
        self.assertIn("update_meta_data('_agentcart_merchant_quote_id', $merchant_quote_id)", order_body)
        self.assertIn("'meta_key' => '_agentcart_merchant_quote_id'", quote_lookup_body)
        self.assertIn("'meta_value' => $merchant_quote_id", quote_lookup_body)

    def test_public_endpoints_are_rate_limited(self) -> None:
        self.assertIn("RATE_LIMIT_TRANSIENT_PREFIX", SOURCE)
        self.assertIn("RATE_LIMIT_WINDOW_SECONDS", SOURCE)

        public_body = function_body("authorize_public_read")
        checkout_body = function_body("authorize_checkout")
        status_body = function_body("authorize_order_status")
        refund_body = function_body("authorize_refund")
        cancellation_body = function_body("authorize_cancellation")
        well_known_body = function_body("maybe_serve_well_known_manifest")

        self.assertIn("enforce_rate_limit", public_body)
        self.assertIn("enforce_well_known_rate_limit($path)", well_known_body)
        self.assertIn("enforce_rate_limit($request, 'checkout')", checkout_body)
        self.assertIn("enforce_rate_limit($request, 'order_status')", status_body)
        self.assertIn("enforce_rate_limit($request, 'refund')", refund_body)
        self.assertIn("enforce_rate_limit($request, 'cancellation')", cancellation_body)
        self.assertLess(checkout_body.index("enforce_rate_limit"), checkout_body.index("has_valid_merchant_token"))
        self.assertLess(status_body.index("enforce_rate_limit"), status_body.index("wc_get_order"))
        self.assertLess(refund_body.index("enforce_rate_limit"), refund_body.index("has_valid_merchant_token"))
        self.assertLess(cancellation_body.index("enforce_rate_limit"), cancellation_body.index("has_valid_merchant_token"))

    def test_checkout_mode_can_require_external_verifier_before_token_fallback(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        checkout_body = function_body("authorize_checkout")
        payment_body = function_body("verify_payment_receipt")
        readiness_body = function_body("readiness")
        guide_body = function_body("setup_guide")
        capability_body = function_body("capability_document")
        quote_hash_body = function_body("quote_hash_payload")
        requirements_body = function_body("payment_requirements")
        uninstall = UNINSTALL.read_text()

        for symbol in [
            "CHECKOUT_MODE_OPTION",
            "AGENTCART_CHECKOUT_MODE",
            "external_verifier_only",
            "trusted_token_or_verifier",
        ]:
            self.assertIn(symbol, SOURCE)
        self.assertIn("sanitize_checkout_mode_setting", settings_body)
        self.assertIn("render_checkout_mode_setting_row", render_body)
        self.assertIn("agentcart_shopbridge_checkout_mode", uninstall)
        self.assertIn("external_verifier_required_for_checkout", checkout_body)
        self.assertLess(checkout_body.index("external_verifier_required_for_checkout"), checkout_body.index("has_valid_merchant_token"))
        self.assertIn("agentcart_payment_verifier_required", checkout_body)
        self.assertIn("external_verifier_required_for_checkout", payment_body)
        self.assertLess(payment_body.index("external_verifier_required_for_checkout"), payment_body.index("has_valid_merchant_token"))
        self.assertIn("external-verifier-only checkout mode", readiness_body)
        self.assertIn("external_verifier_required_for_checkout", guide_body)
        self.assertIn("'checkout_mode'", capability_body + quote_hash_body + requirements_body)
        self.assertIn("'trusted_token_checkout_enabled'", capability_body + requirements_body)
        self.assertIn("'external_verifier_required_for_checkout'", capability_body + quote_hash_body + requirements_body)

    def test_stable_merchant_id_is_admin_configurable(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        sanitizer_body = function_body("sanitize_merchant_id_setting")
        readiness_body = function_body("stable_merchant_id_configured")
        merchant_body = function_body("merchant")
        merchant_id_body = function_body("merchant_id")
        uninstall = UNINSTALL.read_text()

        self.assertIn("MERCHANT_ID_OPTION", SOURCE)
        self.assertIn("agentcart_shopbridge_merchant_id", uninstall)
        self.assertIn("sanitize_merchant_id_setting", settings_body)
        self.assertIn("AGENTCART_MERCHANT_ID", render_body)
        self.assertIn("Merchant id", render_body)
        self.assertIn("/[^a-z0-9._-]+/", sanitizer_body)
        self.assertIn("substr($value, 0, 96)", sanitizer_body)
        self.assertIn("self::merchant_id()", readiness_body)
        self.assertNotIn("!defined('AGENTCART_MERCHANT_ID')", readiness_body)
        self.assertIn("'id' => self::merchant_id()", merchant_body)
        self.assertIn("AGENTCART_MERCHANT_ID", merchant_id_body)
        self.assertIn("get_option(self::MERCHANT_ID_OPTION", merchant_id_body)
        self.assertIn("'woocommerce-demo-shop'", merchant_id_body)

    def test_admin_credential_actions_rotate_local_tokens(self) -> None:
        render_body = function_body("render_settings_page")
        action_body = function_body("maybe_handle_credential_action")
        forms_body = function_body("render_credential_action_forms")
        setting_row_body = function_body("render_setting_row")

        self.assertIn("maybe_handle_credential_action", render_body)
        self.assertIn("render_credential_action_forms", render_body)
        self.assertIn('id="agentcart-credentials"', SOURCE)
        self.assertIn("agentcart_credential_action", action_body + forms_body)
        self.assertIn("agentcart_shopbridge_credential_action", action_body + forms_body)
        self.assertIn("rotate_merchant_token", action_body + forms_body)
        self.assertIn("rotate_payment_verifier_token", action_body + forms_body)
        self.assertIn("AGENTCART_SHOPBRIDGE_TOKEN", action_body + forms_body)
        self.assertIn("AGENTCART_PAYMENT_VERIFIER_TOKEN", action_body + forms_body)
        self.assertIn("update_option(self::TOKEN_OPTION, wp_generate_password(48, false, false), false)", action_body)
        self.assertIn(
            "update_option(self::PAYMENT_VERIFIER_TOKEN_OPTION, wp_generate_password(48, false, false), false)",
            action_body,
        )
        self.assertIn("Managed in wp-config.php", forms_body)
        self.assertIn("input.type === 'password' ? 'text' : 'password'", setting_row_body)
        self.assertIn("esc_js($option)", setting_row_body)

    def test_admin_quick_start_prepares_sandbox_access_without_exposing_products(self) -> None:
        render_body = function_body("render_settings_page")
        action_body = function_body("maybe_handle_setup_action")
        defaults_body = function_body("prepare_sandbox_defaults")
        panel_body = function_body("render_setup_wizard_panel")
        review_guard = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-wordpress-plugin-review.py").read_text()

        self.assertIn("maybe_handle_setup_action", render_body)
        self.assertIn("render_setup_wizard_panel", render_body)
        self.assertIn("agentcart_setup_action", action_body + panel_body)
        self.assertIn("agentcart_shopbridge_setup_action", action_body + panel_body)
        self.assertIn("check_admin_referer('agentcart_shopbridge_setup_action')", action_body)
        self.assertIn("prepare_sandbox_secrets", action_body + panel_body)
        self.assertIn("prepare_sandbox_defaults", action_body)
        self.assertIn("update_option(self::TOKEN_OPTION, wp_generate_password(48, false, false), false)", defaults_body)
        self.assertIn("update_option(self::SIGNED_REQUEST_SECRET_OPTION, wp_generate_password(64, false, false), false)", defaults_body)
        self.assertIn("update_option(self::SIGNED_REQUEST_MODE_OPTION, 'allow', false)", defaults_body)
        self.assertIn("update_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION", defaults_body)
        self.assertIn("update_option(self::REGISTRY_UPDATED_AT_OPTION", defaults_body)
        self.assertIn("delete_option(self::REGISTRY_PUBLIC_CHECK_OPTION)", defaults_body)
        self.assertIn("This does not expose products or configure", panel_body)
        self.assertNotIn("set_agentcart_exposure_for_published_simple_products", defaults_body)
        self.assertIn("agentcart_shopbridge_setup_action", review_guard)

    def test_admin_sandbox_quote_check_uses_quote_path_and_cleans_up(self) -> None:
        render_body = function_body("render_settings_page")
        action_body = function_body("maybe_handle_setup_action")
        check_body = function_body("run_sandbox_quote_check")
        product_body = function_body("sandbox_quote_test_product")
        panel_body = function_body("render_setup_wizard_panel")
        result_body = function_body("sandbox_quote_check_result")
        uninstall = UNINSTALL.read_text()

        self.assertIn("SANDBOX_QUOTE_CHECK_OPTION", SOURCE)
        self.assertIn("agentcart_shopbridge_sandbox_quote_check", uninstall)
        self.assertIn("maybe_handle_setup_action", render_body)
        self.assertIn("run_sandbox_quote_check", action_body + panel_body)
        self.assertIn("update_option(self::SANDBOX_QUOTE_CHECK_OPTION, $result, false)", action_body)
        self.assertIn("get_option(self::SANDBOX_QUOTE_CHECK_OPTION", result_body)
        self.assertIn("Run quote check", panel_body)
        self.assertIn("Last quote check", panel_body)
        self.assertIn("Quote hash", panel_body)
        self.assertIn("new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/quote')", check_body)
        self.assertIn("self::quote($request)", check_body)
        self.assertIn("delete_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id)", check_body)
        self.assertIn("self::release_stock_hold($quote_id)", check_body)
        self.assertIn("'cleanup' => 'quote transient deleted and soft stock hold released'", check_body)
        self.assertIn("sandbox_quote_test_product", check_body)
        self.assertIn("sandbox_quote_ship_to", check_body)
        self.assertIn("product_ships_to_country", product_body)
        self.assertIn("validate_product_stock_for_agentcart", product_body)
        self.assertNotIn("create_order", check_body)
        self.assertNotIn("set_agentcart_exposure_for_published_simple_products", check_body)

    def test_rate_limiter_has_endpoint_policies_and_retry_metadata(self) -> None:
        policy_body = function_body("rate_limit_policy")
        limiter_body = function_body("enforce_rate_limit")
        client_limiter_body = function_body("enforce_rate_limit_for_client")
        error_body = function_body("rate_limit_error")
        key_body = function_body("rate_limit_client_key")
        server_key_body = function_body("rate_limit_client_key_from_server")
        well_known_bucket_body = function_body("well_known_rate_limit_bucket_for_path")
        capability_body = function_body("capability_document")

        for bucket in ["'catalog'", "'registry'", "'quote'", "'checkout'", "'order_status'", "'refund'", "'cancellation'"]:
            self.assertIn(bucket, policy_body)
        self.assertIn("enforce_rate_limit_for_client", limiter_body)
        self.assertIn("agentcart_rate_limited", error_body)
        self.assertIn("'retry_after_seconds'", error_body)
        self.assertIn("'reset_at'", error_body)
        self.assertIn("set_transient", client_limiter_body)
        self.assertIn("rate_limit_client_key_from_server", key_body)
        self.assertIn("REMOTE_ADDR", server_key_body)
        self.assertIn("HTTP_USER_AGENT", server_key_body)
        self.assertNotIn("x-forwarded-for", server_key_body)
        self.assertIn("/.well-known/agentcart.json", well_known_bucket_body)
        self.assertIn("'registry'", well_known_bucket_body)
        self.assertIn("'endpoint_rate_limits'", capability_body)
        self.assertIn("'rate_limits'", capability_body)

    def test_product_exposure_modes_are_supported(self) -> None:
        self.assertIn("PRODUCT_EXPOSURE_MODE_OPTION", SOURCE)
        self.assertIn("PRODUCT_EXPOSURE_TAG_OPTION", SOURCE)
        self.assertIn("PRODUCT_EXPOSURE_CATEGORIES_OPTION", SOURCE)
        self.assertIn("PRODUCT_BLOCKED_CATEGORIES_OPTION", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_EXPOSURE_MODE", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_EXPOSURE_TAG", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_EXPOSURE_CATEGORIES", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_BLOCKED_CATEGORIES", SOURCE)

        mode_body = function_body("sanitize_product_exposure_mode_setting")
        self.assertIn("'manual'", mode_body)
        self.assertIn("'tag'", mode_body)
        self.assertIn("'category'", mode_body)
        self.assertIn("'all'", mode_body)
        self.assertIn("sanitize_slug_list_setting", SOURCE)

    def test_product_exposure_query_supports_manual_tag_and_all_modes(self) -> None:
        query_body = function_body("agentcart_product_query_args")
        eligibility_body = function_body("is_product_agentcart_enabled")
        capability_body = function_body("capability_document")

        self.assertIn("agentcart_enabled_meta_query", query_body)
        self.assertIn("product_exposure_tag", query_body)
        self.assertIn("'tag'", query_body)
        self.assertIn("product_exposure_categories", query_body)
        self.assertIn("'category'", query_body)
        self.assertIn("'all'", eligibility_body)
        self.assertIn("has_term", eligibility_body)
        self.assertIn("product_has_category_slug", eligibility_body)
        self.assertIn("PRODUCT_ENABLED_META", eligibility_body)
        self.assertIn("'product_exposure'", capability_body)
        self.assertIn("'tag_based_product_exposure'", capability_body)
        self.assertIn("'category_based_product_exposure'", capability_body)
        self.assertIn("'all_published_simple_product_exposure'", capability_body)
        self.assertIn("'blocked_category_product_exclusion'", capability_body)

    def test_admin_setup_guide_is_rendered_and_exposed_publicly(self) -> None:
        render_body = function_body("render_settings_page")
        guide_body = function_body("setup_guide")
        step_body = function_body("setup_guide_step")
        capability_body = function_body("capability_document")

        self.assertIn("render_setup_guide", render_body)
        self.assertIn("render_setup_wizard_panel", render_body)
        self.assertIn("'setup_guide'", capability_body)
        for step_id in [
            "'merchant_identity'",
            "'products'",
            "'tax_shipping'",
            "'payment_verifier'",
            "'registry'",
            "'sandbox_test'",
        ]:
            self.assertIn(step_id, guide_body)
        self.assertIn("'next_step'", guide_body)
        self.assertIn("'demo_complete'", guide_body)
        self.assertIn("'production_complete'", guide_body)
        self.assertIn("'settings_anchor'", step_body)
        self.assertIn("#agentcart-settings", SOURCE)
        self.assertIn("#agentcart-product-exposure", SOURCE)
        self.assertNotIn("admin_url(", guide_body)

    def test_registry_revocation_endpoint_is_auto_published_and_bound(self) -> None:
        well_known_body = function_body("maybe_serve_well_known_manifest")
        proof_body = function_body("registry_domain_proof")
        revocations_body = function_body("registry_revocations")
        claim_body = function_body("registry_claim")
        capability_body = function_body("capability_document")
        signature_payload_body = function_body("registry_signature_payload")

        self.assertIn("agentcart-registry-revocations.json", well_known_body)
        self.assertIn("registry_revocation_url", proof_body)
        self.assertIn("$revocations = self::registry_revoked_records()", revocations_body)
        self.assertIn("'revocations' => $revocations", revocations_body)
        self.assertIn("'revocation_url' => self::registry_revocation_url()", claim_body)
        self.assertIn("'registry_revocations' => self::registry_revocation_url()", capability_body)
        self.assertIn("'revocation_url' => self::registry_revocation_url()", capability_body)
        self.assertIn("'revocation_snapshot'", signature_payload_body)

    def test_registry_onboarding_bundle_is_auto_published(self) -> None:
        well_known_body = function_body("maybe_serve_well_known_manifest")
        render_body = function_body("render_settings_page")
        bundle_body = function_body("registry_onboarding_bundle")
        capability_body = function_body("capability_document")

        self.assertIn("agentcart-registry-bundle.json", well_known_body)
        self.assertIn("registry_bundle_url", render_body)
        self.assertIn("'type' => 'agentcart-registry-onboarding-bundle'", bundle_body)
        self.assertIn("'registry_record' => $record", bundle_body)
        self.assertIn("'record_hash' => self::registry_record_hash($record)", bundle_body)
        self.assertIn("'proof_document_expected' => self::registry_domain_proof()", bundle_body)
        self.assertIn("'registry_feed'", bundle_body)
        self.assertIn("'entries' => [$record]", bundle_body)
        self.assertIn("'merchant_action' => 'none'", bundle_body)
        self.assertIn("'registry_bundle' => self::registry_bundle_url()", capability_body)
        self.assertIn("'registry_bundle_url' => self::registry_bundle_url()", capability_body)
        self.assertIn("'registry_onboarding_bundle' => self::registry_onboarding_bundle()", capability_body)

    def test_registry_transparency_actions_refresh_and_check_public_endpoints(self) -> None:
        render_body = function_body("render_settings_page")
        action_body = function_body("maybe_handle_registry_action")
        panel_body = function_body("render_registry_transparency_panel")
        check_body = function_body("run_registry_public_check")
        fetch_body = function_body("fetch_public_json")
        capability_body = function_body("capability_document")
        review_guard = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-wordpress-plugin-review.py").read_text()

        self.assertIn("REGISTRY_PUBLIC_CHECK_OPTION", SOURCE)
        self.assertIn("maybe_handle_registry_action", render_body)
        self.assertIn("render_registry_transparency_panel", render_body)
        self.assertIn("agentcart_registry_action", action_body + panel_body)
        self.assertIn("agentcart_shopbridge_registry_action", action_body + panel_body)
        self.assertIn("check_admin_referer('agentcart_shopbridge_registry_action')", action_body)
        self.assertIn("refresh_registry_metadata", action_body + panel_body)
        self.assertIn("check_public_registry_endpoints", action_body + panel_body)
        self.assertIn("update_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION", action_body)
        self.assertIn("update_option(self::REGISTRY_PUBLIC_CHECK_OPTION, $result, false)", action_body)
        self.assertIn("wp_remote_get", fetch_body)
        self.assertIn("manifest_registry_claim_hash_mismatch", check_body)
        self.assertIn("'record_hash' => $record_hash", check_body)
        self.assertIn("'domain_proof_' . $field . '_mismatch'", check_body)
        self.assertIn("current_record_revoked", check_body)
        self.assertIn("'registry_public_check' => self::registry_public_check_result()", capability_body)
        self.assertIn("agentcart_shopbridge_registry_action", review_guard)

    def test_registry_connection_can_submit_and_revoke_hosted_records(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        action_body = function_body("maybe_handle_registry_action")
        panel_body = function_body("render_registry_transparency_panel")
        submit_body = function_body("submit_registry_connection")
        payload_body = function_body("registry_connection_payload")
        call_body = function_body("call_registry_connection")
        revocations_body = function_body("registry_revocations")
        records_body = function_body("record_registry_revocation")
        stored_body = function_body("registry_revoked_records")
        review_guard = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-wordpress-plugin-review.py").read_text()
        uninstall = UNINSTALL.read_text()

        for symbol in [
            "REGISTRY_CONNECTION_URL_OPTION",
            "REGISTRY_CONNECTION_TOKEN_OPTION",
            "REGISTRY_CONNECTION_STATUS_OPTION",
            "REGISTRY_REVOKED_RECORDS_OPTION",
            "AGENTCART_REGISTRY_CONNECTION_URL",
            "AGENTCART_REGISTRY_CONNECTION_TOKEN",
        ]:
            self.assertIn(symbol, SOURCE)
        for option in [
            "agentcart_shopbridge_registry_connection_url",
            "agentcart_shopbridge_registry_connection_token",
            "agentcart_shopbridge_registry_connection_status",
            "agentcart_shopbridge_registry_revoked_records",
        ]:
            self.assertIn(option, uninstall)
        self.assertIn("REGISTRY_CONNECTION_URL_OPTION", settings_body)
        self.assertIn("REGISTRY_CONNECTION_TOKEN_OPTION", settings_body)
        self.assertIn("Registry connection URL", render_body)
        self.assertIn("Registry connection token", render_body)
        self.assertIn("registry_connection_status", render_body + panel_body)
        self.assertIn("submit_registry_bundle", action_body + panel_body)
        self.assertIn("revoke_registry_record", action_body + panel_body)
        self.assertIn("submit_registry_connection('upsert')", action_body)
        self.assertIn("submit_registry_connection('revoke')", action_body)
        self.assertIn("update_option(self::REGISTRY_CONNECTION_STATUS_OPTION, $result, false)", action_body)
        self.assertIn("record_registry_revocation", action_body)
        self.assertIn("wp_nonce_field('agentcart_shopbridge_registry_action')", panel_body)
        self.assertIn("registry_onboarding_bundle", payload_body)
        self.assertIn("'schema' => 'agentcart.shopbridge.registry_connection_request.v1'", payload_body)
        self.assertIn("'idempotency_key' => hash('sha256'", payload_body)
        self.assertIn("registry_connection_url", submit_body)
        self.assertIn("call_registry_connection", submit_body)
        self.assertIn("wp_remote_post($registry_url", call_body)
        self.assertIn("'X-AgentCart-Registry-Operation'", call_body)
        self.assertIn("$headers['Authorization'] = 'Bearer ' . $token", call_body)
        self.assertIn("wp_json_encode($payload", call_body)
        self.assertIn("'redirection' => 0", call_body)
        self.assertIn("wp_remote_retrieve_response_code($response)", call_body)
        self.assertIn("json_decode($raw_body, true)", call_body)
        self.assertIn("self::registry_revoked_records()", revocations_body)
        self.assertIn("'revocations' => $revocations", revocations_body)
        self.assertIn("update_option(self::REGISTRY_REVOKED_RECORDS_OPTION, $records, false)", records_body)
        self.assertIn("delete_option(self::REGISTRY_PUBLIC_CHECK_OPTION)", records_body)
        self.assertIn("'revoked' => true", stored_body + records_body)
        self.assertIn("call_registry_connection", review_guard)

    def test_manifest_protocol_profiles_are_configured_only_and_registry_bound(self) -> None:
        capability_body = function_body("capability_document")
        profiles_body = function_body("protocol_profiles")
        claim_body = function_body("registry_claim")
        requirements_body = function_body("payment_requirements")
        registry_tool = (pathlib.Path(__file__).resolve().parents[2] / "gateway" / "scripts" / "registry_record.py").read_text()
        smoke = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "woocommerce-shopbridge-smoke.py").read_text()

        self.assertIn("'protocol_profiles' => self::protocol_profiles()", capability_body)
        self.assertIn("'protocol_profile_ids' => self::protocol_profile_ids()", capability_body)
        self.assertIn("'protocol_profile_ids' => self::protocol_profile_ids()", claim_body)
        self.assertIn("'payment_protocol_profile_ids' => self::payment_protocol_profile_ids()", requirements_body)
        self.assertIn("'id' => 'agentcart-shopbridge'", profiles_body)
        self.assertIn("'id' => 'mpp-http-auth'", profiles_body)
        self.assertIn("'id' => 'stripe-card-mpp'", profiles_body)
        self.assertIn("'id' => 'erc8004-ready'", profiles_body)
        self.assertIn("if (self::tempo_payment_profile_configured())", profiles_body)
        self.assertIn("if (self::stripe_payment_profile_configured())", profiles_body)
        self.assertIn("if (self::merchant_registry_profile_configured())", profiles_body)
        self.assertIn("'id' => 'x402-compatible'", profiles_body)
        self.assertIn("if (self::x402_profile_configured())", profiles_body)
        self.assertIn("'payment_required_header' => 'PAYMENT-REQUIRED'", profiles_body)
        self.assertIn("'id' => 'signed-http-ready'", profiles_body)
        self.assertIn("if (self::signed_request_profile_configured())", profiles_body)
        self.assertIn("protocol_profiles(manifest)", registry_tool)
        self.assertIn("validate_protocol_profiles", smoke)

    def test_x402_payment_required_shim_is_quote_bound_and_verifier_checked(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        create_order_body = function_body("create_order")
        receipt_body = function_body("payment_receipt_from_checkout_request")
        response_body = function_body("x402_payment_required_response")
        requirements_body = function_body("payment_requirements")
        document_body = function_body("x402_payment_required_document")
        verifier_body = function_body("call_payment_verifier")
        rail_body = function_body("normalize_payment_rail")

        for symbol in [
            "X402_NETWORK_OPTION",
            "X402_ASSET_OPTION",
            "X402_ASSET_DECIMALS_OPTION",
            "X402_PAY_TO_OPTION",
            "X402_MAX_TIMEOUT_SECONDS_OPTION",
            "AGENTCART_X402_NETWORK",
            "AGENTCART_X402_ASSET",
            "AGENTCART_X402_PAY_TO",
        ]:
            self.assertIn(symbol, SOURCE)
        self.assertIn("sanitize_x402_asset_decimals_setting", settings_body)
        self.assertIn("sanitize_x402_timeout_setting", settings_body)
        self.assertIn("x402 network", render_body)
        self.assertIn("x402 payTo address", render_body)
        self.assertIn("x402_payment_required_response", create_order_body)
        self.assertLess(create_order_body.index("$receipt = isset($body['payment_receipt']"), create_order_body.index("find_existing_checkout_order"))
        self.assertLess(create_order_body.index("get_transient"), create_order_body.index("payment_receipt_from_checkout_request"))
        self.assertIn("PAYMENT-SIGNATURE", receipt_body + response_body + requirements_body)
        self.assertIn("PAYMENT-REQUIRED", response_body + requirements_body)
        self.assertIn("WP_REST_Response", response_body)
        self.assertIn("'x402Version' => 2", document_body)
        self.assertIn("'maxAmountRequired' => self::x402_atomic_amount", document_body)
        self.assertIn("'quoteHash' => $quote_hash", document_body)
        self.assertIn("'merchantQuoteId' => $quote_id", document_body)
        self.assertIn("'x402-compatible'", rail_body + requirements_body)
        self.assertIn("'x402_max_amount_required' => self::x402_atomic_amount", verifier_body)
        self.assertIn("agentcart_payment_x402_amount_mismatch", verifier_body)
        self.assertIn("agentcart_payment_x402_pay_to_mismatch", verifier_body)

    def test_signed_http_request_gate_is_configured_only_and_replay_protected(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        profiles_body = function_body("protocol_profiles")
        auth_body = function_body("enforce_signed_request_policy")
        verifier_body = function_body("verify_signed_request")
        quote_hash_body = function_body("quote_hash_payload")
        requirements_body = function_body("payment_requirements")
        readiness_body = function_body("readiness")
        checkout_body = function_body("authorize_checkout")
        status_body = function_body("authorize_order_status")
        refund_body = function_body("authorize_refund")
        cancellation_body = function_body("authorize_cancellation")

        for symbol in [
            "SIGNED_REQUEST_MODE_OPTION",
            "SIGNED_REQUEST_SECRET_OPTION",
            "SIGNED_REQUEST_NONCE_PREFIX",
            "AGENTCART_SIGNED_REQUEST_MODE",
            "AGENTCART_SIGNED_REQUEST_SECRET",
        ]:
            self.assertIn(symbol, SOURCE)
        self.assertIn("sanitize_signed_request_mode_setting", settings_body)
        self.assertIn("render_signed_request_mode_setting_row", render_body)
        self.assertIn("Signed request secret", render_body)
        self.assertIn("'id' => 'signed-http-ready'", profiles_body)
        self.assertIn("if (self::signed_request_profile_configured())", profiles_body)
        self.assertIn("'signature_scheme' => 'agentcart-hmac-sha256-v1'", profiles_body + requirements_body)
        for error in [
            "agentcart_signed_request_missing_method",
            "agentcart_signed_request_missing_path",
            "agentcart_signed_request_missing_digest",
            "agentcart_signed_request_missing_nonce",
            "agentcart_signed_request_missing_expiry",
            "agentcart_signed_request_signature_mismatch",
            "agentcart_signed_request_replay",
        ]:
            self.assertIn(error, verifier_body)
        self.assertIn("hash_hmac('sha256'", verifier_body)
        self.assertIn("get_transient($nonce_key)", verifier_body)
        self.assertIn("set_transient($nonce_key", verifier_body)
        self.assertIn("signed_request_required_for_bucket", auth_body + readiness_body)
        self.assertIn("signed_request_required_for", quote_hash_body + requirements_body)
        self.assertIn("enforce_signed_request_policy($request, 'checkout')", checkout_body)
        self.assertIn("enforce_signed_request_policy($request, 'order_status')", status_body)
        self.assertIn("enforce_signed_request_policy($request, 'refund')", refund_body)
        self.assertIn("enforce_signed_request_policy($request, 'cancellation')", cancellation_body)
        self.assertIn("signed_request_verified($request)", status_body + refund_body + cancellation_body)

    def test_product_safety_controls_are_exposed_and_enforced(self) -> None:
        self.assertIn("PRODUCT_BLOCKED_META", SOURCE)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", SOURCE)
        self.assertIn("PRODUCT_SHIPPING_COUNTRIES_META", SOURCE)
        self.assertIn("PRODUCT_PERISHABLE_META", SOURCE)
        self.assertIn("PRODUCT_DEPOSIT_META", SOURCE)
        self.assertIn("PRODUCT_FINAL_SALE_META", SOURCE)
        self.assertIn("PRODUCT_SUBSTITUTION_SENSITIVE_META", SOURCE)

        product_options_body = function_body("render_product_agentcart_options")
        self.assertIn("Exclude from AgentCart checkout", product_options_body)
        self.assertIn("AgentCart max quantity", product_options_body)
        self.assertIn("AgentCart shipping countries", product_options_body)
        self.assertIn("AgentCart perishable item", product_options_body)
        self.assertIn("AgentCart deposit possible", product_options_body)
        self.assertIn("AgentCart final sale / non-returnable", product_options_body)
        self.assertIn("AgentCart substitution-sensitive", product_options_body)

        save_body = function_body("save_product_agentcart_options")
        self.assertIn("PRODUCT_BLOCKED_META", save_body)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", save_body)
        self.assertIn("PRODUCT_SHIPPING_COUNTRIES_META", save_body)
        self.assertIn("PRODUCT_PERISHABLE_META", save_body)
        self.assertIn("PRODUCT_DEPOSIT_META", save_body)
        self.assertIn("PRODUCT_FINAL_SALE_META", save_body)
        self.assertIn("PRODUCT_SUBSTITUTION_SENSITIVE_META", save_body)
        self.assertIn("sanitize_country_list_setting", save_body)

        product_body = function_body("serialize_product")
        self.assertIn("'max_quantity'", product_body)
        self.assertIn("'agentcart_policy'", product_body)
        self.assertIn("is_product_agentcart_blocked", product_body)
        self.assertIn("'blocked_category_slugs'", product_body)

        capability_body = function_body("capability_document")
        self.assertIn("'per_product_agentcart_max_quantity'", capability_body)
        self.assertIn("'per_product_agentcart_block_override'", capability_body)
        self.assertIn("'per_product_shipping_country_overrides'", capability_body)
        self.assertIn("'per_product_aftercare_policy_overrides'", capability_body)
        self.assertIn("'product_policy'", capability_body)
        self.assertIn("'blocked_categories_absent_from_catalog'", capability_body)

    def test_catalog_exposes_structured_package_size_from_woo_weight(self) -> None:
        product_body = function_body("serialize_product")
        package_body = function_body("package_size_for_product")

        self.assertIn("package_size_for_product", product_body)
        self.assertIn("'package_size'", product_body)
        self.assertIn("'normalized_quantity'", package_body)
        self.assertIn("'normalized_unit'", package_body)
        self.assertIn("woocommerce_weight_unit", package_body)
        self.assertIn("normalize_package_quantity", package_body)

    def test_catalog_exposes_structured_tags_and_allergens_from_woo_metadata(self) -> None:
        product_body = function_body("serialize_product")
        labels_body = function_body("product_agent_labels")
        tags_body = function_body("product_tag_values")
        attributes_body = function_body("product_attribute_values")

        self.assertIn("product_agent_labels", product_body)
        for field in ["'tags'", "'labels'", "'dietary_tags'", "'allergens'"]:
            self.assertIn(field, product_body)
        self.assertIn("product_tag_values", labels_body)
        self.assertIn("product_attribute_values", labels_body)
        self.assertIn("known_dietary_labels", labels_body)
        self.assertIn("known_allergen_labels", labels_body)
        self.assertIn("wp_get_post_terms", tags_body)
        self.assertIn("get_attributes", attributes_body)

    def test_catalog_and_quote_expose_restricted_goods_policy_metadata(self) -> None:
        product_body = function_body("serialize_product")
        restricted_body = function_body("product_restricted_goods")
        rules_body = function_body("restricted_goods_rules")
        quote_cart_body = function_body("quote_from_cart")

        self.assertIn("product_restricted_goods", product_body)
        for field in ["'restricted_goods'", "'requires_human_review'", "'agent_should_not_autonomously_purchase'"]:
            self.assertIn(field, product_body + restricted_body)
        for code in ["'age_restricted'", "'medical'", "'weapons'", "'stored_value'"]:
            self.assertIn(code, rules_body)
        self.assertIn("product_category_slugs", restricted_body)
        self.assertIn("'category_slugs'", product_body)
        self.assertIn("'restricted_goods'", quote_cart_body)
        self.assertIn("'agentcart_policy'", quote_cart_body)

    def test_catalog_quote_order_and_refunds_expose_commerce_policy_metadata(self) -> None:
        product_body = function_body("serialize_product")
        policy_body = function_body("product_commerce_policy")
        overrides_body = function_body("product_aftercare_override_flags")
        flag_body = function_body("commerce_policy_flag")
        upsert_body = function_body("upsert_commerce_policy_flag")
        rules_body = function_body("commerce_policy_rules")
        quote_cart_body = function_body("quote_from_cart")
        order_body = function_body("create_order")
        order_response_body = function_body("serialize_order_response")
        order_status_body = function_body("serialize_order_status")
        order_items_body = function_body("serialize_order_items")
        refund_policy_body = function_body("refund_policy")
        policy_summary_body = function_body("order_item_policy_summary")
        capability_body = function_body("capability_document")

        self.assertIn("product_commerce_policy", product_body)
        for code in ["'perishable'", "'deposit'", "'final_sale'", "'substitution_sensitive'"]:
            self.assertIn(code, rules_body)
        for field in ["'commerce_policy'", "'refund_conditions'", "'buyer_agent_aftercare_note'"]:
            self.assertIn(field, product_body + policy_body)
        self.assertIn("product_aftercare_override_flags", policy_body)
        self.assertIn("upsert_commerce_policy_flag", policy_body)
        for meta in [
            "PRODUCT_PERISHABLE_META",
            "PRODUCT_DEPOSIT_META",
            "PRODUCT_FINAL_SALE_META",
            "PRODUCT_SUBSTITUTION_SENSITIVE_META",
        ]:
            self.assertIn(meta, overrides_body)
        self.assertIn("'woocommerce_product_meta'", overrides_body)
        self.assertIn("'source'", flag_body + upsert_body)
        self.assertIn("'returnable'", flag_body + upsert_body)
        self.assertIn("'commerce_policy'", quote_cart_body)
        self.assertIn("ORDER_ITEMS_META", order_body)
        self.assertIn("ORDER_ITEMS_META", order_items_body)
        self.assertIn("'items'", order_response_body)
        self.assertIn("'items'", order_status_body)
        self.assertIn("order_item_policy_summary", refund_policy_body)
        self.assertIn("'merchant_review_required'", policy_summary_body)
        self.assertIn("'structured_commerce_policy_metadata'", capability_body)
        self.assertIn("'item_commerce_policy_metadata'", capability_body)
        self.assertIn("'aftercare_override_meta_keys'", capability_body)
        self.assertIn("'explicit_perishable_deposit_final_sale_overrides'", capability_body)
        self.assertIn("'explicit_substitution_sensitive_override'", capability_body)

    def test_merchant_aftercare_policy_is_configurable_quote_bound_and_preserved(self) -> None:
        settings_body = function_body("register_settings")
        render_body = function_body("render_settings_page")
        quote_body = function_body("quote")
        quote_hash_body = function_body("quote_hash_payload")
        order_body = function_body("create_order")
        order_status_body = function_body("serialize_order_status")
        order_response_body = function_body("serialize_order_response")
        stored_policy_body = function_body("stored_merchant_policy")
        refund_policy_body = function_body("refund_policy")
        registry_claim_body = function_body("registry_claim")
        capability_body = function_body("capability_document")

        for symbol in [
            "RETURNS_URL_OPTION",
            "SUBSTITUTION_POLICY_OPTION",
            "CANCELLATION_WINDOW_MINUTES_OPTION",
            "AGENTCART_RETURNS_URL",
            "AGENTCART_SUBSTITUTION_POLICY",
            "AGENTCART_CANCELLATION_WINDOW_MINUTES",
        ]:
            self.assertIn(symbol, SOURCE)
        self.assertIn("sanitize_substitution_policy_setting", settings_body)
        self.assertIn("sanitize_cancellation_window_minutes_setting", settings_body)
        self.assertIn("render_aftercare_policy_setting_rows", render_body)
        self.assertIn("'merchant_policy'", quote_body)
        self.assertIn("'merchant_policy'", quote_hash_body)
        self.assertIn("ORDER_MERCHANT_POLICY_META", order_body)
        self.assertIn("'merchant_policy'", order_status_body)
        self.assertIn("'merchant_policy'", order_response_body)
        self.assertIn("ORDER_MERCHANT_POLICY_META", stored_policy_body)
        self.assertIn("'merchant_policy'", refund_policy_body)
        self.assertIn("'merchant_aftercare_policy_defaults'", capability_body)
        self.assertIn("'merchant_substitution_policy'", capability_body)
        self.assertIn("'merchant_cancellation_policy'", capability_body)
        self.assertIn("'merchant_policy'", capability_body)
        self.assertIn("'merchant_policy_hash'", registry_claim_body)

    def test_cancellation_endpoint_is_idempotent_merchant_only_and_refund_safe(self) -> None:
        routes_body = function_body("register_routes")
        cancellation_body = function_body("create_cancellation")
        key_body = function_body("cancellation_idempotency_key")
        eligibility_body = function_body("cancellation_eligibility")
        policy_body = function_body("cancellation_policy")
        aftercare_body = function_body("aftercare_state")
        fulfillment_phase_body = function_body("fulfillment_phase")
        response_body = function_body("serialize_cancellation_response")
        status_body = function_body("serialize_order_status")
        order_response_body = function_body("serialize_order_response")
        refund_response_body = function_body("serialize_refund_response")
        capability_body = function_body("capability_document")

        self.assertIn("/orders/(?P<id>[\\d]+)/cancellations", routes_body)
        self.assertIn("authorize_cancellation", routes_body)
        self.assertIn("cancellation_idempotency_key", cancellation_body)
        self.assertIn("agentcart_cancellation_idempotency_key_required", cancellation_body)
        self.assertIn("find_existing_cancellation_event", cancellation_body)
        self.assertIn("validate_existing_cancellation_replay", cancellation_body)
        self.assertIn("acquire_cancellation_lock", cancellation_body)
        self.assertIn("cancellation_eligibility", cancellation_body)
        self.assertIn("update_status('cancelled'", cancellation_body)
        self.assertIn("'real_refund_verified' => false", cancellation_body + response_body)
        self.assertIn("'refund_required'", cancellation_body + response_body)
        self.assertIn("does_not_execute_refund", policy_body + capability_body)
        self.assertIn("'aftercare_state_contract'", capability_body)
        self.assertIn("'aftercare_state'", status_body)
        self.assertIn("'aftercare_state'", order_response_body)
        self.assertIn("'aftercare_state'", response_body)
        self.assertIn("'aftercare_state'", refund_response_body)
        for state in [
            "cancellable_before_fulfillment",
            "fulfillment_locked",
            "refund_available",
            "complete_verified_refund",
        ]:
            self.assertIn(state, aftercare_body)
        self.assertIn("'state' => $aftercare_state['cancellation_state']", policy_body)
        self.assertIn("serialize_fulfillment", aftercare_body)
        self.assertIn("cancellation_eligibility", aftercare_body)
        self.assertIn("tracking_number", fulfillment_phase_body)
        self.assertIn("pre_fulfillment", fulfillment_phase_body)
        self.assertIn("fulfillment_tracking_attached", eligibility_body)
        self.assertIn("terminal_order_status", eligibility_body)
        self.assertIn("requested_reference", key_body + cancellation_body)
        self.assertIn("'cancellation_policy'", status_body)
        self.assertIn("'cancellations'", status_body)
        self.assertIn("'cancellation_policy'", order_response_body)
        self.assertIn("'cancellations'", order_response_body)
        self.assertIn("'cancellation_endpoint'", capability_body)

    def test_fulfillment_tracking_adapter_contract_is_exposed_and_used_for_aftercare(self) -> None:
        capability_body = function_body("capability_document")
        fulfillment_body = function_body("serialize_fulfillment")
        tracking_body = function_body("tracking_from_order_meta")
        candidate_body = function_body("tracking_candidate")
        status_body = function_body("normalize_tracking_status")
        phase_body = function_body("fulfillment_phase")
        eligibility_body = function_body("cancellation_eligibility")

        self.assertIn("'carrier_tracking_adapter_contract'", capability_body)
        self.assertIn("'tracking_adapter_contract'", capability_body)
        for source in [
            "woocommerce_shipment_tracking",
            "aftership_tracking",
            "parcelpanel_tracking",
            "generic_order_meta",
        ]:
            self.assertIn(source, capability_body + tracking_body)
        for field in [
            "'tracking_status'",
            "'tracking'",
            "'shipped_at'",
            "'delivered_at'",
            "'last_event_at'",
            "'confidence'",
            "'is_real_carrier_tracking'",
        ]:
            self.assertIn(field, fulfillment_body + candidate_body)
        self.assertIn("_wc_shipment_tracking_items", tracking_body)
        self.assertIn("first_order_meta_value", tracking_body)
        self.assertIn("normalize_tracking_datetime", candidate_body)
        self.assertIn("normalize_tracking_status", candidate_body)
        self.assertIn("out_for_delivery", status_body)
        self.assertIn("in_transit", status_body)
        self.assertIn("tracking_status", phase_body)
        self.assertIn("fulfillment_tracking_attached", eligibility_body)
        self.assertIn("'in_transit'", eligibility_body)
        self.assertIn("'delivered'", eligibility_body)

    def test_product_shipping_country_overrides_are_exposed_and_rechecked(self) -> None:
        product_body = function_body("serialize_product")
        quote_body = function_body("quote")
        order_body = function_body("create_order")
        shipping_body = function_body("product_shipping_countries")

        self.assertIn("sanitize_country_list_setting", SOURCE)
        self.assertIn("product_shipping_countries", product_body)
        self.assertIn("'shipping_regions'", product_body)
        self.assertIn("PRODUCT_SHIPPING_COUNTRIES_META", shipping_body)
        self.assertIn("product_ships_to_country", quote_body)
        self.assertIn("agentcart_product_shipping_country_unsupported", quote_body)
        self.assertIn("product_ships_to_country", order_body)
        self.assertIn("agentcart_product_shipping_country_unsupported", order_body)
        self.assertLess(
            quote_body.index("agentcart_product_shipping_country_unsupported"),
            quote_body.index("validate_product_stock_for_agentcart"),
        )
        self.assertLess(
            order_body.index("agentcart_product_shipping_country_unsupported"),
            order_body.index("validate_product_stock_for_agentcart"),
        )

    def test_soft_stock_holds_are_created_and_revalidated(self) -> None:
        quote_body = function_body("quote")
        order_body = function_body("create_order")
        reservation_body = function_body("reserve_stock_for_quote")
        stock_check_body = function_body("validate_product_stock_for_agentcart")
        capability_body = function_body("capability_document")

        self.assertIn("STOCK_HOLD_MODE_OPTION", SOURCE)
        self.assertIn("STOCK_HOLD_MINUTES_OPTION", SOURCE)
        self.assertIn("STOCK_HOLDS_OPTION", SOURCE)
        self.assertIn("stock_hold_ttl_seconds", quote_body)
        self.assertIn("reserve_stock_for_quote", quote_body)
        self.assertIn("'stock_reserved_until'", quote_body)
        self.assertIn("'soft_reserved'", reservation_body)
        self.assertIn("held_stock_quantity", stock_check_body)
        self.assertIn("validate_product_stock_for_agentcart($product, $quantity)", quote_body)
        self.assertIn("validate_product_stock_for_agentcart($product, $quantity, $merchant_quote_id)", order_body)
        self.assertIn("release_stock_hold($merchant_quote_id)", order_body)
        self.assertIn("delete_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id)", order_body)
        self.assertIn("'soft_quote_stock_holds'", capability_body)

    def test_quote_rejects_over_limit_quantities_instead_of_clamping(self) -> None:
        quote_body = function_body("quote")

        self.assertIn("product_max_quantity", quote_body)
        self.assertIn("agentcart_quantity_limit_exceeded", quote_body)
        self.assertNotIn("min(20", quote_body)
        self.assertLess(
            quote_body.index("agentcart_quantity_limit_exceeded"),
            quote_body.index("add_to_cart"),
        )

    def test_order_creation_revalidates_product_quantity_limits_before_order_creation(self) -> None:
        order_body = function_body("create_order")

        self.assertIn("product_max_quantity", order_body)
        self.assertIn("agentcart_quantity_limit_exceeded", order_body)
        self.assertNotIn("min(20", order_body)
        self.assertLess(
            order_body.index("agentcart_quantity_limit_exceeded"),
            order_body.index("wc_create_order"),
        )

    def test_catalog_and_readiness_filter_blocked_products(self) -> None:
        catalog_body = function_body("catalog")
        count_body = function_body("agentcart_enabled_product_count")
        eligibility_body = function_body("is_product_agentcart_enabled")

        self.assertIn("array_filter", catalog_body)
        self.assertIn("is_product_agentcart_enabled", catalog_body)
        self.assertIn("array_filter", count_body)
        self.assertIn("is_product_agentcart_enabled", count_body)
        self.assertIn("is_product_agentcart_blocked", eligibility_body)


if __name__ == "__main__":
    unittest.main()
