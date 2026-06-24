<?php
/**
 * Uninstall cleanup for AgentCart ShopBridge.
 *
 * This removes plugin configuration and ephemeral locks/transients. It
 * intentionally preserves WooCommerce order, refund, cancellation, payment,
 * and product metadata so merchants keep their commerce audit trail.
 */

if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

global $wpdb;

$options = [
    'agentcart_shopbridge_merchant_id',
    'agentcart_shopbridge_token',
    'agentcart_shopbridge_payment_verifier_url',
    'agentcart_shopbridge_payment_verifier_token',
    'agentcart_shopbridge_checkout_mode',
    'agentcart_shopbridge_tempo_recipient',
    'agentcart_shopbridge_tempo_network',
    'agentcart_shopbridge_stripe_profile_id',
    'agentcart_shopbridge_support_email',
    'agentcart_shopbridge_returns_url',
    'agentcart_shopbridge_substitution_policy',
    'agentcart_shopbridge_cancellation_window_minutes',
    'agentcart_shopbridge_registry_claim_fingerprint',
    'agentcart_shopbridge_registry_updated_at',
    'agentcart_shopbridge_registry_public_check',
    'agentcart_shopbridge_product_exposure_mode',
    'agentcart_shopbridge_product_exposure_tag',
    'agentcart_shopbridge_product_exposure_categories',
    'agentcart_shopbridge_product_blocked_categories',
    'agentcart_shopbridge_stock_hold_mode',
    'agentcart_shopbridge_stock_hold_minutes',
    'agentcart_shopbridge_stock_holds',
];

foreach ($options as $option) {
    delete_option($option);
}

$option_prefixes = [
    'agentcart_shopbridge_checkout_lock_',
    'agentcart_shopbridge_quote_lock_',
    'agentcart_shopbridge_refund_lock_',
    'agentcart_shopbridge_cancellation_lock_',
    '_transient_agentcart_shopbridge_quote_',
    '_transient_timeout_agentcart_shopbridge_quote_',
    '_transient_agentcart_shopbridge_rate_',
    '_transient_timeout_agentcart_shopbridge_rate_',
];

foreach ($option_prefixes as $prefix) {
    $like = $wpdb->esc_like($prefix) . '%';
    $wpdb->query(
        $wpdb->prepare(
            "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s",
            $like
        )
    );
}
