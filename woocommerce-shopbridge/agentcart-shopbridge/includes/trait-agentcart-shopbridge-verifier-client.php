<?php
/**
 * Merchant-side External Verifier client for AgentCart ShopBridge.
 *
 * @package AgentCart_ShopBridge
 */

if (!defined('ABSPATH')) {
    exit;
}
trait AgentCart_ShopBridge_Verifier_Client {
    private static function call_payment_verifier($verifier_url, $quote, $receipt, $body) {
        $rail = self::payment_rail_from_receipt($receipt, $body);
        $payment_contract = self::payment_verification_contract($quote, $rail);
        $payment_contract_hash = self::payment_contract_hash($payment_contract);
        $payload = [
            'operation' => 'payment',
            'quote' => $quote,
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'payment_contract' => $payment_contract,
            'payment_contract_hash' => $payment_contract_hash,
            'payment_receipt' => $receipt,
            'approval' => self::checkout_approval_metadata($body),
            'agentcart_order_id' => sanitize_text_field((string) ($body['agentcart_order_id'] ?? '')),
            'expected' => [
                'amount_cents' => intval($quote['total_cents'] ?? 0),
                'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                'merchant_id' => self::merchant()['id'],
                'rail' => $rail,
                'payment_contract_hash' => $payment_contract_hash,
                'tempo_network' => self::tempo_network(),
                'tempo_recipient' => self::tempo_recipient(),
                'stripe_profile_id' => self::stripe_profile_id(),
                'x402_network' => self::x402_network(),
                'x402_asset' => self::x402_asset(),
                'x402_pay_to' => self::x402_pay_to(),
                'x402_max_amount_required' => self::x402_atomic_amount(intval($quote['total_cents'] ?? 0)),
            ],
        ];
        $headers = ['Content-Type' => 'application/json'];
        $token = self::payment_verifier_token();
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
        }
        $response = self::verifier_http_post($verifier_url, $payload, $headers, 15);
        if (is_wp_error($response)) {
            return new WP_Error(
                'agentcart_payment_verifier_failed',
                'External payment verifier request failed.',
                ['status' => 502, 'detail' => ['error_code' => sanitize_key($response->get_error_code())]]
            );
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded) || empty($decoded['ok'])) {
            return new WP_Error('agentcart_payment_not_verified', 'External payment verifier rejected the receipt.', ['status' => 402, 'detail' => self::verifier_error_detail($status, $decoded, $raw_body)]);
        }
        $expected_quote_hash = (string) ($quote['quote_hash'] ?? '');
        $verified_quote_hash = (string) ($decoded['quote_hash'] ?? '');
        $verified_amount = intval($decoded['amount_cents'] ?? -1);
        $verified_currency = strtoupper((string) ($decoded['currency'] ?? ''));
        $expected_currency = strtoupper((string) ($quote['currency'] ?? get_woocommerce_currency()));
        $verified_network = (string) ($decoded['network'] ?? $decoded['x402_network'] ?? '');
        $expected_network = self::tempo_network();
        $verified_recipient = strtolower((string) ($decoded['recipient'] ?? ''));
        $expected_recipient = strtolower(self::tempo_recipient());
        $verified_rail = self::normalize_payment_rail((string) ($decoded['rail'] ?? ''));
        $verified_stripe_profile_id = sanitize_text_field((string) ($decoded['stripe_profile_id'] ?? ''));
        $expected_stripe_profile_id = self::stripe_profile_id();
        $verified_x402_asset = strtolower(sanitize_text_field((string) ($decoded['asset'] ?? $decoded['x402_asset'] ?? '')));
        $verified_x402_pay_to = strtolower(sanitize_text_field((string) ($decoded['pay_to'] ?? $decoded['payTo'] ?? $decoded['x402_pay_to'] ?? '')));
        $verified_x402_amount = sanitize_text_field((string) ($decoded['max_amount_required'] ?? $decoded['maxAmountRequired'] ?? $decoded['x402_max_amount_required'] ?? ''));
        $expected_x402_asset = strtolower(self::x402_asset());
        $expected_x402_pay_to = strtolower(self::x402_pay_to());
        $expected_x402_amount = self::x402_atomic_amount(intval($quote['total_cents'] ?? 0));
        $verified_payer_address = strtolower(sanitize_text_field((string) ($decoded['payer_address'] ?? $decoded['source_address'] ?? '')));
        $verified_payer_source = sanitize_text_field((string) ($decoded['payer_source'] ?? $decoded['payment_source'] ?? ''));
        $transaction_reference = sanitize_text_field((string) ($decoded['transaction_reference'] ?? ''));
        $verified_contract_hash = sanitize_text_field((string) ($decoded['payment_contract_hash'] ?? $decoded['contract_hash'] ?? ''));
        if (
            $verified_quote_hash === ''
            || !hash_equals($expected_quote_hash, $verified_quote_hash)
            || $verified_amount !== intval($quote['total_cents'] ?? 0)
            || $verified_currency !== $expected_currency
        ) {
            return new WP_Error('agentcart_payment_verifier_mismatch', 'External payment verifier response does not match the quote.', ['status' => 402]);
        }
        if ($verified_contract_hash === '') {
            return new WP_Error('agentcart_payment_contract_required', 'External payment verifier must return payment_contract_hash.', ['status' => 402]);
        }
        if (!hash_equals($payment_contract_hash, $verified_contract_hash)) {
            return new WP_Error('agentcart_payment_contract_mismatch', 'External payment verifier returned the wrong payment contract hash.', ['status' => 402]);
        }
        if ($verified_rail === '' || $verified_rail !== $rail) {
            return new WP_Error('agentcart_payment_rail_mismatch', 'External payment verifier returned the wrong payment rail.', ['status' => 402]);
        }
        if ($rail === 'tempo-mpp' && $expected_network !== '' && $verified_network !== $expected_network) {
            return new WP_Error('agentcart_payment_network_mismatch', 'External payment verifier returned the wrong network.', ['status' => 402]);
        }
        if ($rail === 'tempo-mpp' && $expected_recipient !== '' && $verified_recipient !== $expected_recipient) {
            return new WP_Error('agentcart_payment_recipient_mismatch', 'External payment verifier returned the wrong recipient.', ['status' => 402]);
        }
        if ($rail === 'tempo-mpp' && $verified_payer_address !== '' && !preg_match('/^0x[a-f0-9]{40}$/', $verified_payer_address)) {
            return new WP_Error('agentcart_payment_payer_address_invalid', 'External payment verifier returned an invalid payer address.', ['status' => 402]);
        }
        if ($rail === 'stripe-card-mpp' && $expected_stripe_profile_id !== '' && $verified_stripe_profile_id !== $expected_stripe_profile_id) {
            return new WP_Error('agentcart_payment_stripe_profile_mismatch', 'External payment verifier returned the wrong Stripe profile.', ['status' => 402]);
        }
        if ($rail === 'x402-compatible' && self::x402_network() !== '' && $verified_network !== self::x402_network()) {
            return new WP_Error('agentcart_payment_x402_network_mismatch', 'External payment verifier returned the wrong x402 network.', ['status' => 402]);
        }
        if ($rail === 'x402-compatible' && $expected_x402_asset !== '' && $verified_x402_asset !== $expected_x402_asset) {
            return new WP_Error('agentcart_payment_x402_asset_mismatch', 'External payment verifier returned the wrong x402 asset.', ['status' => 402]);
        }
        if ($rail === 'x402-compatible' && $expected_x402_pay_to !== '' && $verified_x402_pay_to !== $expected_x402_pay_to) {
            return new WP_Error('agentcart_payment_x402_pay_to_mismatch', 'External payment verifier returned the wrong x402 payTo address.', ['status' => 402]);
        }
        if ($rail === 'x402-compatible' && $expected_x402_amount !== '' && $verified_x402_amount !== $expected_x402_amount) {
            return new WP_Error('agentcart_payment_x402_amount_mismatch', 'External payment verifier returned the wrong x402 atomic amount.', ['status' => 402]);
        }
        if ($transaction_reference === '') {
            return new WP_Error('agentcart_payment_reference_required', 'External payment verifier must return a transaction_reference.', ['status' => 402]);
        }
        $existing_orders = wc_get_orders([
            'limit' => 1,
            'return' => 'objects',
            'meta_key' => '_agentcart_payment_transaction_reference', // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_key -- Payment replay protection must query Woo order meta by transaction reference.
            'meta_value' => $transaction_reference, // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_value -- Payment replay protection must query Woo order meta by transaction reference.
        ]);
        if (!empty($existing_orders)) {
            return new WP_Error('agentcart_payment_replay', 'Payment transaction reference has already been used.', ['status' => 409]);
        }
        return [
            'state' => 'verified',
            'mode' => 'external_verifier',
            'real_settlement_verified' => !empty($decoded['real_settlement_verified']),
            'amount_cents' => $verified_amount,
            'currency' => $expected_currency,
            'rail' => $verified_rail,
            'network' => $verified_network ?: $expected_network,
            'recipient' => $verified_recipient ?: $expected_recipient,
            'payer_address' => $verified_payer_address,
            'payer_source' => $verified_payer_source,
            'stripe_profile_id' => $verified_stripe_profile_id ?: $expected_stripe_profile_id,
            'transaction_reference' => $transaction_reference,
            'quote_hash' => $expected_quote_hash,
            'payment_contract_hash' => $payment_contract_hash,
        ];
    }

    private static function call_refund_verifier($verifier_url, WC_Order $order, $amount_cents, $currency, $reason, $rail, $quote_hash, $transaction_reference, $payment_verification, $body) {
        $refund_recipient = is_array($payment_verification) ? strtolower(sanitize_text_field((string) ($payment_verification['payer_address'] ?? ''))) : '';
        $tempo_asset = self::tempo_settlement_asset();
        $tempo_asset_name = sanitize_text_field((string) ($tempo_asset['asset'] ?? ''));
        $payload = [
            'operation' => 'refund',
            'merchant' => self::merchant(),
            'order' => [
                'id' => (string) $order->get_id(),
                'number' => $order->get_order_number(),
                'agentcart_order_id' => (string) $order->get_meta('_agentcart_order_id', true),
                'agentcart_quote_id' => (string) $order->get_meta('_agentcart_quote_id', true),
                'merchant_quote_id' => (string) $order->get_meta('_agentcart_merchant_quote_id', true),
                'quote_hash' => $quote_hash,
                'currency' => $currency,
                'payment_method' => $order->get_payment_method(),
                'payment_receipt_id' => (string) $order->get_meta('_agentcart_payment_receipt_id', true),
                'transaction_reference' => $transaction_reference,
                'payment_verification' => is_array($payment_verification) ? $payment_verification : null,
            ],
            'refund' => [
                'amount_cents' => intval($amount_cents),
                'currency' => $currency,
                'reason' => $reason,
                'rail' => $rail,
                'requested_reference' => sanitize_text_field((string) ($body['requested_reference'] ?? '')),
                'recipient' => $rail === 'tempo-mpp' ? $refund_recipient : '',
                'asset' => $rail === 'tempo-mpp' ? $tempo_asset_name : '',
            ],
            'expected' => [
                'amount_cents' => intval($amount_cents),
                'currency' => $currency,
                'quote_hash' => $quote_hash,
                'original_transaction_reference' => $transaction_reference,
                'tempo_network' => self::tempo_network(),
                'tempo_recipient' => self::tempo_recipient(),
                'refund_recipient' => $rail === 'tempo-mpp' ? $refund_recipient : '',
                'asset' => $rail === 'tempo-mpp' ? $tempo_asset_name : '',
                'stripe_profile_id' => self::stripe_profile_id(),
            ],
        ];
        $headers = ['Content-Type' => 'application/json'];
        $token = self::payment_verifier_token();
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
        }
        $response = self::verifier_http_post($verifier_url, $payload, $headers, 20);
        if (is_wp_error($response)) {
            return new WP_Error(
                'agentcart_refund_verifier_failed',
                'External refund verifier request failed.',
                ['status' => 502, 'detail' => ['error_code' => sanitize_key($response->get_error_code())]]
            );
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded) || empty($decoded['ok'])) {
            return new WP_Error('agentcart_refund_not_verified', 'External payment verifier rejected the refund.', ['status' => 402, 'detail' => self::verifier_error_detail($status, $decoded, $raw_body)]);
        }
        $verified_amount = intval($decoded['amount_cents'] ?? -1);
        $verified_currency = strtoupper((string) ($decoded['currency'] ?? ''));
        $verified_quote_hash = (string) ($decoded['quote_hash'] ?? '');
        $verified_original_reference = sanitize_text_field((string) ($decoded['original_transaction_reference'] ?? ''));
        $verified_rail = sanitize_key((string) ($decoded['rail'] ?? ''));
        $refund_reference = sanitize_text_field((string) ($decoded['refund_reference'] ?? $decoded['refund_id'] ?? $decoded['transaction_reference'] ?? ''));
        if ($verified_amount !== intval($amount_cents) || $verified_currency !== strtoupper($currency)) {
            return new WP_Error('agentcart_refund_verifier_mismatch', 'External refund verifier response does not match the refund amount or currency.', ['status' => 402]);
        }
        if ($quote_hash !== '' && ($verified_quote_hash === '' || !hash_equals($quote_hash, $verified_quote_hash))) {
            return new WP_Error('agentcart_refund_quote_mismatch', 'External refund verifier response does not match the original quote hash.', ['status' => 402]);
        }
        if ($transaction_reference !== '' && ($verified_original_reference === '' || !hash_equals($transaction_reference, $verified_original_reference))) {
            return new WP_Error('agentcart_refund_original_reference_mismatch', 'External refund verifier response does not match the original payment reference.', ['status' => 402]);
        }
        if ($verified_rail === '' || $verified_rail !== $rail) {
            return new WP_Error('agentcart_refund_rail_mismatch', 'External refund verifier response does not match the refund rail.', ['status' => 402]);
        }
        if ($refund_reference === '') {
            return new WP_Error('agentcart_refund_reference_required', 'External refund verifier must return a refund_reference.', ['status' => 402]);
        }
        if (empty($decoded['real_refund_verified'])) {
            return new WP_Error('agentcart_refund_not_real_verified', 'External refund verifier did not confirm real rail refund execution.', ['status' => 402]);
        }
        return [
            'state' => 'rail_refund_verified',
            'mode' => 'external_verifier',
            'rail' => $verified_rail,
            'real_refund_verified' => true,
            'amount_cents' => $verified_amount,
            'currency' => $currency,
            'quote_hash' => $quote_hash,
            'original_transaction_reference' => $transaction_reference,
            'refund_reference' => $refund_reference,
            'provider' => sanitize_text_field((string) ($decoded['provider'] ?? 'external_verifier')),
            'replay_reference' => sanitize_text_field((string) ($decoded['replay_reference'] ?? '')),
            'replay_request_hash' => sanitize_text_field((string) ($decoded['replay_request_hash'] ?? '')),
            'refund_status' => sanitize_text_field((string) ($decoded['refund_status'] ?? '')),
            'idempotent_replay' => !empty($decoded['idempotent_replay']),
        ];
    }

    private static function verifier_http_post($verifier_url, $payload, $headers, $timeout) {
        $url = self::normalize_payment_verifier_url($verifier_url);
        if ($url === '') {
            return new WP_Error(
                'agentcart_payment_verifier_url_invalid',
                'Payment verifier URL must be a valid HTTP(S) URL without embedded credentials.',
                ['status' => 400]
            );
        }
        return wp_remote_post($url, [
            'headers' => $headers,
            'body' => wp_json_encode($payload),
            'timeout' => intval($timeout),
            'redirection' => 0,
            'limit_response_size' => 1048576,
        ]);
    }

    private static function verifier_error_detail($status, $decoded, $raw_body) {
        $detail = [
            'http_status' => intval($status),
        ];
        if (is_array($decoded)) {
            foreach (['error', 'code', 'provider_error_class', 'provider_status', 'request_id', 'correlation_id'] as $field) {
                if (isset($decoded[$field]) && is_scalar($decoded[$field])) {
                    $detail[$field] = sanitize_text_field((string) $decoded[$field]);
                }
            }
            if (isset($decoded['retryable'])) {
                $detail['retryable'] = !empty($decoded['retryable']);
            }
            return $detail;
        }
        $body = (string) $raw_body;
        $detail['raw_body_hash'] = hash('sha256', $body);
        $detail['raw_body_bytes'] = strlen($body);
        return $detail;
    }
}
