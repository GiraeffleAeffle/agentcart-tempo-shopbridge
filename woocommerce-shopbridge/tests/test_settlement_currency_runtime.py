"""Exercise settlement advertisement and readiness on the actual PHP plugin class."""
import json
import shutil
import unittest

import test_payment_availability_runtime as payment_availability


READINESS_FIXTURES = r'''
class WooCommerce {}
function sanitize_title($value) { return strtolower(trim((string) $value)); }
class WC_Product {
    public function get_id() { return 101; }
    public function get_status() { return 'publish'; }
    public function get_type() { return 'simple'; }
    public function get_category_ids() { return []; }
    public function get_meta($key, $single) {
        return in_array($key, ['_agentcart_enabled', '_agentcart_restricted_goods_allowed'], true) ? 'yes' : '';
    }
}
function wc_get_products($args) { return [new WC_Product()]; }
function has_filter($hook) { return !empty($GLOBALS['filters'][$hook]); }
function wc_get_page_id($page) { return $GLOBALS['options']['woocommerce_'.$page.'_page_id'] ?? 0; }
function get_page_by_path($path) { return $GLOBALS['pages_by_path'][$path] ?? null; }
function get_post_status($page) {
    $id = is_object($page) ? $page->ID : $page;
    return $GLOBALS['page_statuses'][$id] ?? false;
}
function wc_tax_enabled() { return ($GLOBALS['options']['woocommerce_calc_taxes'] ?? 'no') === 'yes'; }
class WC_Tax {
    public static function get_rates_for_tax_class($class) { return $GLOBALS['tax_rates']; }
}
class WC_Shipping_Zones {
    public static function get_zones() { return [['zone_id' => 1]]; }
}
class WC_Shipping_Zone {
    public function __construct(public $id) {}
    public function get_shipping_methods($enabled_only) { return $GLOBALS['shipping_methods'][$this->id] ?? []; }
}
'''


@unittest.skipUnless(shutil.which("php"), "php is required")
class SettlementCurrencyRuntimeTests(unittest.TestCase):
    def run_plugin(self, currency, production=True, stripe=False, network="testnet", mutate=""):
        body = f'''
$GLOBALS['options'][AgentCart_ShopBridge::TOKEN_OPTION] = str_repeat('m', 40);
$GLOBALS['options'][AgentCart_ShopBridge::PAYMENT_VERIFIER_TOKEN_OPTION] = str_repeat('v', 40);
$GLOBALS['options'][AgentCart_ShopBridge::MERCHANT_ID_OPTION] = 'currency-fixture-shop';
$GLOBALS['options'][AgentCart_ShopBridge::SUPPORT_EMAIL_OPTION] = 'support@shop.example';
$GLOBALS['options'][AgentCart_ShopBridge::CHECKOUT_MODE_OPTION] = {json.dumps('external_verifier_only' if production else 'trusted_token_or_verifier')};
$GLOBALS['options'][AgentCart_ShopBridge::SIGNED_REQUEST_MODE_OPTION] = 'require_checkout';
$GLOBALS['options'][AgentCart_ShopBridge::SIGNED_REQUEST_KEYS_OPTION] = [[
    'id' => 'currency-fixture-signer', 'secret' => str_repeat('s', 40), 'state' => 'active',
]];
$GLOBALS['options'][AgentCart_ShopBridge::STOCK_HOLD_MODE_OPTION] = 'hard';
$GLOBALS['options'][AgentCart_ShopBridge::TEMPO_RECIPIENT_OPTION] = '0x1111111111111111111111111111111111111111';
$GLOBALS['options'][AgentCart_ShopBridge::TEMPO_NETWORK_OPTION] = {json.dumps(network)};
$GLOBALS['options'][AgentCart_ShopBridge::STRIPE_PROFILE_ID_OPTION] = {json.dumps('stripe-profile' if stripe else '')};
$GLOBALS['options'][AgentCart_ShopBridge::PRODUCT_EXPOSURE_SNAPSHOT_OPTION] = [
    'included_count' => 1, 'catalog_hash' => str_repeat('a', 64), 'saved_at' => '2026-10-01T00:00:00Z',
];
$GLOBALS['options']['woocommerce_currency'] = {json.dumps(currency)};
$GLOBALS['options']['woocommerce_terms_page_id'] = 10;
$GLOBALS['options']['woocommerce_calc_taxes'] = 'yes';
$GLOBALS['pages_by_path'] = ['returns' => (object) ['ID' => 11]];
$GLOBALS['page_statuses'] = [10 => 'publish', 11 => 'publish'];
$GLOBALS['tax_rates'] = [1 => ['rate' => 19]];
$GLOBALS['shipping_methods'] = [1 => [(object) ['enabled' => 'yes', 'id' => 'flat_rate']]];
{mutate}
$quote = ['id' => 'currency-quote', 'currency' => get_woocommerce_currency(), 'total_cents' => 1580,
    'quote_hash' => str_repeat('a', 64)];
echo json_encode([
    'requirements' => invoke('payment_requirements', $quote),
    'readiness' => invoke('readiness'),
    'rails' => invoke('available_payment_rails_for_quote', $quote),
]);
'''
        return payment_availability.PaymentAvailabilityRuntimeTests.run_plugin(self, body, setup=READINESS_FIXTURES)

    def test_eur_tempo_only_production_is_unavailable_and_not_ready(self):
        for network in ("testnet", "mainnet"):
            with self.subTest(network=network):
                result = self.run_plugin("EUR", network=network)
                tempo = result["requirements"]["protocols"][0]
                self.assertFalse(tempo["available"])
                self.assertEqual(tempo["unavailable_reason"], "tempo_settlement_currency_mismatch")
                self.assertIsNone(tempo["profile_id"])
                self.assertNotIn("tempo-mpp", result["rails"])
                self.assertFalse(result["readiness"]["production_ready"])
                self.assertEqual(len(result["readiness"]["missing_for_production"]), 1, result["readiness"])

    def test_usd_tempo_production_remains_available_and_ready(self):
        result = self.run_plugin("USD")
        self.assertTrue(result["requirements"]["protocols"][0]["available"])
        self.assertIn("tempo-mpp", result["rails"])
        self.assertTrue(result["readiness"]["production_ready"], result["readiness"])
        self.assertEqual(result["requirements"]["verification_contract"]["amount"]["currency"], "USD")
        self.assertEqual(result["requirements"]["verification_contract"]["settlement"]["fx_policy"], "same_currency_only_no_fx")
        weak = self.run_plugin("USD", mutate="$GLOBALS['options'][AgentCart_ShopBridge::PAYMENT_VERIFIER_TOKEN_OPTION] = 'weak';")
        self.assertFalse(weak["readiness"]["production_ready"])
        self.assertEqual(len(weak["readiness"]["missing_for_production"]), 1, weak["readiness"])

    def test_eur_stripe_allows_readiness_but_not_tempo(self):
        result = self.run_plugin("EUR", stripe=True)
        self.assertFalse(result["requirements"]["protocols"][0]["available"])
        self.assertTrue(result["requirements"]["protocols"][1]["available"])
        self.assertTrue(result["readiness"]["production_ready"], result["readiness"])
        self.assertEqual(result["requirements"]["verification_contract"]["rail"], "stripe-card-mpp")
        self.assertEqual(result["requirements"]["verification_contract"]["settlement"]["asset"]["denomination"], "EUR")

    def test_eur_sandbox_retains_demo_advertisement(self):
        result = self.run_plugin("EUR", production=False)
        self.assertTrue(result["requirements"]["protocols"][0]["available"])
        self.assertIn("not real settlement", result["requirements"]["protocols"][0]["settlement_note"])
        self.assertFalse(result["readiness"]["production_ready"])
        self.assertEqual(result["requirements"]["verification_contract"]["settlement"]["fx_policy"], "demo_fixed_1_1_not_real_settlement")


if __name__ == "__main__":
    unittest.main()
