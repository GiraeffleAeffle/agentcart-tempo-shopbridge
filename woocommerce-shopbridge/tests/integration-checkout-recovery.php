<?php
// Run with wp eval-file in an isolated, seeded WooCommerce database only.
if (getenv('AGENTCART_CHECKOUT_INTEGRATION') !== '1') {
    throw new RuntimeException('This harness requires an explicitly isolated test shop.');
}
define('AGENTCART_PAYMENT_VERIFIER_URL', 'https://verifier.example.com/verify');
define('AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL', true);
add_filter('pre_wp_mail', '__return_true');
function ac_assert($ok, $message) {
    if (!$ok) { throw new RuntimeException($message); }
    echo "PASS $message\n";
}
function ac_ok($result) {
    if (is_wp_error($result)) { throw new RuntimeException($result->get_error_code() . ': ' . $result->get_error_message()); }
    return $result;
}
function ac_request($body, $path = '/agentcart/v1/orders') {
    $r = new WP_REST_Request('POST', $path);
    $r->set_header('content-type', 'application/json');
    $r->set_body(wp_json_encode($body));
    return $r;
}
function ac_private($name, ...$args) {
    return (new ReflectionMethod(AgentCart_ShopBridge::class, $name))->invoke(null, ...$args);
}
function ac_product($stock = 5) {
    $p = new WC_Product_Simple();
    $p->set_name('Recovery integration fixture');
    $p->set_status('publish');
    $p->set_regular_price('8.00');
    $p->set_price('8.00');
    $p->set_manage_stock(true);
    $p->set_stock_quantity($stock);
    $p->set_tax_status('none');
    $p->update_meta_data('_agentcart_enabled', 'yes');
    $p->update_meta_data('_agentcart_max_quantity', 10);
    $p->save();
    return $p;
}
function ac_quote($p, $quantity = 1, $final = true) {
    $address = ['country' => 'DE', 'postcode' => '10115'];
    if ($final) { $address += ['first_name' => 'Test', 'last_name' => 'Buyer', 'address_1' => 'Teststrasse 1', 'city' => 'Berlin', 'email' => 'buyer@example.test']; }
    return ac_ok(AgentCart_ShopBridge::quote(ac_request(['items' => [['product_id' => $p->get_id(), 'quantity' => $quantity]], 'ship_to' => $address], '/agentcart/v1/quote')));
}
function ac_checkout($quote) {
    $key = 'test-' . wp_generate_uuid4();
    $contract = ac_private('payment_verification_contract', $quote, 'tempo-mpp');
    return ac_request([
        'agentcart_order_id' => $key, 'merchant_quote_id' => $quote['id'], 'quote_hash' => $quote['quote_hash'],
        'approval_id' => 'approved-test',
        'payment_receipt' => [
            'id' => 'payment-' . $key, 'rail' => 'tempo-mpp', 'amount_cents' => $quote['total_cents'],
            'currency' => $quote['currency'], 'quote_hash' => $quote['quote_hash'],
            'payment_contract_hash' => ac_private('payment_contract_hash', $contract),
        ],
    ]);
}
function ac_recover($id, $action = 'retry') {
    $r = ac_request(['action' => $action], '/agentcart/v1/checkout-recovery/' . $id);
    $r->set_param('id', $id);
    return AgentCart_ShopBridge::recover_checkout($r);
}
wp_set_current_user(1);
update_option('agentcart_shopbridge_stock_hold_mode', 'hard');
update_option('agentcart_shopbridge_product_exposure_mode', 'product_opt_in');
$payment_calls = 0;
$refund_calls = 0;
$refund_status = 'pending';
$lose_payment_response = false;
add_filter('pre_http_request', function ($pre, $args, $url) use (&$payment_calls, &$refund_calls, &$refund_status, &$lose_payment_response) {
    if ($url !== 'https://verifier.example.com/verify') { return new WP_Error('integration_network_disabled', 'External network disabled in checkout fixture.'); }
    $body = json_decode($args['body'], true);
    $expected = $body['expected'];
    if ($body['operation'] === 'refund') {
        $refund_calls++;
        $data = ['ok' => true, 'amount_cents' => $expected['amount_cents'], 'currency' => $expected['currency'],
            'quote_hash' => $expected['quote_hash'], 'original_transaction_reference' => $expected['original_transaction_reference'],
            'rail' => 'tempo-mpp', 'refund_reference' => 'refund-' . $body['refund']['requested_reference'],
            'refund_status' => $refund_status, 'real_refund_verified' => $refund_status === 'succeeded'];
    } else {
        $payment_calls++;
        if ($lose_payment_response) {
            $lose_payment_response = false;
            return new WP_Error('timeout', 'Simulated lost acknowledgement after settlement');
        }
        $data = ['ok' => true, 'real_settlement_verified' => true, 'amount_cents' => $expected['amount_cents'],
            'currency' => $expected['currency'], 'quote_hash' => $body['quote_hash'],
            'payment_contract_hash' => $body['payment_contract_hash'], 'rail' => 'tempo-mpp', 'network' => 'testnet',
            'payer_address' => '0x1111111111111111111111111111111111111111',
            'transaction_reference' => $body['payment_receipt']['id']];
    }
    return ['response' => ['code' => 200], 'headers' => [], 'body' => wp_json_encode($data)];
}, 10, 3);

$race_mode = getenv('AGENTCART_STOCK_RACE_MODE');
if ($race_mode === 'create') {
    echo ac_product(1)->get_id();
    return;
}
if ($race_mode === 'reserve') {
    $product = wc_get_product(intval(getenv('AGENTCART_STOCK_RACE_PRODUCT')));
    if (!$product || $product->get_name() !== 'Recovery integration fixture') { throw new RuntimeException('Wrong race fixture'); }
    $hold = AgentCart_ShopBridge_Checkout_Store::reserve(null, [
        'quote_id' => 'race-' . wp_generate_uuid4(), 'expires_at' => gmdate('c', time() + 300),
        'items' => [['product_id' => $product->get_id(), 'quantity' => 1]],
    ]);
    echo is_wp_error($hold) ? 'rejected' : 'held';
    return;
}

echo 'WooCommerce ' . WC_VERSION . ' HPOS=' . get_option('woocommerce_custom_orders_table_enabled') . "\n";
$p = ac_product(3);
$comparison = ac_quote($p, 2, false);
ac_assert($comparison['stock_reservation']['state'] === 'not_reserved', 'comparison quote does not hoard stock');
$quote = ac_quote($p, 2);
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
ac_assert($draft && $draft->get_status() === 'checkout-draft', 'final quote has an unpaid persistent draft');
ac_assert((int) wc_get_held_stock_quantity($p) === 2, 'native reservation visible to ordinary WooCommerce checkout');
$ordinary = wc_create_order(['status' => 'pending']);
$ordinary->add_product($p, 2);
$ordinary->save();
$blocked = false;
try { (new Automattic\WooCommerce\Checkout\Helpers\ReserveStock())->reserve_stock_for_order($ordinary, 5); }
catch (Throwable $e) { $blocked = true; }
ac_assert($blocked, 'ordinary checkout cannot reserve the same units');
$ordinary->update_status('cancelled');
$request = ac_checkout($quote);
$result = ac_ok(AgentCart_ShopBridge::create_order($request));
ac_assert((int) $result['id'] === $draft->get_id(), 'checkout promotes the same draft');
ac_assert((int) wc_get_product($p->get_id())->get_stock_quantity() === 1, 'payment reduces stock exactly once');
ac_assert((int) wc_get_held_stock_quantity($p) === 0, 'paid checkout releases native hold');
$replay = ac_ok(AgentCart_ShopBridge::create_order($request));
ac_assert($replay['state'] === 'idempotent_replay' && $payment_calls === 1, 'checkout replay does not verify or charge again');

// Interrupt after verification and after stock reduction inside promotion.
$p = ac_product(2);
$quote = ac_quote($p);
$request = ac_checkout($quote);
$crash = function ($id) { if (wc_get_order($id)->get_created_via() === 'agentcart-shopbridge') { throw new RuntimeException('injected promotion crash'); } };
add_action('woocommerce_payment_complete', $crash, 100);
$failed = AgentCart_ShopBridge::create_order($request);
ac_assert(is_wp_error($failed) && $failed->get_error_code() === 'agentcart_order_payment_completion_failed', 'failure injected after stock reduction');
remove_action('woocommerce_payment_complete', $crash, 100);
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
ac_assert($draft->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true) === 'compensation_required', 'verified failed promotion remains visible for recovery');
wc_delete_product_transients($p->get_id());
ac_assert((int) wc_get_product($p->get_id())->get_stock_quantity() === 2, 'transaction rolls back native stock reduction');
delete_transient(AgentCart_ShopBridge::QUOTE_TRANSIENT_PREFIX . $quote['id']);
$before = $payment_calls;
$recovered = ac_ok(ac_recover($draft->get_id()));
ac_assert((int) $recovered['id'] === $draft->get_id() && $payment_calls === $before, 'recovery uses saved payment checkpoint after transient loss');
ac_assert((int) wc_get_product($p->get_id())->get_stock_quantity() === 1, 'recovered order consumes stock exactly once');

// Lost verifier acknowledgement, then stock becomes unavailable.
$p = ac_product(1);
$quote = ac_quote($p);
$lose_payment_response = true;
$failed = AgentCart_ShopBridge::create_order(ac_checkout($quote));
ac_assert(is_wp_error($failed), 'lost settlement acknowledgement returns an error');
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
wc_update_product_stock($p, 0);
delete_transient(AgentCart_ShopBridge::QUOTE_TRANSIENT_PREFIX . $quote['id']);
$failed = ac_recover($draft->get_id());
ac_assert(is_wp_error($failed), 'recovery cannot fulfill unavailable stock');
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
ac_assert($draft->get_meta('_agentcart_payment_verification', true) !== '', 'unknown settlement is resolved before stock rejection');
wp_set_current_user(0);
ac_assert(is_wp_error(ac_recover($draft->get_id(), 'compensate')), 'anonymous caller cannot compensate checkout');
wp_set_current_user(1);
$pending = ac_recover($draft->get_id(), 'compensate');
ac_assert(is_wp_error($pending), 'pending rail refund is not reported as compensation');
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
ac_assert(count($draft->get_refunds()) === 0, 'pending compensation creates no completed WooCommerce refund');
ac_assert(is_wp_error(ac_recover($draft->get_id())), 'compensating checkout cannot resume fulfillment');
$refund_status = 'succeeded';
$compensated = ac_ok(ac_recover($draft->get_id(), 'compensate'));
ac_assert($compensated['state'] === 'compensated', 'successful rail refund completes compensation');
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
ac_assert(count($draft->get_refunds()) === 1, 'compensation creates exactly one WooCommerce refund');
$before = $refund_calls;
ac_ok(ac_recover($draft->get_id(), 'compensate'));
ac_assert($refund_calls === $before, 'completed compensation does not submit again');
ac_assert($draft->get_meta('_agentcart_checkout_request', true) === '', 'completed compensation erases encrypted payment credentials');

// A policy rejection must not schedule a future attempt to settle the receipt.
$p = ac_product(2);
$quote = ac_quote($p);
$request = ac_checkout($quote);
$p->update_meta_data('_agentcart_checkout_blocked', 'yes');
$p->save();
$before = $payment_calls;
ac_assert(is_wp_error(AgentCart_ShopBridge::create_order($request)), 'merchant policy rejection stops checkout');
$draft = AgentCart_ShopBridge_Checkout_Store::find($quote['id']);
AgentCart_ShopBridge::recover_checkout_job($draft->get_id());
ac_assert($payment_calls === $before, 'background recovery cannot settle a rejected request');
$queue = AgentCart_ShopBridge_Checkout_Store::queue();
ac_assert(strpos(wp_json_encode($queue), 'buyer@example.test') === false && strpos(wp_json_encode($queue), 'payment_receipt') === false, 'manager queue excludes address and payment request contents');
echo "CHECKOUT RECOVERY INTEGRATION PASSED\n";
