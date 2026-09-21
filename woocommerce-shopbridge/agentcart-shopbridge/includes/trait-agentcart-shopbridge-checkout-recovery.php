<?php
/**
 * Manager recovery and bounded retries for persisted checkout intents.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

trait AgentCart_ShopBridge_Checkout_Recovery {
    /**
     * Whether a manager's durable compensation intent is invoking refunds.
     *
     * @var bool
     */
    private static $checkout_compensation_active = false;
    public static function checkout_recovery_queue(WP_REST_Request $request) {
        $allowed = self::authorize_support_diagnostics($request);
        if (is_wp_error($allowed)) {
            return $allowed;
        }
        return AgentCart_ShopBridge_Checkout_Store::queue(intval($request->get_param('page') ?: 1));
    }

    public static function recover_checkout(WP_REST_Request $request) {
        // Also enforce capability for direct PHP callers and admin forms.
        $allowed = self::authorize_support_diagnostics($request);
        if (is_wp_error($allowed)) {
            return $allowed;
        }
        $body = $request->get_json_params();
        $action = is_array($body) ? ($body['action'] ?? 'retry') : 'retry';
        if (!in_array($action, ['retry', 'compensate'], true)) {
            return new WP_Error('agentcart_recovery_action_invalid', 'Choose retry or compensate.', ['status' => 400]);
        }
        return self::run_checkout_recovery(intval($request['id']), $action);
    }

    private static function run_checkout_recovery($order_id, $action) {
        $storage = AgentCart_ShopBridge_Checkout_Store::require_transactional_storage();
        if (is_wp_error($storage)) {
            return $storage;
        }
        $order = wc_get_order($order_id);
        if (!$order || !AgentCart_ShopBridge_Checkout_Store::started($order)
            || $order->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true) === '') {
            return new WP_Error('agentcart_recovery_not_found', 'Checkout recovery case not found.', ['status' => 404]);
        }
        $quote_id = (string) $order->get_meta(AgentCart_ShopBridge_Checkout_Store::QUOTE_META, true);
        $lock = self::acquire_quote_lock($quote_id);
        if (is_wp_error($lock)) {
            return $lock;
        }
        try {
            $order->get_data_store()->read($order);
            $order->read_meta_data(true);
            $state = (string) $order->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true);
            if (in_array($state, ['completed', 'compensated'], true)) {
                return ['order_id' => $order_id, 'state' => $state];
            }
            if ($state === 'compensating' && $action !== 'compensate') {
                return new WP_Error('agentcart_checkout_compensating', 'Reconcile the existing compensation; this checkout cannot resume.', ['status' => 409]);
            }
            $quote = AgentCart_ShopBridge_Checkout_Store::quote($order);
            $saved = AgentCart_ShopBridge_Checkout_Store::request($order);
            if (!is_array($quote) || !is_array($saved) || !is_array($saved['body'] ?? null)) {
                return new WP_Error('agentcart_recovery_request_unavailable', 'The original recovery request cannot be decrypted. Restore the original WordPress auth salts and reconcile provider evidence.', ['status' => 503]);
            }
            $retry = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/orders');
            $retry->set_header('content-type', 'application/json');
            foreach ($saved['headers'] ?? [] as $name => $value) {
                $retry->set_header($name, $value);
            }
            $retry->set_body(wp_json_encode($saved['body']));
            if (!hash_equals((string) $order->get_meta(self::CHECKOUT_REQUEST_HASH_META, true), self::checkout_request_hash($saved['body'], $retry))) {
                return new WP_Error('agentcart_recovery_request_mismatch', 'The recovery request does not match its original binding.', ['status' => 409]);
            }
            $verification = json_decode((string) $order->get_meta('_agentcart_payment_verification', true), true);
            if (!is_array($verification)) {
                if (!AgentCart_ShopBridge_Checkout_Store::verification_attempted($order)) {
                    return new WP_Error('agentcart_recovery_payment_not_attempted', 'No payment verification was attempted for this checkout.', ['status' => 409]);
                }
                // Resolve uncertain settlement before mutable stock checks. The
                // verifier receives exactly the original quote and evidence.
                $receipt = self::payment_receipt_from_checkout_request($saved['body'], $retry, $quote);
                $verification = self::verify_payment_receipt($quote, $receipt, $saved['body'], $retry);
                if (is_wp_error($verification)) {
                    AgentCart_ShopBridge_Checkout_Store::failure($order, $verification->get_error_code());
                    return $verification;
                }
                if (!self::connection_lock_owned(self::quote_lock_option_name($quote_id))) {
                    return new WP_Error('agentcart_checkout_lock_lost', 'Reconcile after database recovery.', ['status' => 503]);
                }
                AgentCart_ShopBridge_Checkout_Store::verified($order, $verification, $receipt);
            }
            if ($action === 'compensate') {
                if (($verification['real_settlement_verified'] ?? false) !== true) {
                    return new WP_Error('agentcart_compensation_payment_unverified', 'Compensation requires verified real settlement.', ['status' => 409]);
                }
                if ($state !== 'compensating') {
                    $order->update_meta_data('_agentcart_recovery_attempts', 0);
                }
                $order->update_meta_data(AgentCart_ShopBridge_Checkout_Store::STATE_META, 'compensating');
                $order->save();
                if ($state !== 'compensating') {
                    AgentCart_ShopBridge_Checkout_Store::schedule($order_id, 90);
                }
                $refund = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/orders/' . $order_id . '/refunds');
                $refund->set_param('id', $order_id);
                $refund->set_header('content-type', 'application/json');
                $refund->set_body(wp_json_encode([
                    'amount_cents' => intval($quote['total_cents']),
                    'rail' => (string) $verification['rail'],
                    'idempotency_key' => 'checkout-compensation-' . $order_id,
                    'requested_reference' => 'checkout-compensation-' . $order_id,
                    'reason' => 'Verified payment could not be fulfilled; merchant approved checkout compensation.',
                ]));
                self::$checkout_compensation_active = true;
                try {
                    $result = self::create_refund($refund);
                } finally {
                    self::$checkout_compensation_active = false;
                }
                if (is_wp_error($result)) {
                    return $result;
                }
                if (($result['real_refund_verified'] ?? false) !== true || ($result['refund_status'] ?? '') !== 'succeeded') {
                    return new WP_Error('agentcart_compensation_unconfirmed', 'Compensation is not confirmed by the payment rail.', ['status' => 409]);
                }
                $order->get_data_store()->read($order);
                $order->read_meta_data(true);
                $order->update_meta_data(AgentCart_ShopBridge_Checkout_Store::STATE_META, 'compensated');
                $order->delete_meta_data('_agentcart_checkout_request');
                $order->delete_meta_data('_agentcart_checkout_error');
                $order->set_status('cancelled');
                $order->save();
                wc_release_stock_for_order($order);
                self::release_stock_hold($quote_id, 'compensated');
                return ['order_id' => $order_id, 'state' => 'compensated', 'refund_reference' => $result['refund_reference']];
            }
        } finally {
            // Release before create_order, which takes checkout then quote locks.
            self::release_quote_lock($quote_id);
        }
        self::$checkout_recovery_active = true;
        try {
            return self::create_order($retry);
        } finally {
            self::$checkout_recovery_active = false;
        }
    }

    public static function recover_checkout_job($order_id) {
        $job_lock = self::connection_lock_name('recovery-job', (string) $order_id);
        if (is_wp_error(self::acquire_connection_lock($job_lock))) {
            return;
        }
        try {
            self::run_checkout_recovery_job($order_id);
        } finally {
            self::release_connection_lock($job_lock);
        }
    }

    private static function run_checkout_recovery_job($order_id) {
        $order = wc_get_order(intval($order_id));
        if (!$order || !in_array($order->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true), ['verifying', 'verification_pending', 'payment_verified', 'compensating'], true)) {
            return;
        }
        if (intval($order->get_meta('_agentcart_recovery_next_attempt_at', true)) > time()) {
            return;
        }
        $attempts = intval($order->get_meta('_agentcart_recovery_attempts', true));
        if ($attempts >= 3) {
            return;
        }
        $order->update_meta_data('_agentcart_recovery_attempts', $attempts + 1);
        $order->save();
        try {
            $action = $order->get_meta(AgentCart_ShopBridge_Checkout_Store::STATE_META, true) === 'compensating' ? 'compensate' : 'retry';
            self::run_checkout_recovery(intval($order_id), $action);
        } catch (Throwable $error) {
            // No provider body or request secrets in operational metadata.
            $order->update_meta_data('_agentcart_checkout_error', 'recovery_interrupted');
            $order->save();
        } finally {
            if ($attempts < 2) {
                AgentCart_ShopBridge_Checkout_Store::schedule($order_id, 300 * ($attempts + 1));
            }
        }
    }

    public static function operations_cron_schedules($schedules) {
        $schedules['agentcart_minute'] = ['interval' => 60, 'display' => 'ShopBridge recovery check'];
        return $schedules;
    }

    public static function ensure_operations_schedule() {
        if (!wp_next_scheduled('agentcart_shopbridge_operations_tick')) {
            wp_schedule_event(time() + 60, 'agentcart_minute', 'agentcart_shopbridge_operations_tick');
        }
    }

    public static function operations_tick() {
        $lock = self::connection_lock_name('operations', 'scheduler');
        if (is_wp_error(self::acquire_connection_lock($lock))) {
            return;
        }
        try {
            // Select eligible attempts directly: exhausted cases cannot starve newer work.
            // phpcs:disable WordPress.DB.SlowDBQuery -- Bounded operational scan across legacy and HPOS order stores.
            $query = [
                'type' => 'shop_order', 'limit' => 10, 'orderby' => 'ID', 'order' => 'ASC',
                'meta_query' => [
                    [
                        'key' => AgentCart_ShopBridge_Checkout_Store::STATE_META,
                        'value' => ['verifying', 'verification_pending', 'payment_verified', 'compensating'], 'compare' => 'IN',
                    ],
                    [
                        'relation' => 'OR', ['key' => '_agentcart_recovery_attempts', 'compare' => 'NOT EXISTS'],
                        ['key' => '_agentcart_recovery_attempts', 'value' => 3, 'compare' => '<', 'type' => 'NUMERIC'],
                    ],
                    [
                        'relation' => 'OR', ['key' => '_agentcart_recovery_next_attempt_at', 'compare' => 'NOT EXISTS'],
                        ['key' => '_agentcart_recovery_next_attempt_at', 'value' => time(), 'compare' => '<=', 'type' => 'NUMERIC'],
                    ],
                ],
            ];
            if (\Automattic\WooCommerce\Utilities\OrderUtil::custom_orders_table_usage_is_enabled()) {
                $orders = wc_get_orders($query);
            } else {
                // Legacy WC_Order_Query does not support meta_query; use its authoritative posts store.
                $ids = get_posts([
                    'post_type' => 'shop_order', 'post_status' => 'any', 'fields' => 'ids',
                    'numberposts' => 10, 'orderby' => 'ID', 'order' => 'ASC',
                    'meta_query' => $query['meta_query'],
                ]);
                $orders = array_filter(array_map('wc_get_order', $ids));
            }
            // phpcs:enable WordPress.DB.SlowDBQuery
            foreach ($orders as $order) {
                self::recover_checkout_job($order->get_id());
            }
            update_option('agentcart_shopbridge_scheduler_heartbeat', time(), false);
        } finally {
            self::release_connection_lock($lock);
        }
    }

    private static function operations_diagnostics() {
        $cases = AgentCart_ShopBridge_Checkout_Store::queue()['cases'];
        $counts = [];
        $oldest = 0;
        $exhausted = 0;
        foreach ($cases as $case) {
            $counts[$case['state']] = ($counts[$case['state']] ?? 0) + 1;
            $oldest = max($oldest, time() - $case['created_at']);
            if ($case['attempts'] >= 3) {
                ++$exhausted;
            }
        }
        $heartbeat = intval(get_option('agentcart_shopbridge_scheduler_heartbeat', 0));
        return [
            'external_scheduler_configured' => defined('AGENTCART_EXTERNAL_SCHEDULER') && AGENTCART_EXTERNAL_SCHEDULER === true,
            'heartbeat_at' => $heartbeat,
            'heartbeat_fresh' => $heartbeat > 0 && $heartbeat <= time() && time() - $heartbeat <= 180,
            'next_tick_at' => wp_next_scheduled('agentcart_shopbridge_operations_tick') ?: null,
            'transactional_storage' => !is_wp_error(AgentCart_ShopBridge_Checkout_Store::require_transactional_storage()),
            'encrypted_recovery_available' => AgentCart_ShopBridge_Checkout_Store::encryption_available(),
            'sampled_unresolved_count' => count($cases),
            'counts' => $counts,
            'sample_limit_per_state' => 20,
            'exhausted_in_sample' => $exhausted,
            'oldest_age_seconds_in_sample' => max(0, $oldest),
            'attention_required' => count($cases) > 0,
        ];
    }

    public static function handle_checkout_recovery_action() {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('WooCommerce manager access is required.', 'agentcart-shopbridge'));
        }
        check_admin_referer('agentcart_checkout_recovery');
        $request = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/checkout-recovery');
        $request->set_param('id', intval($_POST['order_id'] ?? 0));
        $request->set_header('content-type', 'application/json');
        $request->set_body(wp_json_encode(['action' => sanitize_key(wp_unslash($_POST['recovery_action'] ?? 'retry'))]));
        $result = self::recover_checkout($request);
        $message = is_wp_error($result) ? $result->get_error_message() : 'Recovery state: ' . sanitize_text_field($result['state'] ?? 'updated');
        wp_die(esc_html($message), esc_html__('Checkout recovery', 'agentcart-shopbridge'), ['response' => 200, 'back_link' => true]);
    }

    private static function render_checkout_recovery_panel() {
        $queue = AgentCart_ShopBridge_Checkout_Store::queue();
        ?>
        <h3>Checkout recovery</h3>
        <p>Interrupted checkouts retain their original payment request. Retry resumes that request. Refund payment permanently stops checkout and requests the full original amount back to its original payer. Pending refunds stay in the queue until verified.</p>
        <?php if (!$queue['cases']) : ?>
            <p>No unresolved checkouts.</p>
        <?php else : ?>
            <table class="widefat striped">
                <thead><tr><th>Order</th><th>State</th><th>Amount</th><th>Actions</th></tr></thead>
                <tbody>
                    <?php foreach ($queue['cases'] as $case) : ?>
                        <tr>
                            <td><?php echo esc_html((string) $case['order_id']); ?></td>
                            <td><?php echo esc_html($case['state']); ?></td>
                            <td><?php echo esc_html($case['total'] . ' ' . $case['currency']); ?></td>
                            <td>
                                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                                    <?php wp_nonce_field('agentcart_checkout_recovery'); ?>
                                    <input type="hidden" name="action" value="agentcart_checkout_recovery" />
                                    <input type="hidden" name="order_id" value="<?php echo esc_attr((string) $case['order_id']); ?>" />
                                    <?php if ($case['state'] !== 'compensating') : ?>
                                        <button class="button" name="recovery_action" value="retry">Retry checkout</button>
                                    <?php endif; ?>
                                    <?php if ($case['verified']) : ?>
                                        <button class="button" name="recovery_action" value="compensate"><?php echo $case['state'] === 'compensating' ? 'Reconcile refund' : 'Refund payment'; ?></button>
                                    <?php endif; ?>
                                </form>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <p>Up to 20 cases per state. The manager-only checkout-recovery API supports further pages.</p>
        <?php
        endif;
    }
}
