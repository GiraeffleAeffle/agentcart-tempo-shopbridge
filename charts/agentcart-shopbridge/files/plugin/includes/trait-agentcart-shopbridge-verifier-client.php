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
    private static function x402_authorization_nonce($quote_hash, $contract_hash, $resource_url) {
        if (!preg_match('/^[a-f0-9]{64}$/', $quote_hash) || !preg_match('/^[a-f0-9]{64}$/', $contract_hash) || $resource_url === '') {
            return '';
        }
        return '0x' . bin2hex(self::x402_keccak256('shopbridge-x402-nonce-v1' . hex2bin($quote_hash) . hex2bin($contract_hash) . self::x402_keccak256($resource_url)));
    }

    /**
     * Ethereum Keccak-256 (not SHA3-256), with lanes split into 32-bit halves.
     *
     * @param string $input Raw bytes.
     * @return string 32 raw digest bytes.
     */
    private static function x402_keccak256($input) {
        $rotations = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14];
        $constants = [
            [0x00000001, 0x00000000], [0x00008082, 0x00000000], [0x0000808a, 0x80000000], [0x80008000, 0x80000000],
            [0x0000808b, 0x00000000], [0x80000001, 0x00000000], [0x80008081, 0x80000000], [0x00008009, 0x80000000],
            [0x0000008a, 0x00000000], [0x00000088, 0x00000000], [0x80008009, 0x00000000], [0x8000000a, 0x00000000],
            [0x8000808b, 0x00000000], [0x0000008b, 0x80000000], [0x00008089, 0x80000000], [0x00008003, 0x80000000],
            [0x00008002, 0x80000000], [0x00000080, 0x80000000], [0x0000800a, 0x00000000], [0x8000000a, 0x80000000],
            [0x80008081, 0x80000000], [0x00008080, 0x80000000], [0x80000001, 0x00000000], [0x80008008, 0x80000000],
        ];
        $remaining = 136 - (strlen($input) % 136);
        $input .= $remaining === 1 ? "\x81" : "\x01" . str_repeat("\x00", $remaining - 2) . "\x80";
        $state = array_fill(0, 25, [0, 0]);
        $length = strlen($input);
        for ($offset = 0; $offset < $length; $offset += 136) {
            $words = array_values(unpack('V*', substr($input, $offset, 136)));
            for ($i = 0; $i < 17; ++$i) {
                $state[$i][0] ^= $words[2 * $i];
                $state[$i][1] ^= $words[2 * $i + 1];
            }
            foreach ($constants as $constant) {
                $columns = array_fill(0, 5, [0, 0]);
                for ($x = 0; $x < 5; ++$x) {
                    for ($y = 0; $y < 5; ++$y) {
                        $columns[$x][0] ^= $state[$x + 5 * $y][0];
                        $columns[$x][1] ^= $state[$x + 5 * $y][1];
                    }
                }
                $lanes = array_fill(0, 25, [0, 0]);
                for ($x = 0; $x < 5; ++$x) {
                    $next = self::x402_rotate_lane($columns[($x + 1) % 5], 1);
                    $delta = [$columns[($x + 4) % 5][0] ^ $next[0], $columns[($x + 4) % 5][1] ^ $next[1]];
                    for ($y = 0; $y < 5; ++$y) {
                        $i = $x + 5 * $y;
                        $lanes[$y + 5 * ((2 * $x + 3 * $y) % 5)] = self::x402_rotate_lane([$state[$i][0] ^ $delta[0], $state[$i][1] ^ $delta[1]], $rotations[$i]);
                    }
                }
                for ($x = 0; $x < 5; ++$x) {
                    for ($y = 0; $y < 5; ++$y) {
                        for ($half = 0; $half < 2; ++$half) {
                            $state[$x + 5 * $y][$half] = $lanes[$x + 5 * $y][$half] ^ ((~$lanes[($x + 1) % 5 + 5 * $y][$half]) & $lanes[($x + 2) % 5 + 5 * $y][$half]);
                        }
                    }
                }
                $state[0][0] ^= $constant[0];
                $state[0][1] ^= $constant[1];
            }
        }
        $digest = '';
        for ($i = 0; $i < 4; ++$i) {
            $digest .= pack('V2', $state[$i][0], $state[$i][1]);
        }
        return $digest;
    }

    private static function x402_rotate_lane($lane, $bits) {
        if ($bits >= 32) {
            $lane = [$lane[1], $lane[0]];
            $bits -= 32;
        }
        if ($bits === 0) {
            return $lane;
        }
        return [
            (($lane[0] << $bits) | ($lane[1] >> (32 - $bits))) & 0xffffffff,
            (($lane[1] << $bits) | ($lane[0] >> (32 - $bits))) & 0xffffffff,
        ];
    }

    private static function call_payment_verifier($verifier_url, $quote, $receipt, $body, $payment_contract, $checkout_draft) {
        $rail = self::payment_rail_from_receipt($receipt, $body);
        $payment_contract_hash = self::payment_contract_hash($payment_contract);
        $settlement = $payment_contract['settlement'] ?? [];
        if ($rail === 'x402-compatible') {
            $document = $quote['payment_requirements']['x402']['payment_required'] ?? [];
            $nonce = self::x402_authorization_nonce((string) ($quote['quote_hash'] ?? ''), $payment_contract_hash, (string) ($document['resource']['url'] ?? ''));
            $decoded = json_decode(base64_decode((string) ($receipt['x402_payment_signature'] ?? ''), true), true); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_decode -- Decode the x402 v2 transport document.
            if ($nonce === '' || ($decoded['payload']['authorization']['nonce'] ?? '') !== $nonce) {
                return new WP_Error('agentcart_x402_nonce_mismatch', 'The x402 authorization nonce does not bind this quote and checkout resource.', ['status' => 402]);
            }
        }
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
                'tempo_network' => $rail === 'tempo-mpp' ? ($settlement['network'] ?? '') : self::tempo_network(),
                'tempo_recipient' => $rail === 'tempo-mpp' ? ($settlement['recipient'] ?? '') : self::tempo_recipient(),
                'stripe_profile_id' => $rail === 'stripe-card-mpp' ? ($settlement['stripe_profile_id'] ?? '') : self::stripe_profile_id(),
                'x402_network' => $rail === 'x402-compatible' ? ($settlement['network'] ?? '') : self::x402_network(),
                'x402_asset' => $rail === 'x402-compatible' ? ($settlement['asset'] ?? '') : self::x402_asset(),
                'x402_pay_to' => $rail === 'x402-compatible' ? ($settlement['pay_to'] ?? '') : self::x402_pay_to(),
                'x402_amount' => $rail === 'x402-compatible' ? ($settlement['amount'] ?? '') : self::x402_atomic_amount(intval($quote['total_cents'] ?? 0)),
                'x402_max_timeout_seconds' => $rail === 'x402-compatible' ? ($settlement['max_timeout_seconds'] ?? 0) : self::x402_max_timeout_seconds(),
                'x402_payment_requirements' => $quote['payment_requirements']['x402']['payment_required']['accepts'][0] ?? null,
            ],
        ];
        $headers = ['Content-Type' => 'application/json'];
        $token = self::payment_verifier_token();
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
        }
        $response = self::verifier_http_post($verifier_url, $payload, $headers, 15, $checkout_draft);
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
        $expected_network = (string) ($settlement['network'] ?? '');
        $verified_recipient = strtolower((string) ($decoded['recipient'] ?? ''));
        $expected_recipient = strtolower((string) ($settlement['recipient'] ?? ''));
        $verified_rail = self::normalize_payment_rail((string) ($decoded['rail'] ?? ''));
        $verified_stripe_profile_id = sanitize_text_field((string) ($decoded['stripe_profile_id'] ?? ''));
        $expected_stripe_profile_id = (string) ($settlement['stripe_profile_id'] ?? '');
        $verified_x402_asset = strtolower(sanitize_text_field((string) ($decoded['asset'] ?? $decoded['x402_asset'] ?? '')));
        $verified_x402_pay_to = strtolower(sanitize_text_field((string) ($decoded['pay_to'] ?? $decoded['payTo'] ?? $decoded['x402_pay_to'] ?? '')));
        $verified_x402_amount = sanitize_text_field((string) ($decoded['amount'] ?? $decoded['x402_amount'] ?? ''));
        $expected_x402_asset = $rail === 'x402-compatible' ? strtolower((string) ($settlement['asset'] ?? '')) : '';
        $expected_x402_pay_to = $rail === 'x402-compatible' ? strtolower((string) ($settlement['pay_to'] ?? '')) : '';
        $expected_x402_amount = $rail === 'x402-compatible' ? (string) ($settlement['amount'] ?? '') : '';
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
        if ($rail === 'x402-compatible' && $expected_network !== '' && $verified_network !== $expected_network) {
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
            'real_settlement_verified' => ($decoded['real_settlement_verified'] ?? false) === true,
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
            'payment_response' => sanitize_text_field((string) ($decoded['payment_response_header_value'] ?? '')),
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
        $response = self::verifier_http_post($verifier_url, $payload, $headers, 20, null);
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
        $refund_status = sanitize_key((string) ($decoded['refund_status'] ?? ''));
        if ($refund_status !== 'succeeded') {
            return new WP_Error('agentcart_refund_pending_or_failed', 'Refund is not confirmed successful. Retry the same request reference to reconcile.', [
                'status' => 409, 'refund_status' => $refund_status ?: 'unknown',
                'refund_reference' => $refund_reference,
                'retryable' => array_key_exists('retryable', $decoded) ? $decoded['retryable'] === true : !in_array($refund_status, ['failed', 'canceled', 'review_required'], true),
            ]);
        }
        if ($refund_reference === '') {
            return new WP_Error('agentcart_refund_reference_required', 'External refund verifier must return a refund_reference.', ['status' => 402]);
        }
        if (($decoded['real_refund_verified'] ?? false) !== true) {
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

    private static function verifier_http_post($verifier_url, $payload, $headers, $timeout, $checkout_draft) {
        $url = self::normalize_payment_verifier_url($verifier_url);
        if ($url === '') {
            return new WP_Error(
                'agentcart_payment_verifier_url_invalid',
                'Payment verifier URL must be a public HTTP(S) URL without embedded credentials. Deployment-pinned internal verifier URLs are also accepted.',
                ['status' => 400]
            );
        }
        $args = [
            'headers' => $headers,
            'body' => wp_json_encode($payload),
            'timeout' => intval($timeout),
            'reject_unsafe_urls' => !self::payment_verifier_url_allows_private_networks(),
            'redirection' => 0,
            'limit_response_size' => 1048576,
        ];
        if ($checkout_draft !== null && !AgentCart_ShopBridge_Checkout_Store::verification_attempted($checkout_draft)) {
            AgentCart_ShopBridge_Checkout_Store::mark_verifying($checkout_draft);
        }
        return wp_remote_post($url, $args);
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
