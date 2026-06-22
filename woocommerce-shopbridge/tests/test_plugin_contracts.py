from __future__ import annotations

import pathlib
import re
import unittest


PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "agentcart-shopbridge" / "agentcart-shopbridge.php"
SOURCE = PLUGIN.read_text()


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

        self.assertIn("enforce_rate_limit", public_body)
        self.assertIn("enforce_rate_limit($request, 'checkout')", checkout_body)
        self.assertIn("enforce_rate_limit($request, 'order_status')", status_body)
        self.assertIn("enforce_rate_limit($request, 'refund')", refund_body)
        self.assertLess(checkout_body.index("enforce_rate_limit"), checkout_body.index("has_valid_merchant_token"))
        self.assertLess(status_body.index("enforce_rate_limit"), status_body.index("wc_get_order"))
        self.assertLess(refund_body.index("enforce_rate_limit"), refund_body.index("has_valid_merchant_token"))

    def test_rate_limiter_has_endpoint_policies_and_retry_metadata(self) -> None:
        policy_body = function_body("rate_limit_policy")
        limiter_body = function_body("enforce_rate_limit")
        key_body = function_body("rate_limit_client_key")
        capability_body = function_body("capability_document")

        for bucket in ["'catalog'", "'quote'", "'checkout'", "'order_status'", "'refund'"]:
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

    def test_product_safety_controls_are_exposed_and_enforced(self) -> None:
        self.assertIn("PRODUCT_BLOCKED_META", SOURCE)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", SOURCE)
        self.assertIn("PRODUCT_SHIPPING_COUNTRIES_META", SOURCE)

        product_options_body = function_body("render_product_agentcart_options")
        self.assertIn("Exclude from AgentCart checkout", product_options_body)
        self.assertIn("AgentCart max quantity", product_options_body)
        self.assertIn("AgentCart shipping countries", product_options_body)

        save_body = function_body("save_product_agentcart_options")
        self.assertIn("PRODUCT_BLOCKED_META", save_body)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", save_body)
        self.assertIn("PRODUCT_SHIPPING_COUNTRIES_META", save_body)
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
        self.assertIn("'commerce_policy'", quote_cart_body)
        self.assertIn("ORDER_ITEMS_META", order_body)
        self.assertIn("ORDER_ITEMS_META", order_items_body)
        self.assertIn("'items'", order_response_body)
        self.assertIn("'items'", order_status_body)
        self.assertIn("order_item_policy_summary", refund_policy_body)
        self.assertIn("'merchant_review_required'", policy_summary_body)
        self.assertIn("'structured_commerce_policy_metadata'", capability_body)
        self.assertIn("'item_commerce_policy_metadata'", capability_body)

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
