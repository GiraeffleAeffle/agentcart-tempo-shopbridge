<?php
/**
 * WooCommerce-native stock holds and durable, unpaid checkout drafts.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}

final class AgentCart_ShopBridge_Checkout_Store {
    const QUOTE_META = '_agentcart_reservation_quote_id';
    const STATE_META = '_agentcart_checkout_state';
    const PROVIDER = 'woocommerce-native';

    public static function init() {
        add_filter('agentcart_shopbridge_reserve_stock', [__CLASS__, 'reserve'], 100, 2);
        add_filter('agentcart_shopbridge_confirm_stock_reservation', [__CLASS__, 'confirm'], 100, 2);
        add_filter('agentcart_shopbridge_release_stock_reservation', [__CLASS__, 'release'], 100, 2);
    }

    public static function require_transactional_storage() {
        global $wpdb;
        $tables = [
            $wpdb->posts, $wpdb->postmeta, $wpdb->comments, $wpdb->commentmeta,
            $wpdb->prefix . 'woocommerce_order_items', $wpdb->prefix . 'woocommerce_order_itemmeta',
            $wpdb->prefix . 'wc_product_meta_lookup', $wpdb->prefix . 'wc_reserved_stock',
        ];
        if (class_exists('Automattic\\WooCommerce\\Utilities\\OrderUtil') && Automattic\WooCommerce\Utilities\OrderUtil::custom_orders_table_usage_is_enabled()) {
            foreach (['wc_orders', 'wc_orders_meta', 'wc_order_addresses', 'wc_order_operational_data'] as $name) {
                $tables[] = $wpdb->prefix . $name;
            }
        }
        $placeholders = implode(',', array_fill(0, count($tables), '%s'));
        // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared, WordPress.DB.PreparedSQLPlaceholders.UnfinishedPrepare -- The generated list contains only %s placeholders; all table names are bound values. Inspect live engine guarantees before settlement.
        $rows = $wpdb->get_results($wpdb->prepare("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ($placeholders)", $tables), ARRAY_A);
        if (!is_array($rows) || count($rows) !== count($tables)) {
            return new WP_Error('agentcart_transactional_storage_required', 'Checkout recovery requires readable InnoDB order, item, stock and note tables.', ['status' => 503]);
        }
        foreach ($rows as $row) {
            if (strtolower((string) $row['ENGINE']) !== 'innodb') {
                return new WP_Error('agentcart_transactional_storage_required', 'All WooCommerce order, item, stock and note tables must use InnoDB.', ['status' => 503]);
            }
        }
        return true;
    }

    public static function find($quote_id) {
        if (!$quote_id || !function_exists('wc_get_orders')) {
            return null;
        }
        // phpcs:disable WordPress.DB.SlowDBQuery -- Bounded private lookup by the quote binding; supports both WooCommerce datastores.
        $orders = wc_get_orders([
            'limit' => 1, 'type' => 'shop_order',
            'status' => ['checkout-draft', 'pending', 'on-hold', 'failed', 'cancelled', 'processing', 'completed', 'refunded'],
            'meta_key' => self::QUOTE_META, 'meta_value' => (string) $quote_id,
        ]);
        // phpcs:enable WordPress.DB.SlowDBQuery
        return $orders ? $orders[0] : null;
    }

    private static function draft($quote_id) {
        $existing = self::find($quote_id);
        if ($existing) {
            return $existing;
        }
        $order = wc_create_order(['created_via' => 'agentcart-reservation', 'status' => 'checkout-draft']);
        if (is_wp_error($order)) {
            return $order;
        }
        $order->update_meta_data(self::QUOTE_META, (string) $quote_id);
        $order->update_meta_data(self::STATE_META, 'reserved');
        $order->save();
        return $order;
    }

    public static function reserve($existing, $context) {
        if ($existing !== null) {
            return $existing;
        }
        $storage = self::require_transactional_storage();
        if (is_wp_error($storage)) {
            return $storage;
        }
        if (!class_exists('Automattic\\WooCommerce\\Checkout\\Helpers\\ReserveStock') || intval(get_option('woocommerce_schema_version', 0)) < 430) {
            return new WP_Error('agentcart_native_reservation_unavailable', 'WooCommerce native stock reservation is unavailable.', ['status' => 503]);
        }
        $order = self::draft($context['quote_id']);
        if (is_wp_error($order)) {
            return $order;
        }
        try {
            if ($order->get_meta('_agentcart_reservation_items_hash', true) !== '') {
                throw new RuntimeException('This reservation already exists.');
            }
            foreach ($context['items'] as $item) {
                $product = wc_get_product(intval($item['product_id']));
                if (!$product || !$order->add_product($product, intval($item['quantity']))) {
                    throw new RuntimeException('Unable to persist reservation items.');
                }
            }
            $order->update_meta_data('_agentcart_reservation_items_hash', hash('sha256', wp_json_encode($context['items'])));
            $order->update_meta_data('_agentcart_reservation_expires_at', $context['expires_at']);
            $order->save();
            self::hold($order, $context['expires_at']);
            return [
                'hold_id' => (string) $order->get_id(), 'provider' => self::PROVIDER,
                'reference' => (string) $order->get_id(), 'expires_at' => $context['expires_at'],
            ];
        } catch (Throwable $error) {
            wc_release_stock_for_order($order);
            $order->update_status('cancelled');
            return new WP_Error('agentcart_native_stock_unavailable', 'WooCommerce could not reserve the requested stock.', ['status' => 409]);
        }
    }

    private static function hold($order, $expires_at) {
        $seconds = strtotime((string) $expires_at) - time();
        if ($seconds <= 0) {
            throw new RuntimeException('Reservation expired.');
        }
        $expected = [];
        foreach ($order->get_items() as $item) {
            $product = $item->get_product();
            if ($product && $product->managing_stock() && !$product->backorders_allowed()) {
                $id = $product->get_stock_managed_by_id();
                $expected[$id] = ($expected[$id] ?? 0) + $item->get_quantity();
            }
        }
        // Core treats an unchanged UPDATE (zero affected rows) as a failed
        // reservation. Reuse a still-valid hold without repeating that UPDATE.
        if (self::has_native_rows($order, $expected, $expires_at)) {
            return;
        }
        $helper = new Automattic\WooCommerce\Checkout\Helpers\ReserveStock();
        $helper->reserve_stock_for_order($order, max(1, (int) ceil($seconds / 60)));
        // Filters may disable or shorten holds. A successful no-op must never
        // be advertised as a hard reservation.
        if (!self::has_native_rows($order, $expected, $expires_at)) {
            throw new RuntimeException('Native hold was not persisted through the quote expiry.');
        }
    }

    private static function has_native_rows($order, $expected, $expires_at) {
        global $wpdb;
        foreach ($expected as $id => $quantity) {
            // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching -- Read the actual core reservation at the required expiry, not cached stock.
            $held = $wpdb->get_var($wpdb->prepare("SELECT stock_quantity FROM {$wpdb->wc_reserved_stock} WHERE order_id=%d AND product_id=%d AND expires >= %s", $order->get_id(), $id, gmdate('Y-m-d H:i:s', strtotime($expires_at))));
            if ((float) $held < (float) $quantity) {
                return false;
            }
        }
        return true;
    }

    public static function confirm($existing, $context) {
        if ($existing !== null || ($context['reservation']['provider'] ?? '') !== self::PROVIDER) {
            return $existing;
        }
        $order = self::find($context['quote_id']);
        if (!$order || !in_array($order->get_status(), ['checkout-draft', 'pending'], true)
            || (string) $order->get_id() !== (string) $context['hold_id']) {
            return new WP_Error('agentcart_native_reservation_missing', 'The native stock reservation is no longer available.', ['status' => 409]);
        }
        try {
            // Reacquire atomically if an interrupted checkout outlived its hold.
            $until = gmdate('c', max(time() + 300, strtotime($context['reservation']['expires_at'] ?? '')));
            self::hold($order, $until);
        } catch (Throwable $error) {
            return new WP_Error('agentcart_native_reservation_lost', 'Stock could not be reserved for this checkout. Reconcile the payment before retrying.', ['status' => 409]);
        }
        return ['state' => 'confirmed', 'hold_id' => (string) $order->get_id(), 'provider' => self::PROVIDER];
    }

    public static function release($existing, $context) {
        if ($existing !== null || ($context['hold']['provider'] ?? '') !== self::PROVIDER) {
            return $existing;
        }
        $order = self::find($context['quote_id']);
        if ($order && $order->get_meta(self::STATE_META, true) === 'reserved') {
            wc_release_stock_for_order($order);
            $order->update_status('cancelled');
        }
        return ['state' => 'released'];
    }

    public static function remember_quote($quote) {
        $order = self::draft($quote['id']);
        if (is_wp_error($order)) {
            return $order;
        }
        $order->update_meta_data('_agentcart_quote_snapshot', wp_json_encode($quote));
        $order->set_currency($quote['currency']);
        $order->set_total($quote['total_cents'] / 100);
        $order->save();
        return $order;
    }

    public static function quote($order) {
        return $order ? json_decode((string) $order->get_meta('_agentcart_quote_snapshot', true), true) : null;
    }

    public static function started($order) {
        return $order && $order->get_meta('_agentcart_checkout_request_hash', true) !== '';
    }

    public static function encryption_available() {
        return function_exists('openssl_encrypt') && function_exists('openssl_decrypt')
            && in_array('aes-256-gcm', openssl_get_cipher_methods(), true);
    }

    public static function begin($quote, $body, WP_REST_Request $request, $request_hash, $key) {
        $order = self::find($quote['id']);
        if (!$order) {
            $order = self::remember_quote($quote);
        }
        if (is_wp_error($order)) {
            return $order;
        }
        $saved_hash = (string) $order->get_meta('_agentcart_checkout_request_hash', true);
        if ($saved_hash !== '' && !hash_equals($saved_hash, $request_hash)) {
            return new WP_Error('agentcart_checkout_recovery_conflict', 'This quote is bound to another checkout request.', ['status' => 409]);
        }
        if (in_array($order->get_meta(self::STATE_META, true), ['compensating', 'compensated'], true)) {
            return new WP_Error('agentcart_checkout_compensating', 'Checkout was stopped for payment compensation.', ['status' => 409]);
        }
        if ($saved_hash === '') {
            $payload = ['body' => $body, 'headers' => []];
            foreach (['idempotency-key', 'payment-signature', 'x-payment', 'payment-response'] as $name) {
                $payload['headers'][$name] = (string) $request->get_header($name);
            }
            if (!self::encryption_available()) {
                return new WP_Error('agentcart_recovery_storage_unavailable', 'Encrypted checkout recovery storage requires OpenSSL.', ['status' => 503]);
            }
            $nonce = random_bytes(12);
            $tag = '';
            $encrypted = openssl_encrypt(wp_json_encode($payload), 'aes-256-gcm', hash('sha256', wp_salt('auth'), true), OPENSSL_RAW_DATA, $nonce, $tag);
            if ($encrypted === false) {
                return new WP_Error('agentcart_recovery_storage_unavailable', 'Unable to persist the checkout recovery request.', ['status' => 503]);
            }
            // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_encode -- Binary authenticated ciphertext stored in textual order metadata.
            $order->update_meta_data('_agentcart_checkout_request', base64_encode($nonce . $tag . $encrypted));
            $order->update_meta_data('_agentcart_checkout_request_hash', $request_hash);
            $order->update_meta_data('_agentcart_order_id', (string) ($body['agentcart_order_id'] ?? $key));
            $order->update_meta_data('_agentcart_idempotency_key', $key);
            $order->update_meta_data('_agentcart_merchant_quote_id', $quote['id']);
            $order->update_meta_data('_agentcart_quote_hash', $quote['quote_hash']);
            $order->update_meta_data(self::STATE_META, 'intent_saved');
            $order->set_status('pending');
            $order->save();
        }
        return $order;
    }

    public static function request($order) {
        if (!function_exists('openssl_decrypt')) {
            return null;
        }
        // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_decode -- Decode only the private authenticated recovery ciphertext written above.
        $bytes = base64_decode((string) $order->get_meta('_agentcart_checkout_request', true), true);
        if ($bytes === false || strlen($bytes) < 29) {
            return null;
        }
        $clear = openssl_decrypt(substr($bytes, 28), 'aes-256-gcm', hash('sha256', wp_salt('auth'), true), OPENSSL_RAW_DATA, substr($bytes, 0, 12), substr($bytes, 12, 16));
        $payload = $clear === false ? null : json_decode($clear, true);
        return is_array($payload) ? $payload : null;
    }

    public static function verified($order, $verification, $receipt) {
        $order->update_meta_data('_agentcart_payment_verification', wp_json_encode($verification));
        $order->update_meta_data('_agentcart_payment_receipt_id', (string) ($receipt['id'] ?? ''));
        $order->update_meta_data('_agentcart_payment_transaction_reference', (string) ($verification['transaction_reference'] ?? ''));
        $order->update_meta_data('_agentcart_payment_rail', (string) ($verification['rail'] ?? ''));
        $order->update_meta_data(self::STATE_META, 'payment_verified');
        $order->save();
    }

    public static function verification_attempted($order) {
        return $order && $order->get_meta('_agentcart_verifier_attempted_at', true) !== '';
    }

    public static function mark_verifying($order) {
        $order->update_meta_data('_agentcart_verifier_attempted_at', gmdate('c'));
        $order->update_meta_data(self::STATE_META, 'verifying');
        $order->save();
        self::schedule($order->get_id(), 90);
    }

    public static function failure($order, $code, $paid = false) {
        if (!$order || !self::started($order)) {
            return;
        }
        $state = $paid ? 'compensation_required' : (self::verification_attempted($order) ? 'verification_pending' : 'checkout_rejected');
        $order->update_meta_data(self::STATE_META, $state);
        $order->update_meta_data('_agentcart_checkout_error', sanitize_key($code));
        $order->save();
    }

    public static function schedule($order_id, $delay) {
        $args = [intval($order_id)];
        $next = wp_next_scheduled('agentcart_shopbridge_recover_checkout', $args);
        if (!$next) {
            $next = time() + intval($delay);
            wp_schedule_single_event($next, 'agentcart_shopbridge_recover_checkout', $args);
        }
        $order = wc_get_order($order_id);
        if ($order) {
            $order->update_meta_data('_agentcart_recovery_next_attempt_at', $next);
            $order->save();
        }
    }

    public static function queue($page = 1) {
        $cases = [];
        foreach (['verifying', 'verification_pending', 'payment_verified', 'compensation_required', 'compensating'] as $state) {
            // phpcs:disable WordPress.DB.SlowDBQuery -- Manager-only, bounded recovery queue; excludes full request and address metadata.
            $orders = wc_get_orders([
                'limit' => 20, 'page' => max(1, min(1000, intval($page))), 'type' => 'shop_order',
                'orderby' => 'ID', 'order' => 'ASC',
                'meta_key' => self::STATE_META, 'meta_value' => $state,
            ]);
            // phpcs:enable WordPress.DB.SlowDBQuery
            foreach ($orders as $order) {
                $cases[] = [
                    'order_id' => $order->get_id(), 'state' => $state,
                    'created_at' => $order->get_date_created() ? $order->get_date_created()->getTimestamp() : time(),
                    'total' => $order->get_total(), 'currency' => $order->get_currency(),
                    'attempts' => intval($order->get_meta('_agentcart_recovery_attempts', true)),
                    'error' => (string) $order->get_meta('_agentcart_checkout_error', true),
                    'verified' => $order->get_meta('_agentcart_payment_verification', true) !== '',
                ];
            }
        }
        return ['cases' => $cases, 'page' => max(1, intval($page)), 'per_state_limit' => 20];
    }

    public static function complete($order) {
        $order->update_meta_data(self::STATE_META, 'completed');
        $order->delete_meta_data('_agentcart_checkout_request');
        $order->delete_meta_data('_agentcart_checkout_error');
        $order->save();
    }

    public static function invalidate_after_rollback($order) {
        clean_post_cache($order->get_id());
        wc_delete_shop_order_transients($order->get_id());
        if (class_exists('Automattic\\WooCommerce\\Caches\\OrderCache')) {
            wc_get_container()->get(Automattic\WooCommerce\Caches\OrderCache::class)->remove($order->get_id());
        }
        foreach ($order->get_items() as $item) {
            $product = $item->get_product();
            if ($product) {
                clean_post_cache($product->get_stock_managed_by_id());
                wc_delete_product_transients($product->get_stock_managed_by_id());
            }
        }
        WC_Cache_Helper::invalidate_cache_group('orders');
    }
}
