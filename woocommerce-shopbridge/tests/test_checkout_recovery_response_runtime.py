"""Exercise the manager retry action with persisted x402 recovery state."""
import json
import pathlib
import shutil
import subprocess
import unittest

TRAIT = pathlib.Path(__file__).resolve().parents[1] / "agentcart-shopbridge/includes/trait-agentcart-shopbridge-checkout-recovery.php"


@unittest.skipUnless(shutil.which("php"), "php is required")
class CheckoutRecoveryResponseRuntimeTests(unittest.TestCase):
    def test_x402_retry_response_is_rendered_without_fatal(self):
        script = r'''<?php
 define('ABSPATH', '/');
 class WP_REST_Request implements ArrayAccess {
   public $params = [], $headers = [], $body;
   public function __construct(...$args) {}
   public function set_param($key, $value) { $this->params[$key] = $value; }
   public function set_header($key, $value) { $this->headers[$key] = $value; }
   public function set_body($body) { $this->body = $body; }
   public function get_json_params() { return json_decode($this->body, true); }
   public function offsetExists($key): bool { return isset($this->params[$key]); }
   public function offsetGet($key): mixed { return $this->params[$key]; }
   public function offsetSet($key, $value): void { $this->params[$key] = $value; }
   public function offsetUnset($key): void { unset($this->params[$key]); }
 }
 class WP_REST_Response {
   public function __construct(public $data) {}
   public function get_data() { return $this->data; }
 }
 function current_user_can($cap) { return true; }
 function check_admin_referer($action) {}
 function sanitize_key($text) { return $text; }
 function sanitize_text_field($text) { return $text; }
 function wp_unslash($text) { return $text; }
 function wp_json_encode($value) { return json_encode($value); }
 function is_wp_error($value) { return false; }
 function esc_html($text) { return $text; }
 function esc_html__($text, $domain) { return $text; }
 function wp_die($message, ...$args) { throw new RuntimeException($message); }
 $GLOBALS['order'] = new class {
   public $state = 'compensation_required';
   public function get_meta($key, $single) {
     return match ($key) {
       'state' => $this->state,
       'quote' => 'quote-one',
       'request_hash' => 'hash',
       '_agentcart_payment_verification' => '{"rail":"x402-compatible","payment_response":"fixture"}',
       default => ''
     };
   }
   public function get_data_store() { return new class { public function read($order) {} }; }
   public function read_meta_data($force) {}
 };
 function wc_get_order($id) { return $id === 7 ? $GLOBALS['order'] : null; }
 class AgentCart_ShopBridge_Checkout_Store {
   const STATE_META = 'state';
   const QUOTE_META = 'quote';
   public static function require_transactional_storage() { return true; }
   public static function started($order) { return true; }
   public static function quote($order) { return ['id' => 'quote-one']; }
   public static function request($order) { return ['body' => ['rail' => 'x402-compatible']]; }
 }
 require $argv[1];
 class RecoveryFixture {
   use AgentCart_ShopBridge_Checkout_Recovery;
   const API_NAMESPACE = 'agentcart/v1';
   const CHECKOUT_REQUEST_HASH_META = 'request_hash';
   private static $checkout_recovery_active = false;
   private static function authorize_support_diagnostics($request) { return true; }
   private static function acquire_quote_lock($id) { return true; }
   private static function release_quote_lock($id) {}
   private static function checkout_request_hash($body, $request) { return 'hash'; }
   public static function create_order($request) {
     $GLOBALS['order']->state = 'completed';
     return new WP_REST_Response(['id' => 7, 'state' => 'created']);
   }
 }
 $_POST = ['order_id' => 7, 'recovery_action' => 'retry'];
 try { RecoveryFixture::handle_checkout_recovery_action(); }
 catch (RuntimeException $message) {
   echo json_encode(['message' => $message->getMessage(), 'state' => $GLOBALS['order']->state]);
 }
'''
        result = subprocess.run(["php", "--", str(TRAIT)], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"message": "Recovery state: created", "state": "completed"})
