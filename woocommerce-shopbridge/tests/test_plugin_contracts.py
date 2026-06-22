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

    def test_product_exposure_modes_are_supported(self) -> None:
        self.assertIn("PRODUCT_EXPOSURE_MODE_OPTION", SOURCE)
        self.assertIn("PRODUCT_EXPOSURE_TAG_OPTION", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_EXPOSURE_MODE", SOURCE)
        self.assertIn("AGENTCART_PRODUCT_EXPOSURE_TAG", SOURCE)

        mode_body = function_body("sanitize_product_exposure_mode_setting")
        self.assertIn("'manual'", mode_body)
        self.assertIn("'tag'", mode_body)
        self.assertIn("'all'", mode_body)

    def test_product_exposure_query_supports_manual_tag_and_all_modes(self) -> None:
        query_body = function_body("agentcart_product_query_args")
        eligibility_body = function_body("is_product_agentcart_enabled")
        capability_body = function_body("capability_document")

        self.assertIn("agentcart_enabled_meta_query", query_body)
        self.assertIn("product_exposure_tag", query_body)
        self.assertIn("'tag'", query_body)
        self.assertIn("'all'", eligibility_body)
        self.assertIn("has_term", eligibility_body)
        self.assertIn("PRODUCT_ENABLED_META", eligibility_body)
        self.assertIn("'product_exposure'", capability_body)
        self.assertIn("'tag_based_product_exposure'", capability_body)
        self.assertIn("'all_published_simple_product_exposure'", capability_body)

    def test_product_safety_controls_are_exposed_and_enforced(self) -> None:
        self.assertIn("PRODUCT_BLOCKED_META", SOURCE)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", SOURCE)

        product_options_body = function_body("render_product_agentcart_options")
        self.assertIn("Exclude from AgentCart checkout", product_options_body)
        self.assertIn("AgentCart max quantity", product_options_body)

        save_body = function_body("save_product_agentcart_options")
        self.assertIn("PRODUCT_BLOCKED_META", save_body)
        self.assertIn("PRODUCT_MAX_QUANTITY_META", save_body)

        product_body = function_body("serialize_product")
        self.assertIn("'max_quantity'", product_body)
        self.assertIn("'agentcart_policy'", product_body)
        self.assertIn("is_product_agentcart_blocked", product_body)

        capability_body = function_body("capability_document")
        self.assertIn("'per_product_agentcart_max_quantity'", capability_body)
        self.assertIn("'per_product_agentcart_block_override'", capability_body)
        self.assertIn("'product_policy'", capability_body)

    def test_quote_rejects_over_limit_quantities_instead_of_clamping(self) -> None:
        quote_body = function_body("quote")

        self.assertIn("product_max_quantity", quote_body)
        self.assertIn("agentcart_quantity_limit_exceeded", quote_body)
        self.assertNotIn("min(20", quote_body)
        self.assertLess(
            quote_body.index("agentcart_quantity_limit_exceeded"),
            quote_body.index("add_to_cart"),
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
