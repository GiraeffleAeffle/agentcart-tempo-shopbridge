"""Exercise plugin payment advertisement and hosted registry opt-in in PHP."""
import json
import pathlib
import shutil
import subprocess
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "agentcart-shopbridge/agentcart-shopbridge.php"


@unittest.skipUnless(shutil.which("php"), "php is required")
class PaymentAvailabilityRuntimeTests(unittest.TestCase):
    def run_plugin(self, body, setup=""):
        script = r'''<?php
 define('ABSPATH', '/');
 class WP_REST_Request {}
 class WP_Error {
   public function __construct(public $code, public $message, public $data = []) {}
   public function get_error_code() { return $this->code; }
   public function get_error_data() { return $this->data; }
   public function get_error_message() { return $this->message; }
 }
 class WC_Order {
   public function __construct(public $currency = 'USD', public $rail = 'tempo-mpp') {}
   public function get_currency() { return $this->currency; }
   public function get_meta($key, $single) { return $key === '_agentcart_payment_rail' ? $this->rail : ''; }
   public function get_payment_method() { return $this->rail; }
   public function get_id() { return 1; }
   public function get_order_number() { return 'one'; }
 }
 function is_wp_error($value) { return $value instanceof WP_Error; }
 function current_user_can($capability) { return $capability === 'manage_woocommerce'; }
 function get_bloginfo($key) { return 'Fixture Shop'; }
 function wc_get_page_permalink($key) { return 'https://shop.example/terms'; }
 function WC() { return (object) ['countries' => new class { public function get_base_country() { return 'US'; } }]; }
 function wc_get_orders($args) { return []; }
 function wp_remote_retrieve_response_code($response) { return 200; }
 function wp_remote_retrieve_body($response) { return json_encode($response); }
 function add_action(...$args) {}
 function add_filter(...$args) { $GLOBALS['filters'][$args[0]][] = $args[1]; }
 function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
 function register_setting($group, $key, $args) { $GLOBALS['settings'][$key] = $args; }
 function sanitize_text_field($value) { return trim((string) $value); }
 function sanitize_key($value) { return strtolower((string) $value); }
 function sanitize_email($value) { return $value; }
 function absint($value) { return abs(intval($value)); }
 function esc_url_raw($value, $schemes = null) { return trim((string) $value); }
 function wp_parse_url($value) { return parse_url($value); }
 function get_woocommerce_currency() { return $GLOBALS['options']['woocommerce_currency'] ?? 'USD'; }
 function home_url($path = '') { return 'https://shop.example' . $path; }
 function rest_url($path = '') { return 'https://shop.example/wp-json/' . $path; }
 function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
 function wp_safe_remote_post(...$args) { throw new Exception('Unexpected registry network request'); }
 function wp_safe_remote_get(...$args) { throw new Exception('Unexpected network request'); }
 function wp_remote_post(...$args) {
   $GLOBALS['http_calls'] = ($GLOBALS['http_calls'] ?? 0) + 1;
   if (!isset($GLOBALS['verifier_response'])) { throw new Exception('Unexpected network request'); }
   return $GLOBALS['verifier_response'];
 }
 function wp_remote_get(...$args) { throw new Exception('Unexpected network request'); }
 function invoke($name, ...$args) { return (new ReflectionMethod(AgentCart_ShopBridge::class, $name))->invoke(null, ...$args); }
 $GLOBALS['options'] = [
   'agentcart_shopbridge_payment_verifier_url' => 'https://8.8.8.8/verify',
   'agentcart_shopbridge_x402_network' => 'eip155:84532',
   'agentcart_shopbridge_x402_asset' => '0x1111111111111111111111111111111111111111',
   'agentcart_shopbridge_x402_pay_to' => '0x2222222222222222222222222222222222222222',
 ];
 ''' + setup + r'''
 require $argv[1];
 ''' + body
        result = subprocess.run(["php", "--", str(PLUGIN)], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_configured_x402_without_confirmed_verifier_is_unavailable(self):
        profiles = self.run_plugin("""
echo json_encode(invoke('protocol_profiles', ['production_ready' => false]));
""")
        profile = next(p for p in profiles if p["id"] == "x402-compatible")
        self.assertEqual(profile["status"], "unavailable")
        self.assertFalse(profile["available"])
        self.assertEqual(profile["unavailable_reason"], "verifier_x402_support_unconfirmed")
        result = self.run_plugin('''
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => 'bound'];
echo json_encode([
 'ids' => invoke('protocol_profile_ids', ['production_ready' => false]),
 'rails' => invoke('available_payment_rails_for_quote', $quote),
 'requirement' => invoke('x402_payment_required_document', $quote),
 'reason' => invoke('x402_unavailable_reason', $quote),
 'registry_protocols' => invoke('registry_supported_protocols'),
]);
''')
        self.assertEqual(result["reason"], "verifier_x402_support_unconfirmed")
        self.assertNotIn("x402-compatible", result["ids"])
        self.assertNotIn("x402-compatible", result["rails"])
        self.assertNotIn("x402-compatible", result["registry_protocols"])
        self.assertIsNone(result["requirement"])

    def test_hosted_registry_default_is_opt_in_and_empty_calls_do_not_send(self):
        result = self.run_plugin('''
AgentCart_ShopBridge::register_settings();
echo json_encode([
 'default' => $GLOBALS['settings'][AgentCart_ShopBridge::REGISTRY_CONNECTION_URL_OPTION]['default'],
 'url' => invoke('registry_connection_url'),
 'health' => invoke('registry_connection_endpoint_url', 'health'),
 'monitor' => invoke('registry_connection_endpoint_url', 'monitor'),
 'events' => invoke('registry_connection_endpoint_url', 'onchain_events'),
 'submission' => invoke('call_registry_connection', '', ['operation' => 'upsert']),
]);
''')
        for field in ("default", "url", "health", "monitor", "events"):
            self.assertEqual(result[field], "")
        self.assertEqual(result["submission"]["state"], "failed")
        self.assertEqual(result["submission"]["status"], 0)

    def test_explicitly_saved_hosted_registry_url_is_preserved(self):
        result = self.run_plugin('''
$GLOBALS['options'][AgentCart_ShopBridge::REGISTRY_CONNECTION_URL_OPTION] = 'https://registry.example/v1/registry/records';
echo json_encode([
 'url' => invoke('registry_connection_url'),
 'health' => invoke('registry_connection_endpoint_url', 'health'),
 'monitor' => invoke('registry_connection_endpoint_url', 'monitor'),
 'events' => invoke('registry_connection_endpoint_url', 'onchain_events'),
]);
''')
        self.assertEqual(result["url"], "https://registry.example/v1/registry/records")
        self.assertEqual(result["health"], "https://registry.example/v1/registry/health")
        self.assertEqual(result["monitor"], "https://registry.example/v1/registry/monitor")
        self.assertEqual(result["events"], "https://registry.example/v1/registry/onchain/events")

    def verify_receipt(self, rail="tempo-mpp", currency="USD", mutate=""):
        return self.run_plugin(f'''
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$GLOBALS['options']['agentcart_shopbridge_tempo_recipient'] = '0x3333333333333333333333333333333333333333';
$GLOBALS['options']['agentcart_shopbridge_stripe_profile_id'] = 'profile_fixture';
$rail = {json.dumps(rail)};
$currency = {json.dumps(currency)};
$quote = ['id' => 'quote-one', 'currency' => $currency, 'total_cents' => 1234, 'quote_hash' => 'bound'];
$contract = invoke('payment_verification_contract_with_hash', $quote, $rail);
$quote['payment_requirements']['verification_contracts'] = invoke('payment_verification_contracts', $quote);
$receipt = ['id' => 'receipt-one', 'rail' => $rail, 'amount_cents' => 1234, 'currency' => $currency,
 'quote_hash' => 'bound', 'payment_contract_hash' => $contract['payment_contract_hash']];
$body = ['rail' => $rail, 'payment_contract_hash' => $contract['payment_contract_hash']];
$GLOBALS['verifier_response'] = ['ok' => true, 'real_settlement_verified' => true,
 'amount_cents' => 1234, 'currency' => $currency, 'rail' => $rail,
 'quote_hash' => 'bound', 'payment_contract_hash' => $contract['payment_contract_hash'],
 'network' => 'testnet', 'recipient' => '0x3333333333333333333333333333333333333333',
 'stripe_profile_id' => 'profile_fixture', 'transaction_reference' => 'tx-fixture'];
{mutate}
$result = invoke('verify_payment_receipt', $quote, $receipt, $body, new WP_REST_Request());
echo json_encode(['result' => is_wp_error($result) ? ['error' => $result->code] : $result,
 'http_calls' => $GLOBALS['http_calls'] ?? 0]);
''')

    def test_unavailable_x402_receipt_never_contacts_verifier(self):
        result = self.verify_receipt("x402-compatible")
        self.assertEqual(result["result"].get("error"), "agentcart_payment_rail_unavailable_for_quote")
        self.assertEqual(result["http_calls"], 0)

    def test_eur_production_tempo_receipt_never_contacts_verifier(self):
        result = self.verify_receipt(currency="EUR")
        self.assertEqual(result["result"].get("error"), "agentcart_payment_rail_unavailable_for_quote")
        self.assertEqual(result["http_calls"], 0)

    def test_honest_stripe_and_usd_tempo_receipts_verify(self):
        for rail in ("stripe-card-mpp", "tempo-mpp"):
            with self.subTest(rail=rail):
                result = self.verify_receipt(rail)
                self.assertEqual(result["result"]["state"], "verified")
                self.assertTrue(result["result"]["real_settlement_verified"])
                self.assertEqual(result["result"]["rail"], rail)
                self.assertEqual(result["result"]["currency"], "USD")
                self.assertEqual(result["result"]["amount_cents"], 1234)
                self.assertEqual(result["http_calls"], 1)

    def test_contract_claims_must_match_stored_advertisement(self):
        mutations = [
            "$body['payment_contract_hash'] = str_repeat('a', 64);",
            "$receipt['contract_hash'] = str_repeat('a', 64);",
            "unset($quote['payment_requirements']['verification_contracts']);",
            "$quote['payment_requirements']['verification_contracts'][0]['settlement']['recipient'] = 'changed';",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.verify_receipt(mutate=mutation)
                self.assertEqual(result["result"].get("error"), "agentcart_payment_contract_mismatch")
                self.assertEqual(result["http_calls"], 0)

    def test_refund_rail_must_be_available_and_match_original_payment(self):
        for original, selected, currency, error in (
            ("tempo-mpp", "x402-compatible", "USD", "agentcart_payment_rail_unavailable_for_quote"),
            ("tempo-mpp", "tempo-mpp", "EUR", "agentcart_payment_rail_unavailable_for_quote"),
            ("tempo-mpp", "stripe-card-mpp", "USD", "agentcart_refund_rail_mismatch"),
        ):
            with self.subTest(original=original, selected=selected, currency=currency):
                result = self.run_plugin(f'''
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$GLOBALS['options']['agentcart_shopbridge_stripe_profile_id'] = 'profile_fixture';
$result = invoke('verify_refund_request', new WC_Order({json.dumps(currency)}, {json.dumps(original)}),
 100, 'return', {json.dumps(selected)}, []);
echo json_encode(['error' => $result->code, 'http_calls' => $GLOBALS['http_calls'] ?? 0]);
''')
                self.assertEqual(result["error"], error)
                self.assertEqual(result["http_calls"], 0)

    def sandbox_dry_result(self, options=None, mutate=""):
        return self.run_plugin(f'''
$GLOBALS['options'] = json_decode({json.dumps(json.dumps(options or {}))}, true);
$quote = ['id' => 'sandbox-quote', 'currency' => get_woocommerce_currency(), 'total_cents' => 1234, 'quote_hash' => 'bound'];
$quote['payment_requirements']['verification_contracts'] = invoke('payment_verification_contracts', $quote);
$receipt = invoke('sandbox_checkout_payment_receipt', $quote, 'sandbox-order');
if (is_wp_error($receipt)) {{
 echo json_encode(['result' => ['error' => $receipt->code, 'message' => $receipt->message], 'http_calls' => $GLOBALS['http_calls'] ?? 0]);
 exit;
}}
$approval = invoke('sandbox_checkout_approval_record', $quote, 'sandbox-order', '2026-10-01T12:00:00Z', $receipt);
$body = ['rail' => $receipt['rail'], 'approval' => $approval];
(new ReflectionProperty(AgentCart_ShopBridge::class, 'sandbox_checkout_active'))->setValue(null, true);
{mutate}
$result = invoke('verify_payment_receipt', $quote, $receipt, $body, new WP_REST_Request());
echo json_encode(['result' => is_wp_error($result) ? ['error' => $result->code] : $result,
 'approval' => $approval['approval_record']['approval_material'],
 'http_calls' => $GLOBALS['http_calls'] ?? 0]);
''')

    def test_eur_verifier_only_sandbox_uses_stripe_without_http(self):
        result = self.sandbox_dry_result({
            "woocommerce_currency": "EUR",
            "agentcart_shopbridge_checkout_mode": "external_verifier_only",
            "agentcart_shopbridge_payment_verifier_url": "https://8.8.8.8/verify",
            "agentcart_shopbridge_stripe_profile_id": "profile_eur",
        })
        self.assertEqual(result["result"]["mode"], "woocommerce_admin_dry_run")
        self.assertFalse(result["result"]["real_settlement_verified"])
        self.assertEqual(result["result"]["currency"], "EUR")
        self.assertEqual(result["result"]["amount_cents"], 1234)
        self.assertEqual(result["result"]["rail"], "stripe-card-mpp")
        self.assertEqual(result["approval"]["payment_destination"]["stripe_profile_id"], "profile_eur")
        self.assertEqual(result["approval"]["payment_destination"]["rail"], "stripe-card-mpp")
        self.assertEqual(result["approval"]["payment_contract_hash"], result["result"]["payment_contract_hash"])
        self.assertEqual(result["http_calls"], 0)

    def test_sandbox_without_available_rail_names_configuration_fix(self):
        result = self.sandbox_dry_result({
            "woocommerce_currency": "EUR",
            "agentcart_shopbridge_checkout_mode": "external_verifier_only",
            "agentcart_shopbridge_payment_verifier_url": "https://8.8.8.8/verify",
        })
        self.assertEqual(result["result"]["error"], "agentcart_sandbox_payment_rail_unavailable")
        self.assertIn("Stripe/card profile and verifier", result["result"]["message"])
        self.assertIn("USD store with Tempo", result["result"]["message"])
        self.assertEqual(result["http_calls"], 0)

    def test_fresh_sandbox_dry_checkout_verifies_only_its_advertised_contract(self):
        for mutation, expected in (
            ("", None),
            ("$body['rail'] = 'x402-compatible';", "agentcart_payment_rail_unavailable_for_quote"),
            ("$receipt['payment_contract_hash'] = str_repeat('a', 64);", "agentcart_payment_contract_mismatch"),
            ("unset($quote['payment_requirements']['verification_contracts']);", "agentcart_payment_contract_mismatch"),
        ):
            with self.subTest(mutation=mutation):
                result = self.sandbox_dry_result(mutate=mutation)
                if expected is None:
                    self.assertEqual(result["result"]["state"], "verified")
                    self.assertEqual(result["result"]["mode"], "woocommerce_admin_dry_run")
                    self.assertFalse(result["result"]["real_settlement_verified"])
                    self.assertEqual(result["result"]["amount_cents"], 1234)
                    self.assertEqual(result["result"]["currency"], "USD")
                    self.assertEqual(result["result"]["rail"], "tempo-mpp")
                else:
                    self.assertEqual(result["result"].get("error"), expected)
                self.assertEqual(result["http_calls"], 0)

    def refund_replay_after_settings_change(self):
        setup = r'''
define('ARRAY_A', 'ARRAY_A');
class RefundReplayDatabase {
 public $posts = 'wp_posts', $postmeta = 'wp_postmeta', $comments = 'wp_comments', $commentmeta = 'wp_commentmeta', $prefix = 'wp_';
 public function prepare($sql, ...$args) { return $sql; }
 public function get_results($sql, $format) { return array_fill(0, 8, ['ENGINE' => 'InnoDB']); }
 public function get_var($sql) { $GLOBALS['lock_calls'] = ($GLOBALS['lock_calls'] ?? 0) + 1; return 1; }
}
$GLOBALS['wpdb'] = new RefundReplayDatabase();
class RefundReplayRequest extends WP_REST_Request implements ArrayAccess {
 public function __construct(public $body) {}
 public function get_json_params() { return $this->body; }
 public function get_header($name) { return ''; }
 public function offsetExists(mixed $offset): bool { return $offset === 'id'; }
 public function offsetGet(mixed $offset): mixed { return 1; }
 public function offsetSet(mixed $offset, mixed $value): void { throw new Exception('Unexpected request mutation'); }
 public function offsetUnset(mixed $offset): void { throw new Exception('Unexpected request mutation'); }
}
class CompletedRefund {
 public function get_id() { return 23; }
 public function get_amount() { return 1.23; }
 public function get_reason() { return 'return'; }
 public function get_date_created() { return null; }
 public function get_meta($key, $single) {
   return [
     '_agentcart_refund_idempotency_key' => 'refund-one',
     '_agentcart_refund_rail' => 'stripe-card-mpp',
     '_agentcart_refund_requested_reference' => 'refund-ref',
     '_agentcart_refund_reference' => 're_completed',
     '_agentcart_refund_verification' => json_encode(['real_refund_verified' => true, 'refund_status' => 'succeeded', 'refund_reference' => 're_completed']),
   ][$key] ?? '';
 }
}
class RefundedOrder extends WC_Order {
 public $refunds;
 public function __construct() { parent::__construct('EUR', 'stripe-card-mpp'); $this->refunds = [new CompletedRefund()]; }
 public function get_meta($key, $single) { return $key === '_agentcart_order_id' ? 'order-one' : parent::get_meta($key, $single); }
 public function get_refunds() { return $this->refunds; }
 public function get_status() { return 'processing'; }
 public function get_date_created() { return null; }
 public function get_remaining_refund_amount() { return 8.77; }
 public function get_total_refunded() { return 1.23; }
 public function get_total() { return 10; }
 public function is_paid() { return true; }
 public function has_status($status) { return in_array($this->get_status(), (array) $status, true); }
 public function get_items($type = null) { return []; }
 public function get_data_store() { return new class { public function read($order) {} }; }
 public function read_meta_data($force) {}
 public function update_meta_data(...$args) { throw new Exception('Replay or rejected new refund must not reserve capacity'); }
 public function save() { throw new Exception('Replay or rejected new refund must not save order'); }
}
function wc_get_order($id) { return $GLOBALS['replay_order']; }
$GLOBALS['replay_order'] = new RefundedOrder();
'''
        body = r'''
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$GLOBALS['options']['agentcart_shopbridge_stripe_profile_id'] = 'profile_refund';
$request = new RefundReplayRequest(['refund_idempotency_key' => 'refund-one', 'amount_cents' => 123, 'rail' => 'stripe-card-mpp', 'requested_reference' => 'refund-ref']);
$before = AgentCart_ShopBridge::create_refund($request);
unset($GLOBALS['options']['agentcart_shopbridge_stripe_profile_id']);
$GLOBALS['options']['agentcart_shopbridge_payment_verifier_url'] = 'https://8.8.4.4/changed-verifier';
$after = AgentCart_ShopBridge::create_refund($request);
$replay_lock_calls = $GLOBALS['lock_calls'] ?? 0;
$conflict_request = new RefundReplayRequest(['refund_idempotency_key' => 'refund-one', 'amount_cents' => 124, 'rail' => 'stripe-card-mpp']);
$conflict = AgentCart_ShopBridge::create_refund($conflict_request);
$new_request = new RefundReplayRequest(['refund_idempotency_key' => 'refund-two', 'amount_cents' => 123, 'rail' => 'stripe-card-mpp']);
$new = AgentCart_ShopBridge::create_refund($new_request);
echo json_encode([
 'before' => $before, 'after' => $after, 'replay_lock_calls' => $replay_lock_calls,
 'conflict_error' => is_wp_error($conflict) ? $conflict->code : null,
 'new_error' => is_wp_error($new) ? $new->code : null,
 'http_calls' => $GLOBALS['http_calls'] ?? 0,
]);
'''
        return self.run_plugin(body, setup=setup)

    def test_successful_refund_replay_survives_changed_payment_settings(self):
        result = self.refund_replay_after_settings_change()
        for field in ("before", "after"):
            self.assertEqual(result[field]["state"], "refund_idempotent_replay")
            self.assertTrue(result[field]["real_refund_verified"])
            self.assertEqual(result[field]["refund_reference"], "re_completed")
            self.assertEqual(result[field]["amount_cents"], 123)
            self.assertEqual(result[field]["rail"], "stripe-card-mpp")
        self.assertEqual(result["replay_lock_calls"], 0)
        self.assertEqual(result["conflict_error"], "agentcart_refund_idempotency_conflict")
        self.assertEqual(result["new_error"], "agentcart_payment_rail_unavailable_for_quote")
        self.assertEqual(result["http_calls"], 0)


if __name__ == "__main__":
    unittest.main()
