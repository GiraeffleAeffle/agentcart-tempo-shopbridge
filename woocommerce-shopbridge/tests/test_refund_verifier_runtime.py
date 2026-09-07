"""Run the real verifier-client trait against PHP HTTP/WordPress fixtures."""
import json
import pathlib
import subprocess
import unittest

TRAIT = pathlib.Path(__file__).resolve().parents[1] / "agentcart-shopbridge/includes/trait-agentcart-shopbridge-verifier-client.php"


class RefundVerifierRuntimeTests(unittest.TestCase):
    def verify(self, status, verified=True):
        script = r'''<?php
define('ABSPATH', __DIR__);
require $argv[1];
class WP_Error {
    public function __construct(public $code, public $message, public $data=[]) {}
}
function is_wp_error($v) { return $v instanceof WP_Error; }
function sanitize_text_field($v) { return $v; }
function sanitize_key($v) { return $v; }
function wp_json_encode($v) { return json_encode($v); }
function wp_remote_retrieve_response_code($v) { return 200; }
function wp_remote_retrieve_body($v) { return json_encode($v); }
function wp_remote_post($url, $args) { return json_decode(getenv('REFUND_FIXTURE'), true); }
class WC_Order {
    function get_id() { return 1; }
    function get_order_number() { return '1'; }
    function get_meta($key, $single) { return ''; }
    function get_payment_method() { return 'stripe'; }
}
class Client {
    use AgentCart_ShopBridge_Verifier_Client;
    static function merchant() { return []; }
    static function tempo_settlement_asset() { return []; }
    static function tempo_network() { return 'testnet'; }
    static function tempo_recipient() { return ''; }
    static function stripe_profile_id() { return 'profile'; }
    static function payment_verifier_token() { return ''; }
    static function normalize_payment_verifier_url($url) { return $url; }
    static function payment_verifier_url_allows_private_networks() { return false; }
    static function run() { return self::call_refund_verifier('https://verifier.example', new WC_Order(), 100, 'USD', 'return', 'stripe-card-mpp', 'quote', 'pi_test', [], ['requested_reference'=>'one']); }
}
$result = Client::run();
echo json_encode($result instanceof WP_Error ? ['error'=>$result->code,'detail'=>$result->data] : $result);
'''
        import os
        response = dict(ok=True, amount_cents=100, currency="USD", quote_hash="quote",
                        original_transaction_reference="pi_test", rail="stripe-card-mpp",
                        refund_reference="re_test", refund_status=status, real_refund_verified=verified)
        # php reads the script from stdin; trait path is an ordinary argv value.
        result = subprocess.run(["php", "--", str(TRAIT)], input=script, text=True, capture_output=True,
                                env={**os.environ, "REFUND_FIXTURE": json.dumps(response)})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_provider_status_controls_success_even_when_boolean_claims_success(self):
        for status in ("pending", "requires_action", "failed", "canceled", ""):
            with self.subTest(status=status):
                result = self.verify(status)
                self.assertEqual(result["error"], "agentcart_refund_pending_or_failed")
                self.assertEqual(result["detail"]["refund_status"], status or "unknown")
        result = self.verify("succeeded")
        self.assertTrue(result["real_refund_verified"])
        self.assertEqual(result["state"], "rail_refund_verified")

    def test_string_booleans_do_not_verify_real_money(self):
        self.assertEqual(self.verify("succeeded", "false")["error"], "agentcart_refund_not_real_verified")


if __name__ == "__main__": unittest.main()
