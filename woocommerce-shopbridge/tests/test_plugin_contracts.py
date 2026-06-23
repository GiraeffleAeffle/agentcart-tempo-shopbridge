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
            "=== AgentCart ShopBridge for WooCommerce ===",
            "Requires at least:",
            "Requires PHP:",
            "Requires Plugins: woocommerce",
            "Stable tag: 0.1.0",
            "License:",
            "== Installation ==",
            "== Changelog ==",
        ]:
            self.assertIn(field, readme)
        for endpoint in [
            "/.well-known/agentcart.json",
            "/.well-known/agentcart-registry-proof.json",
            "/.well-known/agentcart-registry-revocations.json",
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

        self.assertIn("enforce_rate_limit", public_body)
        self.assertIn("enforce_rate_limit($request, 'checkout')", checkout_body)
        self.assertIn("enforce_rate_limit($request, 'order_status')", status_body)
        self.assertIn("enforce_rate_limit($request, 'refund')", refund_body)
        self.assertIn("enforce_rate_limit($request, 'cancellation')", cancellation_body)
        self.assertLess(checkout_body.index("enforce_rate_limit"), checkout_body.index("has_valid_merchant_token"))
        self.assertLess(status_body.index("enforce_rate_limit"), status_body.index("wc_get_order"))
        self.assertLess(refund_body.index("enforce_rate_limit"), refund_body.index("has_valid_merchant_token"))
        self.assertLess(cancellation_body.index("enforce_rate_limit"), cancellation_body.index("has_valid_merchant_token"))

    def test_rate_limiter_has_endpoint_policies_and_retry_metadata(self) -> None:
        policy_body = function_body("rate_limit_policy")
        limiter_body = function_body("enforce_rate_limit")
        key_body = function_body("rate_limit_client_key")
        capability_body = function_body("capability_document")

        for bucket in ["'catalog'", "'quote'", "'checkout'", "'order_status'", "'refund'", "'cancellation'"]:
            self.assertIn(bucket, policy_body)
        self.assertIn("agentcart_rate_limited", limiter_body)
        self.assertIn("'retry_after_seconds'", limiter_body)
        self.assertIn("set_transient", limiter_body)
        self.assertIn("REMOTE_ADDR", key_body)
        self.assertNotIn("x-forwarded-for", key_body)
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
        self.assertIn("'revocations' => []", revocations_body)
        self.assertIn("'revocation_url' => self::registry_revocation_url()", claim_body)
        self.assertIn("'registry_revocations' => self::registry_revocation_url()", capability_body)
        self.assertIn("'revocation_url' => self::registry_revocation_url()", capability_body)
        self.assertIn("'revocation_snapshot'", signature_payload_body)

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
