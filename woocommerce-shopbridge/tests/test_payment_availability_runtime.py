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
 class WP_REST_Request {
   public $headers = [], $body = '{}';
   public function __construct($headers = [], $route = '') { $this->headers = is_array($headers) ? $headers : []; }
   public function get_header($key) { return $this->headers[strtolower($key)] ?? ''; }
   public function set_header($key, $value) { $this->headers[strtolower($key)] = $value; }
   public function set_body($body) { $this->body = $body; }
   public function get_json_params() { return json_decode($this->body, true); }
 }
 class WP_REST_Response {
   public $headers = [];
   public function __construct(public $data, public $status) {}
   public function header($key, $value) { $this->headers[$key] = $value; }
 }
 class WP_Error {
   public function __construct(public $code, public $message, public $data = []) {}
   public function get_error_code() { return $this->code; }
   public function get_error_data() { return $this->data; }
   public function get_error_message() { return $this->message; }
 }
 class WC_Order {
   public function __construct(public $currency = 'USD', public $rail = 'tempo-mpp') {}
   public $meta = [];
   public function get_currency() { return $this->currency; }
   public function get_meta($key, $single) { return $this->meta[$key] ?? ($key === '_agentcart_payment_rail' ? $this->rail : ''); }
   public function get_payment_method() { return $this->rail; }
   public function get_id() { return 1; }
   public function get_order_number() { return 'one'; }
   public function update_meta_data($key, $value) { $this->meta[$key] = $value; }
   public function save() {}
   public function read_meta_data($force) {}
   public function get_data_store() { return new class { public function read($order) {} }; }
 }
 function is_wp_error($value) { return $value instanceof WP_Error; }
 function current_user_can($capability) { return $capability === 'manage_woocommerce'; }
 function get_bloginfo($key) { return 'Fixture Shop'; }
 function wc_get_page_permalink($key) { return 'https://shop.example/terms'; }
 function WC() { return $GLOBALS['wc_fixture'] ?? (object) ['countries' => new class { public function get_base_country() { return 'US'; } }]; }
 function wc_get_orders($args) { return isset($GLOBALS['order_lookup']) ? ($GLOBALS['order_lookup'])($args) : []; }
 function wp_remote_retrieve_response_code($response) { return $GLOBALS['http_status'] ?? 200; }
 function wp_remote_retrieve_body($response) { return json_encode($response); }
 function add_action(...$args) {}
 function add_filter(...$args) { $GLOBALS['filters'][$args[0]][] = $args[1]; }
 function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
 function delete_option($key) { unset($GLOBALS['options'][$key]); }
 function update_option($key, $value, $autoload = false) { $GLOBALS['options'][$key] = $value; }
 function wp_unslash($value) { return $value; }
 function check_admin_referer($action) { if (empty($GLOBALS['nonce_valid'])) { throw new Exception('Invalid nonce'); } }
 if (!function_exists('has_filter')) { function has_filter($name) { return false; } }
 if (!function_exists('wc_get_products')) { function wc_get_products($args) { return []; } }
 if (!function_exists('wc_tax_enabled')) { function wc_tax_enabled() { return false; } }
 function get_posts($args) { return []; }
 function get_post($id) { return null; }
 if (!function_exists('get_page_by_path')) { function get_page_by_path($path) { return null; } }
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
   $GLOBALS['http_request'] = $args;
   if (!isset($GLOBALS['verifier_response'])) { throw new Exception('Unexpected network request'); }
   return $GLOBALS['verifier_response'];
 }
 function wp_remote_get(...$args) { throw new Exception('Unexpected network request'); }
 function invoke($name, ...$args) { return (new ReflectionMethod(AgentCart_ShopBridge::class, $name))->invoke(null, ...$args); }
 $GLOBALS['options'] = [
   'agentcart_shopbridge_payment_verifier_url' => 'https://8.8.8.8/verify',
   'agentcart_shopbridge_x402_network' => 'eip155:84532',
   'agentcart_shopbridge_x402_asset' => '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
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
        self.assertIn("x402-compatible", result["registry_protocols"])
        self.assertIsNone(result["requirement"])


    def capability_setup(self):
        return """
$GLOBALS['options']['agentcart_shopbridge_payment_verifier_token'] = 'fixture-secret';
$GLOBALS['verifier_response'] = ['ok' => true, 'enabled_rails' => ['x402-compatible'], 'x402' => [
 'configured' => true, 'facilitator' => ['supported_kind_confirmed' => true],
 'mode' => 'settle', 'x402_version' => 2, 'scheme' => 'exact', 'networks' => [[
 'network' => 'eip155:84532', 'assets' => [[
 'asset' => '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
 'eip712_name' => 'USDC', 'eip712_version' => '2', 'decimals' => 6, 'currency' => 'USD']]]]]];
$GLOBALS['nonce_valid'] = true;
$_SERVER['REQUEST_METHOD'] = 'POST';
$_POST['agentcart_registry_action'] = 'check_verifier_capabilities';
invoke('maybe_handle_registry_action');
$GLOBALS['http_calls'] = 0;
"""

    def test_unready_and_malformed_capabilities_fail_closed(self):
        for mutation in (
            "$GLOBALS['verifier_response']['ok'] = false;",
            "unset($GLOBALS['verifier_response']['ok']);",
            "$GLOBALS['verifier_response']['ok'] = 'true';",
            "$GLOBALS['verifier_response']['x402']['configured'] = false;",
            "unset($GLOBALS['verifier_response']['x402']['configured']);",
            "$GLOBALS['verifier_response']['x402']['configured'] = 1;",
            "$GLOBALS['verifier_response']['x402']['facilitator']['supported_kind_confirmed'] = false;",
            "unset($GLOBALS['verifier_response']['x402']['facilitator']);",
            "$GLOBALS['verifier_response']['x402']['facilitator']['supported_kind_confirmed'] = 'true';",
        ):
            with self.subTest(mutation=mutation):
                result = self.run_plugin(self.capability_setup() + mutation + """
invoke('check_verifier_capabilities');
echo json_encode(['reason' => invoke('x402_unavailable_reason'), 'document' => invoke('x402_payment_required_document', ['currency' => 'USD'])]);
""")
                self.assertIn("verifier_x402_support_unconfirmed", result["reason"])
                self.assertIsNone(result["document"])

    def test_transport_failure_preserves_snapshot_but_success_revokes(self):
        result = self.run_plugin(self.capability_setup() + """
$before = get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION);
$response = $GLOBALS['verifier_response'];
$GLOBALS['verifier_response'] = new WP_Error('transport_failure', 'Transport unavailable.');
$message = invoke('check_verifier_capabilities');
$retained = get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION);
$GLOBALS['verifier_response'] = $response;
$GLOBALS['verifier_response']['x402']['configured'] = false;
invoke('check_verifier_capabilities');
echo json_encode(['before' => $before, 'retained' => $retained, 'message' => $message, 'reason' => invoke('x402_unavailable_reason')]);
""")
        self.assertEqual(result["before"], result["retained"])
        self.assertIn("failed", result["message"])
        self.assertIn("transport_failure", result["message"])
        self.assertIn("verifier_x402_support_unconfirmed", result["reason"])

    def test_timeout_clamp_and_legacy_value_fail_closed(self):
        result = self.run_plugin(self.capability_setup() + """
$GLOBALS['options'][AgentCart_ShopBridge::X402_MAX_TIMEOUT_SECONDS_OPTION] = 3600;
$reason = invoke('x402_unavailable_reason');
$document = invoke('x402_payment_required_document', ['currency' => 'USD']);
$GLOBALS['options'][AgentCart_ShopBridge::X402_MAX_TIMEOUT_SECONDS_OPTION] = AgentCart_ShopBridge::sanitize_x402_timeout_setting(3600);
$saved = invoke('x402_payment_required_document', ['currency' => 'USD']);
echo json_encode(['reason' => $reason, 'document' => $document, 'saved' => $saved,
 'low' => AgentCart_ShopBridge::sanitize_x402_timeout_setting(1), 'high' => AgentCart_ShopBridge::sanitize_x402_timeout_setting(301)]);
""")
        self.assertEqual(result["low"], 30)
        self.assertEqual(result["high"], 300)
        self.assertIn("x402_max_timeout_seconds", result["reason"])
        self.assertIsNone(result["document"])
        self.assertEqual(result["saved"]["accepts"][0]["maxTimeoutSeconds"], 300)

    def test_capability_action_and_v2_usd_quote(self):
        result = self.run_plugin(self.capability_setup() + """
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => 'bound'];
$requirements = invoke('payment_requirements', $quote);
echo json_encode(['requirements' => $requirements, 'http_calls' => $GLOBALS['http_calls'],
 'request' => $GLOBALS['http_request'], 'snapshot' => get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION)]);
""")
        self.assertEqual(result["http_calls"], 0)
        self.assertEqual(json.loads(result["request"][1]["body"]), {"operation": "capabilities"})
        self.assertEqual(result["request"][1]["headers"]["Authorization"], "Bearer fixture-secret")
        import base64
        req = result["requirements"]["x402"]
        doc = json.loads(base64.b64decode(req["payment_required_header_value"]))
        self.assertEqual(doc, req["payment_required"])
        self.assertEqual(doc["x402Version"], 2)
        self.assertEqual(doc["resource"]["mimeType"], "application/json")
        accepted = doc["accepts"][0]
        self.assertEqual(accepted["amount"], "12340000")
        self.assertEqual(accepted["network"], "eip155:84532")
        self.assertEqual(accepted["extra"], {"name": "USDC", "version": "2"})
        self.assertNotIn("maxAmountRequired", accepted)
        protocol = next(p for p in result["requirements"]["protocols"] if p["id"] == "x402-compatible")
        self.assertTrue(protocol["available"])
        self.assertEqual(protocol["refund_policy"], "unsupported_manual_only")

    def test_eur_and_changed_destination_fail_closed(self):
        result = self.run_plugin(self.capability_setup() + """
$eur = invoke('x402_unavailable_reason', ['currency' => 'EUR']);
$GLOBALS['options'][AgentCart_ShopBridge::X402_PAY_TO_OPTION] = '0x3333333333333333333333333333333333333333';
echo json_encode(['eur' => $eur, 'changed' => invoke('x402_unavailable_reason'),
 'snapshot' => get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION), 'http_calls' => $GLOBALS['http_calls']]);
""")
        self.assertEqual(result["eur"], "quote_currency_eur_does_not_match_x402_asset_currency_usd")
        self.assertEqual(result["changed"], "verifier_x402_support_unconfirmed")
        self.assertFalse(result["snapshot"])
        self.assertEqual(result["http_calls"], 0)

    def test_snapshot_operator_support_and_destination_changes(self):
        for mutation in (
            "$GLOBALS['options'][AgentCart_ShopBridge::PAYMENT_VERIFIER_URL_OPTION] = 'https://1.1.1.1/verify';",
            "$GLOBALS['options'][AgentCart_ShopBridge::X402_NETWORK_OPTION] = 'eip155:1';",
            "$GLOBALS['options'][AgentCart_ShopBridge::X402_ASSET_OPTION] = '0x1111111111111111111111111111111111111111';",
            "$GLOBALS['options'][AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION]['x402']['mode'] = 'disabled';",
            "$GLOBALS['options'][AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION]['x402']['networks'] = [];",
        ):
            with self.subTest(mutation=mutation):
                result = self.run_plugin(self.capability_setup() + mutation + """
echo json_encode(['reason' => invoke('x402_unavailable_reason'), 'http_calls' => $GLOBALS['http_calls']]);
""")
                self.assertIn("verifier_x402_support_unconfirmed", result["reason"])
                self.assertEqual(result["http_calls"], 0)

    def test_v2_receipt_transport_and_v1_header_rejection(self):
        result = self.run_plugin(self.capability_setup() + """
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => 'bound'];
$quote['payment_requirements'] = invoke('payment_requirements', $quote);
$signature = base64_encode(json_encode(['x402Version' => 2, 'payload' => ['signature' => 'fixture']]));
$receipt = invoke('payment_receipt_from_checkout_request', ['payment_receipt' => ['x402_payment_signature' => $signature]], new WP_REST_Request(), $quote);
$legacy = invoke('payment_receipt_from_checkout_request', [], new WP_REST_Request(['x-payment' => $signature]), $quote);
echo json_encode(['receipt' => $receipt, 'signature' => $signature, 'legacy' => $legacy]);
""")
        self.assertEqual(result["receipt"]["x402_payment_signature"], result["signature"])
        self.assertEqual(result["receipt"]["amount"], "12340000")
        self.assertEqual(result["receipt"]["status"], "authorized")
        self.assertEqual(result["legacy"], [])

    def test_x402_refund_is_manual_only_without_http(self):
        result = self.run_plugin(self.capability_setup() + """
$error = invoke('verify_refund_request', new WC_Order('USD', 'x402-compatible'), 100, 'return', 'x402-compatible', []);
echo json_encode(['error' => $error->code, 'data' => $error->data, 'http_calls' => $GLOBALS['http_calls']]);
""")
        self.assertEqual(result["error"], "x402_refund_unsupported")
        self.assertEqual(result["data"]["status"], 400)
        self.assertFalse(result["data"]["real_refund_verified"])
        self.assertEqual(result["http_calls"], 0)

    def test_signature_checkout_forwarding_and_response(self):
        result = self.run_plugin(self.capability_setup() + """
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => str_repeat('a', 64)];
$quote['payment_requirements'] = invoke('payment_requirements', $quote);
$document = $quote['payment_requirements']['x402']['payment_required'];
$contract_hash = invoke('payment_contract_hash', invoke('payment_verification_contract', $quote, 'x402-compatible'));
$nonce = invoke('x402_authorization_nonce', $quote['quote_hash'], $contract_hash, $document['resource']['url']);
$payload = ['x402Version' => 2, 'accepted' => $document['accepts'][0], 'payload' => ['signature' => '0xfixture', 'authorization' => ['nonce' => $nonce]]];
$signature = base64_encode(json_encode($payload));
$request = new WP_REST_Request(['payment-signature' => $signature]);
$receipt = invoke('payment_receipt_from_checkout_request', [], $request, $quote);
$GLOBALS['verifier_response'] = ['ok' => true, 'rail' => 'x402-compatible', 'real_settlement_verified' => true,
 'quote_hash' => $quote['quote_hash'], 'payment_contract_hash' => $receipt['payment_contract_hash'],
 'amount_cents' => 1234, 'currency' => 'USD', 'network' => $receipt['network'],
 'asset' => $receipt['asset'], 'pay_to' => $receipt['pay_to'], 'amount' => $receipt['amount'],
 'transaction_reference' => '0xtx', 'payment_response_header_value' => base64_encode(json_encode(['success' => true, 'transaction' => '0xtx', 'network' => $receipt['network']]))];
$verification = invoke('verify_payment_receipt', $quote, $receipt, ['rail' => 'x402-compatible'], $request);
$response = invoke('checkout_payment_response', ['state' => 'created'], $verification);
echo json_encode(['verification' => $verification, 'response' => $response,
 'forwarded' => json_decode($GLOBALS['http_request'][1]['body'], true), 'payload' => $payload]);
""")
        import base64
        self.assertEqual(result["verification"]["state"], "verified")
        forwarded = result["forwarded"]
        self.assertEqual(json.loads(base64.b64decode(forwarded["payment_receipt"]["x402_payment_signature"])), result["payload"])
        self.assertEqual(forwarded["expected"]["x402_payment_requirements"], result["payload"]["accepted"])
        self.assertTrue(json.loads(base64.b64decode(result["response"]["headers"]["PAYMENT-RESPONSE"]))["success"])

    def test_keccak_rate_boundary_vectors(self):
        vectors = {
            135: "34367dc248bbd832f4e3e69dfaac2f92638bd0bbd18f2912ba4ef454919cf446",
            136: "a6c4d403279fe3e0af03729caada8374b5ca54d8065329a3ebcaeb4b60aa386e",
            271: "132f47effd6c8b1b299efa53fe68aece77ec8ae4eb2e294f668eec94f76001e1",
        }
        for length, expected in vectors.items():
            with self.subTest(length=length):
                result = self.run_plugin(f"echo json_encode(bin2hex(invoke('x402_keccak256', str_repeat('a', {length}))));")
                self.assertEqual(result, expected)
        nonce = self.run_plugin("echo json_encode(invoke('x402_authorization_nonce', str_repeat('a', 64), str_repeat('b', 64), 'https://shop.example/' . str_repeat('a', 114)));")
        self.assertEqual(nonce, "0x797957b73a812296388f2a4949c7373c301db0a72979366e53b07bf7688150a5")

    def test_submitted_x402_draft_survives_capability_revocation(self):
        result = self.run_plugin(self.capability_setup() + """
define('ARRAY_A', 'ARRAY_A');
function wp_salt($scheme) { return 'local-recovery-fixture-salt'; }
function wc_get_order($id) { return $id === 1 ? $GLOBALS['draft'] : null; }
$wpdb = new class {
 public $posts = 'wp_posts', $postmeta = 'wp_postmeta', $comments = 'wp_comments', $commentmeta = 'wp_commentmeta', $prefix = 'wp_';
 public function prepare($sql, $tables) { return $tables; }
 public function get_results($tables, $format) { return array_map(fn($table) => ['TABLE_NAME' => $table, 'ENGINE' => 'InnoDB'], $tables); }
};
class RecoveryFixture {
 use AgentCart_ShopBridge_Checkout_Recovery;
 const API_NAMESPACE = 'agentcart/v1';
 const CHECKOUT_REQUEST_HASH_META = '_agentcart_checkout_request_hash';
 private static $checkout_recovery_active = false;
 private static function acquire_quote_lock($id) { return true; }
 private static function release_quote_lock($id) {}
 private static function quote_lock_option_name($id) { return 'fixture-lock'; }
 private static function connection_lock_owned($key) { return true; }
 private static function checkout_request_hash($body, $request) { return invoke('checkout_request_hash', $body, $request); }
 private static function payment_receipt_from_checkout_request($body, $request, $quote) { return invoke('payment_receipt_from_checkout_request', $body, $request, $quote); }
 private static function verify_payment_receipt($quote, $receipt, $body, $request, $draft) { return invoke('verify_payment_receipt', $quote, $receipt, $body, $request, $draft); }
 public static function retry($id) { return self::run_checkout_recovery($id, 'retry'); }
 public static function create_order($request) {
   $draft = $GLOBALS['draft'];
   if ($draft->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true) !== 'payment_verified') {
     throw new RuntimeException('Promotion requires a persisted verified payment.');
   }
   $verification = json_decode($draft->get_meta('_agentcart_payment_verification', true), true);
   $draft->update_meta_data(AgentCart_ShopBridge_Checkout_Store::STATE_META, 'completed');
   return invoke('checkout_payment_response', ['id' => 1, 'state' => 'created'], $verification);
 }
}
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => str_repeat('a', 64)];
$quote['payment_requirements'] = invoke('payment_requirements', $quote);
$document = $quote['payment_requirements']['x402']['payment_required'];
$contract_hash = invoke('payment_contract_hash', invoke('payment_verification_contract', $quote, 'x402-compatible'));
$nonce = invoke('x402_authorization_nonce', $quote['quote_hash'], $contract_hash, $document['resource']['url']);
$signature = base64_encode(json_encode(['payload' => ['authorization' => ['nonce' => $nonce]]]));
$request = new WP_REST_Request(['payment-signature' => $signature]);
$receipt = invoke('payment_receipt_from_checkout_request', [], $request, $quote);
$body = ['rail' => 'x402-compatible'];
$draft = new WC_Order('USD', 'x402-compatible');
$draft->meta = [
 '_agentcart_checkout_request_hash' => invoke('checkout_request_hash', $body, $request),
 '_agentcart_quote_snapshot' => json_encode($quote),
 '_agentcart_verifier_attempted_at' => '2026-10-01T00:00:00Z',
 AgentCart_ShopBridge_Checkout_Store::STATE_META => 'verification_pending',
 AgentCart_ShopBridge_Checkout_Store::QUOTE_META => 'quote-one',
];
$nonce_bytes = str_repeat('n', 12);
$tag = '';
$saved = ['body' => $body, 'headers' => ['payment-signature' => $signature]];
$ciphertext = openssl_encrypt(json_encode($saved), 'aes-256-gcm', hash('sha256', wp_salt('auth'), true), OPENSSL_RAW_DATA, $nonce_bytes, $tag);
$draft->meta['_agentcart_checkout_request'] = base64_encode($nonce_bytes . $tag . $ciphertext);
$GLOBALS['draft'] = $draft;
$GLOBALS['verifier_response'] = ['ok' => true, 'rail' => 'x402-compatible', 'real_settlement_verified' => true,
 'quote_hash' => $quote['quote_hash'], 'payment_contract_hash' => $receipt['payment_contract_hash'],
 'amount_cents' => 1234, 'currency' => 'USD', 'network' => $receipt['network'],
 'asset' => $receipt['asset'], 'pay_to' => $receipt['pay_to'], 'amount' => $receipt['amount'],
 'transaction_reference' => '0xtx', 'payment_response_header_value' => 'settled-response'];
delete_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION);
$new_draft = clone $draft;
unset($new_draft->meta['_agentcart_verifier_attempted_at']);
$new = invoke('verify_payment_receipt', $quote, $receipt, $body, $request, $new_draft);
$new_calls = $GLOBALS['http_calls'];
$response = RecoveryFixture::retry(1);
$recovered = json_decode($draft->get_meta('_agentcart_payment_verification', true), true);
$draft->meta['_agentcart_checkout_request_hash'] = 'tampered';
$tampered = invoke('verify_payment_receipt', $quote, $receipt, $body, $request, $draft);
echo json_encode(['new_error' => $new->get_error_code(), 'new_calls' => $new_calls,
 'recovered' => $recovered, 'response' => $response, 'http_calls' => $GLOBALS['http_calls'],
 'order_state' => $draft->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true),
 'new_attempted' => AgentCart_ShopBridge_Checkout_Store::verification_attempted($new_draft),
 'tampered_error' => $tampered->get_error_code()]);
""")
        self.assertEqual(result["new_error"], "agentcart_payment_rail_unavailable_for_quote")
        self.assertEqual(result["new_calls"], 0)
        self.assertFalse(result["new_attempted"])
        self.assertEqual(result["tampered_error"], "agentcart_recovery_request_mismatch")
        self.assertEqual(result["recovered"]["state"], "verified")
        self.assertTrue(result["recovered"]["real_settlement_verified"])
        self.assertEqual(result["response"]["headers"]["PAYMENT-RESPONSE"], "settled-response")
        self.assertEqual(result["http_calls"], 1)
        self.assertEqual(result["order_state"], "completed")

    def test_nonce_vector_and_mismatch_rejected_before_http(self):
        result = self.run_plugin(self.capability_setup() + """
$quote = ['id' => 'quote-one', 'currency' => 'USD', 'total_cents' => 1234, 'quote_hash' => str_repeat('a', 64)];
$quote['payment_requirements'] = invoke('payment_requirements', $quote);
$signature = base64_encode(json_encode(['payload' => ['authorization' => ['nonce' => '0x' . str_repeat('0', 64)]]]));
$receipt = invoke('payment_receipt_from_checkout_request', [], new WP_REST_Request(['payment-signature' => $signature]), $quote);
$error = invoke('call_payment_verifier', 'https://8.8.8.8/verify', $quote, $receipt, ['rail' => 'x402-compatible'], invoke('payment_verification_contract', $quote, 'x402-compatible'), null);
echo json_encode(['nonce' => invoke('x402_authorization_nonce', str_repeat('a', 64), str_repeat('b', 64), 'https://shop.example/wp-json/agentcart/v1/orders'),
 'error' => is_wp_error($error) ? $error->get_error_code() : null, 'http_calls' => $GLOBALS['http_calls']]);
""")
        self.assertEqual(result["nonce"], "0x68d8b9f6ce3e20691028d2c78b6904e615d34346820c101f4168c4f5a44c74d2")
        self.assertEqual(result["error"], "agentcart_x402_nonce_mismatch")
        self.assertEqual(result["http_calls"], 0)

    def test_registry_destination_is_conditional_and_non_x402_hash_stable(self):
        result = self.run_plugin("""
$configured = invoke('registry_claim');
$GLOBALS['options'][AgentCart_ShopBridge::X402_PAY_TO_OPTION] = '';
$before = invoke('registry_claim');
$hash = invoke('registry_claim_hash');
$GLOBALS['options'][AgentCart_ShopBridge::X402_NETWORK_OPTION] = 'unused-network';
$GLOBALS['options'][AgentCart_ShopBridge::X402_ASSET_OPTION] = 'unused-asset';
echo json_encode(['configured' => $configured, 'before' => $before, 'after' => invoke('registry_claim'),
 'hash_before' => $hash, 'hash_after' => invoke('registry_claim_hash')]);
""")
        self.assertEqual(result["configured"]["x402_network"], "eip155:84532")
        self.assertEqual(result["configured"]["x402_pay_to"], "0x" + "2" * 40)
        self.assertIn("x402-compatible", result["configured"]["supported_protocols"])
        self.assertNotIn("x402_network", result["before"])
        self.assertNotIn("x402-compatible", result["before"]["supported_protocols"])
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["hash_before"], result["hash_after"])

    def test_uninstall_removes_snapshot(self):
        result = self.run_plugin("""
define('WP_UNINSTALL_PLUGIN', true);
$GLOBALS['options'][AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION] = ['checked_at' => 'fixture'];
$wpdb = new class {
 public $options = 'wp_options';
 public function esc_like($value) { return $value; }
 public function prepare(...$args) { return ''; }
 public function query($sql) {}
};
function wp_clear_scheduled_hook($name) {}
require dirname($argv[1]) . '/uninstall.php';
echo json_encode(get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION));
""")
        self.assertFalse(result)

    def test_capability_action_rejects_bad_nonce_before_http(self):
        result = self.run_plugin("""
$_SERVER['REQUEST_METHOD'] = 'POST';
$_POST['agentcart_registry_action'] = 'check_verifier_capabilities';
try { invoke('maybe_handle_registry_action'); } catch (Exception $error) {}
echo json_encode(['snapshot' => get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION), 'http_calls' => $GLOBALS['http_calls'] ?? 0]);
""")
        self.assertFalse(result["snapshot"])
        self.assertEqual(result["http_calls"], 0)

    def test_capability_private_verifier_and_redirect_fail_closed(self):
        result = self.run_plugin(self.capability_setup() + """
$GLOBALS['options'][AgentCart_ShopBridge::PAYMENT_VERIFIER_URL_OPTION] = 'https://127.0.0.1/verify';
$private = invoke('maybe_handle_registry_action');
$private_calls = $GLOBALS['http_calls'];
$GLOBALS['options'][AgentCart_ShopBridge::PAYMENT_VERIFIER_URL_OPTION] = 'https://8.8.8.8/verify';
$GLOBALS['http_status'] = 302;
$redirect = invoke('maybe_handle_registry_action');
echo json_encode(['private' => $private, 'private_calls' => $private_calls, 'redirect' => $redirect,
 'snapshot' => get_option(AgentCart_ShopBridge::VERIFIER_CAPABILITIES_OPTION)]);
""")
        self.assertEqual(result["private"], "Verifier URL and token are required.")
        self.assertEqual(result["private_calls"], 0)
        self.assertEqual(result["redirect"], "Verifier capability response is invalid.")
        self.assertFalse(result["snapshot"])
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
            ("tempo-mpp", "x402-compatible", "USD", "x402_refund_unsupported"),
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

    def checkout_reliability(self, mutation, rail="tempo-mpp"):
        setup = r'''
define('ARRAY_A', 'ARRAY_A');
class WooCommerce {}
class WC_Product {
 public function get_id() { return 7; }
 public function get_status() { return 'publish'; }
 public function get_type() { return 'simple'; }
 public function get_category_ids() { return []; }
 public function get_attributes() { return []; }
 public function get_meta($key, $single) { return ''; }
 public function is_in_stock() { return true; }
 public function managing_stock() { return false; }
 public function is_sold_individually() { return false; }
 public function __call($name, $args) { return ''; }
}
class WC_Tax {
 public static function get_rates($class) { return []; }
 public static function get_rate_percent_value($id) { return 10; }
}
class CheckoutCart {
 public $price = 8.0, $shipping = 2.0, $tax = 0.0;
 public function empty_cart() {}
 public function add_to_cart($id, $quantity) { return 'product-seven'; }
 public function calculate_shipping() {}
 public function calculate_totals() {}
 public function needs_shipping() { return false; }
 public function get_cart() {
   return [['data' => $GLOBALS['product'], 'quantity' => 1, 'line_total' => $this->price - $this->tax,
     'line_tax' => $this->tax, 'line_tax_data' => ['total' => $this->tax ? [1 => $this->tax] : []]]];
 }
 public function get_shipping_total() { return $this->shipping; }
 public function get_shipping_tax() { return 0; }
 public function get_shipping_taxes() { return []; }
 public function get_taxes() { return []; }
 public function get_total($context) { return $this->price + $this->shipping; }
}
class CheckoutDraft extends WC_Order {
 public function set_status($status) {}
}
function wc_get_product($id) { return $id === 7 ? $GLOBALS['product'] : null; }
function wc_get_order($id) { return null; }
function wc_get_price_including_tax($product, $args) { return 8; }
function wp_strip_all_tags($text) { return strip_tags($text); }
function sanitize_title($text) { return strtolower(str_replace(' ', '-', $text)); }
function wp_get_post_terms(...$args) { return []; }
function wp_salt($scheme) { return 'local-checkout-reliability-salt'; }
function get_transient($key) { return $GLOBALS['transients'][$key] ?? false; }
function wp_next_scheduled(...$args) { return false; }
function wp_schedule_single_event($time, $hook, $args) { $GLOBALS['scheduled_events'][] = $hook; return true; }
$wpdb = new class {
 public $posts = 'wp_posts', $postmeta = 'wp_postmeta', $comments = 'wp_comments', $commentmeta = 'wp_commentmeta', $prefix = 'wp_';
 public function prepare($sql, ...$args) { return isset($args[0]) && is_array($args[0]) ? $args[0] : $sql; }
 public function get_results($tables, $format) { return array_map(fn($table) => ['TABLE_NAME' => $table, 'ENGINE' => 'InnoDB'], $tables); }
 public function get_var($sql) { return '1'; }
};
$GLOBALS['product'] = new WC_Product();
$GLOBALS['cart'] = new CheckoutCart();
$GLOBALS['wc_fixture'] = new class {
 public $cart, $customer = null, $session = null, $countries;
 public function __construct() {
   $this->cart = $GLOBALS['cart'];
   $this->countries = new class { public function get_base_country() { return 'DE'; } };
 }
 public function shipping() { return null; }
};
'''
        body = (self.capability_setup() if rail == "x402-compatible" else "") + "$rail = " + json.dumps(rail) + ";" + r'''
$GLOBALS['options']['agentcart_shopbridge_product_exposure_mode'] = 'all';
$GLOBALS['options']['agentcart_shopbridge_stock_hold_mode'] = 'off';
$GLOBALS['options']['agentcart_shopbridge_checkout_mode'] = 'external_verifier_only';
$GLOBALS['options']['agentcart_shopbridge_tempo_recipient'] = '0x3333333333333333333333333333333333333333';
$GLOBALS['verifier_response'] = new WP_Error('fixture_payment_boundary', 'The local fixture stops at payment verification.');
$quote = invoke('quote_from_cart', $GLOBALS['cart']);
$quote += ['id' => 'quote-checkout', 'currency' => 'USD', 'expires_at' => gmdate('c', time() + 300),
 'ship_to' => ['first_name' => 'Test', 'last_name' => 'Buyer', 'address_1' => 'Teststrasse 1', 'city' => 'Berlin',
   'postcode' => '10115', 'country' => 'DE', 'email' => 'buyer@example.test']];
''' + mutation + r'''
$quote['quote_hash'] = invoke('quote_hash', $quote);
$quote['payment_requirements'] = invoke('payment_requirements', $quote);
$GLOBALS['transients'][AgentCart_ShopBridge::QUOTE_TRANSIENT_PREFIX . $quote['id']] = $quote;
$draft = new CheckoutDraft();
$draft->meta[AgentCart_ShopBridge_Checkout_Store::STATE_META] = 'reserved';
$draft->meta['_agentcart_quote_snapshot'] = json_encode($quote);
$GLOBALS['order_lookup'] = fn($args) => isset($args['status']) && ($args['meta_key'] ?? '') === AgentCart_ShopBridge_Checkout_Store::QUOTE_META ? [$draft] : [];
$contract = invoke('payment_verification_contract_with_hash', $quote, $rail);
$request = new WP_REST_Request();
$request->set_body(json_encode(['agentcart_order_id' => 'checkout-reliability', 'merchant_quote_id' => $quote['id'], 'quote_hash' => $quote['quote_hash'],
 'payment_receipt' => ['id' => 'payment-checkout', 'rail' => $rail, 'amount_cents' => $quote['total_cents'],
   'currency' => 'USD', 'quote_hash' => $quote['quote_hash'], 'payment_contract_hash' => $contract['payment_contract_hash'],
   'x402_payment_signature' => base64_encode(json_encode(['payload' => ['authorization' => ['nonce' => '0x' . str_repeat('0', 64)]]]))]]));
$result = AgentCart_ShopBridge::create_order($request);
echo json_encode(['error' => is_wp_error($result) ? $result->get_error_code() : null,
 'data' => is_wp_error($result) ? $result->get_error_data() : null, 'http_calls' => $GLOBALS['http_calls'] ?? 0,
 'attempted' => AgentCart_ShopBridge_Checkout_Store::verification_attempted($draft), 'scheduled_events' => $GLOBALS['scheduled_events'] ?? []]);
'''
        return self.run_plugin(body, setup)

    def test_checkout_rejects_incomplete_delivery_address_before_payment(self):
        result = self.checkout_reliability("unset($quote['ship_to']['address_1'], $quote['ship_to']['postcode']);")
        self.assertEqual(result["error"], "agentcart_ship_to_incomplete")
        self.assertEqual(result["data"]["recovery"]["reason"], "delivery_address_incomplete")
        self.assertEqual(result["http_calls"], 0)

    def test_checkout_rejects_live_money_drift_before_payment(self):
        for field, value, reason in (("price", 9, "price_changed"), ("shipping", 3, "shipping_changed"), ("tax", 0.5, "tax_changed")):
            with self.subTest(field=field):
                result = self.checkout_reliability(f"$GLOBALS['cart']->{field} = {value};")
                self.assertEqual(result["error"], "agentcart_quote_" + reason)
                self.assertEqual(result["data"]["recovery"]["reason"], reason)
                self.assertEqual(result["http_calls"], 0)

    def test_wrong_x402_nonce_never_marks_or_schedules_payment_attempt(self):
        result = self.checkout_reliability("", rail="x402-compatible")
        self.assertEqual(result["error"], "agentcart_x402_nonce_mismatch")
        self.assertEqual(result["data"]["status"], 402)
        self.assertEqual(result["http_calls"], 0)
        self.assertFalse(result["attempted"])
        self.assertNotIn("agentcart_shopbridge_recover_checkout", result["scheduled_events"])

    def test_outbound_payment_transport_failure_keeps_recovery_eligibility(self):
        result = self.checkout_reliability("")
        self.assertEqual(result["error"], "agentcart_payment_verifier_failed")
        self.assertEqual(result["http_calls"], 1)
        self.assertTrue(result["attempted"])
        self.assertIn("agentcart_shopbridge_recover_checkout", result["scheduled_events"])


if __name__ == "__main__":
    unittest.main()
