<?php
/**
 * Plugin Name: AgentCart ShopBridge
 * Description: Exposes opt-in WooCommerce catalog, quote, and paid-order endpoints for AgentCart household agents.
 * Version: 0.1.0
 * Requires at least: 6.4
 * Requires PHP: 8.1
 * Requires Plugins: woocommerce
 * Author: AgentCart
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: agentcart-shopbridge
 */

if (!defined('ABSPATH')) {
    exit;
}

final class AgentCart_ShopBridge {
    const API_NAMESPACE = 'agentcart/v1';
    const TOKEN_OPTION = 'agentcart_shopbridge_token';
    const QUOTE_TRANSIENT_PREFIX = 'agentcart_shopbridge_quote_';
    const STATUS_TOKEN_META = '_agentcart_order_status_token';
    const IDEMPOTENCY_KEY_META = '_agentcart_idempotency_key';
    const REFUND_IDEMPOTENCY_KEY_META = '_agentcart_refund_idempotency_key';
    const REFUND_REQUESTED_REFERENCE_META = '_agentcart_refund_requested_reference';
    const REFUND_REFERENCE_META = '_agentcart_refund_reference';
    const ORDER_ITEMS_META = '_agentcart_quote_items';
    const ORDER_MERCHANT_POLICY_META = '_agentcart_merchant_policy';
    const CANCELLATION_EVENTS_META = '_agentcart_cancellations';
    const CHECKOUT_LOCK_PREFIX = 'agentcart_shopbridge_checkout_lock_';
    const QUOTE_LOCK_PREFIX = 'agentcart_shopbridge_quote_lock_';
    const REFUND_LOCK_PREFIX = 'agentcart_shopbridge_refund_lock_';
    const CANCELLATION_LOCK_PREFIX = 'agentcart_shopbridge_cancellation_lock_';
    const RATE_LIMIT_TRANSIENT_PREFIX = 'agentcart_shopbridge_rate_';
    const CHECKOUT_LOCK_TTL_SECONDS = 120;
    const RATE_LIMIT_WINDOW_SECONDS = 60;
    const MERCHANT_ID_OPTION = 'agentcart_shopbridge_merchant_id';
    const PAYMENT_VERIFIER_URL_OPTION = 'agentcart_shopbridge_payment_verifier_url';
    const PAYMENT_VERIFIER_TOKEN_OPTION = 'agentcart_shopbridge_payment_verifier_token';
    const CHECKOUT_MODE_OPTION = 'agentcart_shopbridge_checkout_mode';
    const TEMPO_RECIPIENT_OPTION = 'agentcart_shopbridge_tempo_recipient';
    const TEMPO_NETWORK_OPTION = 'agentcart_shopbridge_tempo_network';
    const STRIPE_PROFILE_ID_OPTION = 'agentcart_shopbridge_stripe_profile_id';
    const X402_NETWORK_OPTION = 'agentcart_shopbridge_x402_network';
    const X402_ASSET_OPTION = 'agentcart_shopbridge_x402_asset';
    const X402_ASSET_SYMBOL_OPTION = 'agentcart_shopbridge_x402_asset_symbol';
    const X402_ASSET_DECIMALS_OPTION = 'agentcart_shopbridge_x402_asset_decimals';
    const X402_ASSET_CURRENCY_OPTION = 'agentcart_shopbridge_x402_asset_currency';
    const X402_PAY_TO_OPTION = 'agentcart_shopbridge_x402_pay_to';
    const X402_FACILITATOR_URL_OPTION = 'agentcart_shopbridge_x402_facilitator_url';
    const X402_MAX_TIMEOUT_SECONDS_OPTION = 'agentcart_shopbridge_x402_max_timeout_seconds';
    const SIGNED_REQUEST_MODE_OPTION = 'agentcart_shopbridge_signed_request_mode';
    const SIGNED_REQUEST_SECRET_OPTION = 'agentcart_shopbridge_signed_request_secret';
    const SIGNED_REQUEST_PUBLIC_KEY_OPTION = 'agentcart_shopbridge_signed_request_public_key';
    const SIGNED_REQUEST_KEYS_OPTION = 'agentcart_shopbridge_signed_request_keys';
    const SIGNED_REQUEST_AUDIT_OPTION = 'agentcart_shopbridge_signed_request_audit';
    const SIGNED_REQUEST_NONCE_PREFIX = 'agentcart_shopbridge_signed_nonce_';
    const SIGNED_REQUEST_AUDIT_LIMIT = 100;
    const SIGNED_REQUEST_MAX_TTL_SECONDS = 900;
    const SIGNED_REQUEST_CLOCK_SKEW_SECONDS = 60;
    const SIGNED_REQUEST_KEY_RETIREMENT_SECONDS = 604800;
    const SUPPORT_EMAIL_OPTION = 'agentcart_shopbridge_support_email';
    const RETURNS_URL_OPTION = 'agentcart_shopbridge_returns_url';
    const SUBSTITUTION_POLICY_OPTION = 'agentcart_shopbridge_substitution_policy';
    const CANCELLATION_WINDOW_MINUTES_OPTION = 'agentcart_shopbridge_cancellation_window_minutes';
    const REGISTRY_CLAIM_FINGERPRINT_OPTION = 'agentcart_shopbridge_registry_claim_fingerprint';
    const REGISTRY_UPDATED_AT_OPTION = 'agentcart_shopbridge_registry_updated_at';
    const REGISTRY_PUBLIC_CHECK_OPTION = 'agentcart_shopbridge_registry_public_check';
    const REGISTRY_CONNECTION_URL_OPTION = 'agentcart_shopbridge_registry_connection_url';
    const REGISTRY_CONNECTION_TOKEN_OPTION = 'agentcart_shopbridge_registry_connection_token';
    const REGISTRY_CONNECTION_STATUS_OPTION = 'agentcart_shopbridge_registry_connection_status';
    const REGISTRY_HEALTH_CHECK_OPTION = 'agentcart_shopbridge_registry_health_check';
    const REGISTRY_REVOKED_RECORDS_OPTION = 'agentcart_shopbridge_registry_revoked_records';
    const SANDBOX_QUOTE_CHECK_OPTION = 'agentcart_shopbridge_sandbox_quote_check';
    const SANDBOX_CHECKOUT_TEST_OPTION = 'agentcart_shopbridge_sandbox_checkout_test';
    const PRODUCT_EXPOSURE_MODE_OPTION = 'agentcart_shopbridge_product_exposure_mode';
    const PRODUCT_EXPOSURE_TAG_OPTION = 'agentcart_shopbridge_product_exposure_tag';
    const PRODUCT_EXPOSURE_CATEGORIES_OPTION = 'agentcart_shopbridge_product_exposure_categories';
    const PRODUCT_BLOCKED_CATEGORIES_OPTION = 'agentcart_shopbridge_product_blocked_categories';
    const PRODUCT_EXPOSURE_PREVIEW_OPTION = 'agentcart_shopbridge_product_exposure_preview';
    const PRODUCT_EXPOSURE_SNAPSHOT_OPTION = 'agentcart_shopbridge_product_exposure_snapshot';
    const PRODUCT_EXPOSURE_PREVIEW_LIMIT = 200;
    const PRODUCT_ENABLED_META = '_agentcart_enabled';
    const PRODUCT_BLOCKED_META = '_agentcart_checkout_blocked';
    const PRODUCT_MAX_QUANTITY_META = '_agentcart_max_quantity';
    const PRODUCT_SHIPPING_COUNTRIES_META = '_agentcart_shipping_countries';
    const PRODUCT_PERISHABLE_META = '_agentcart_perishable';
    const PRODUCT_DEPOSIT_META = '_agentcart_deposit_possible';
    const PRODUCT_FINAL_SALE_META = '_agentcart_final_sale';
    const PRODUCT_SUBSTITUTION_SENSITIVE_META = '_agentcart_substitution_sensitive';
    const PRODUCT_RESTRICTED_GOODS_ALLOWED_META = '_agentcart_restricted_goods_allowed';
    const STOCK_HOLD_MODE_OPTION = 'agentcart_shopbridge_stock_hold_mode';
    const STOCK_HOLD_MINUTES_OPTION = 'agentcart_shopbridge_stock_hold_minutes';
    const STOCK_HOLDS_OPTION = 'agentcart_shopbridge_stock_holds';

    public static function init() {
        add_action('rest_api_init', [__CLASS__, 'register_routes']);
        add_action('admin_menu', [__CLASS__, 'register_admin_menu']);
        add_action('admin_init', [__CLASS__, 'ensure_token']);
        add_action('admin_init', [__CLASS__, 'register_settings']);
        add_action('parse_request', [__CLASS__, 'maybe_serve_well_known_manifest']);
        add_action('woocommerce_product_options_general_product_data', [__CLASS__, 'render_product_agentcart_options']);
        add_action('woocommerce_admin_process_product_object', [__CLASS__, 'save_product_agentcart_options']);
    }

    public static function ensure_token() {
        if (!get_option(self::TOKEN_OPTION)) {
            update_option(self::TOKEN_OPTION, wp_generate_password(40, false, false));
        }
    }

    public static function register_routes() {
        register_rest_route(self::API_NAMESPACE, '/capability', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [__CLASS__, 'capability'],
            'permission_callback' => [__CLASS__, 'authorize_public_read'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/support-diagnostics', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [__CLASS__, 'support_diagnostics'],
            'permission_callback' => [__CLASS__, 'authorize_support_diagnostics'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/catalog', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [__CLASS__, 'catalog'],
            'permission_callback' => [__CLASS__, 'authorize_public_read'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/products/(?P<id>[\d]+)', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [__CLASS__, 'product'],
            'permission_callback' => [__CLASS__, 'authorize_public_read'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/quote', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [__CLASS__, 'quote'],
            'permission_callback' => [__CLASS__, 'authorize_public_read'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/orders', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [__CLASS__, 'create_order'],
            'permission_callback' => [__CLASS__, 'authorize_checkout'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/orders/(?P<id>[\d]+)/status', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => [__CLASS__, 'order_status'],
            'permission_callback' => [__CLASS__, 'authorize_order_status'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/orders/(?P<id>[\d]+)/refunds', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [__CLASS__, 'create_refund'],
            'permission_callback' => [__CLASS__, 'authorize_refund'],
        ]);
        register_rest_route(self::API_NAMESPACE, '/orders/(?P<id>[\d]+)/cancellations', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [__CLASS__, 'create_cancellation'],
            'permission_callback' => [__CLASS__, 'authorize_cancellation'],
        ]);
    }

    public static function register_admin_menu() {
        add_submenu_page(
            'woocommerce',
            'AgentCart ShopBridge',
            'AgentCart',
            'manage_woocommerce',
            'agentcart-shopbridge',
            [__CLASS__, 'render_settings_page']
        );
    }

    public static function register_settings() {
        register_setting('agentcart_shopbridge', self::MERCHANT_ID_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_merchant_id_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::TOKEN_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::SUPPORT_EMAIL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_email',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::RETURNS_URL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::REGISTRY_CONNECTION_URL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::REGISTRY_CONNECTION_TOKEN_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::SUBSTITUTION_POLICY_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_substitution_policy_setting'],
            'default' => 'approval_required',
        ]);
        register_setting('agentcart_shopbridge', self::CANCELLATION_WINDOW_MINUTES_OPTION, [
            'type' => 'integer',
            'sanitize_callback' => [__CLASS__, 'sanitize_cancellation_window_minutes_setting'],
            'default' => 30,
        ]);
        register_setting('agentcart_shopbridge', self::TEMPO_NETWORK_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_key',
            'default' => 'testnet',
        ]);
        register_setting('agentcart_shopbridge', self::TEMPO_RECIPIENT_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::STRIPE_PROFILE_ID_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_NETWORK_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_ASSET_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_ASSET_SYMBOL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => 'USDC',
        ]);
        register_setting('agentcart_shopbridge', self::X402_ASSET_DECIMALS_OPTION, [
            'type' => 'integer',
            'sanitize_callback' => [__CLASS__, 'sanitize_x402_asset_decimals_setting'],
            'default' => 6,
        ]);
        register_setting('agentcart_shopbridge', self::X402_ASSET_CURRENCY_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_currency_code_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_PAY_TO_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_FACILITATOR_URL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::X402_MAX_TIMEOUT_SECONDS_OPTION, [
            'type' => 'integer',
            'sanitize_callback' => [__CLASS__, 'sanitize_x402_timeout_setting'],
            'default' => 300,
        ]);
        register_setting('agentcart_shopbridge', self::PAYMENT_VERIFIER_URL_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::PAYMENT_VERIFIER_TOKEN_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::CHECKOUT_MODE_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_checkout_mode_setting'],
            'default' => 'trusted_token_or_verifier',
        ]);
        register_setting('agentcart_shopbridge', self::SIGNED_REQUEST_MODE_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_signed_request_mode_setting'],
            'default' => 'off',
        ]);
        register_setting('agentcart_shopbridge', self::SIGNED_REQUEST_SECRET_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_signed_request_secret_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::SIGNED_REQUEST_PUBLIC_KEY_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_signed_request_public_key_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::PRODUCT_EXPOSURE_MODE_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_product_exposure_mode_setting'],
            'default' => 'manual',
        ]);
        register_setting('agentcart_shopbridge', self::PRODUCT_EXPOSURE_TAG_OPTION, [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_title',
            'default' => 'agentcart-safe',
        ]);
        register_setting('agentcart_shopbridge', self::PRODUCT_EXPOSURE_CATEGORIES_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_slug_list_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::PRODUCT_BLOCKED_CATEGORIES_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_slug_list_setting'],
            'default' => '',
        ]);
        register_setting('agentcart_shopbridge', self::STOCK_HOLD_MODE_OPTION, [
            'type' => 'string',
            'sanitize_callback' => [__CLASS__, 'sanitize_stock_hold_mode_setting'],
            'default' => 'soft',
        ]);
        register_setting('agentcart_shopbridge', self::STOCK_HOLD_MINUTES_OPTION, [
            'type' => 'integer',
            'sanitize_callback' => [__CLASS__, 'sanitize_stock_hold_minutes_setting'],
            'default' => 15,
        ]);
    }

    public static function sanitize_product_exposure_mode_setting($value) {
        $mode = sanitize_key((string) $value);
        return in_array($mode, ['manual', 'tag', 'category', 'all'], true) ? $mode : 'manual';
    }

    public static function sanitize_slug_list_setting($value) {
        $raw_values = is_array($value) ? $value : preg_split('/[\s,]+/', (string) $value);
        $slugs = [];
        foreach ((array) $raw_values as $raw_value) {
            $slug = sanitize_title((string) $raw_value);
            if ($slug !== '' && !in_array($slug, $slugs, true)) {
                $slugs[] = $slug;
            }
        }
        return implode(',', $slugs);
    }

    public static function sanitize_country_list_setting($value) {
        $raw_values = is_array($value) ? $value : preg_split('/[\s,]+/', (string) $value);
        $countries = [];
        foreach ((array) $raw_values as $raw_value) {
            $country = strtoupper(preg_replace('/[^A-Za-z]/', '', (string) $raw_value));
            if (strlen($country) === 2 && !in_array($country, $countries, true)) {
                $countries[] = $country;
            }
        }
        return implode(',', $countries);
    }

    public static function sanitize_stock_hold_mode_setting($value) {
        $mode = sanitize_key((string) $value);
        return in_array($mode, ['soft', 'hard', 'none'], true) ? $mode : 'soft';
    }

    public static function sanitize_stock_hold_minutes_setting($value) {
        $minutes = absint($value);
        return max(1, min(60, $minutes ?: 15));
    }

    public static function sanitize_x402_asset_decimals_setting($value) {
        $decimals = absint($value);
        return max(2, min(18, $decimals ?: 6));
    }

    public static function sanitize_x402_timeout_setting($value) {
        $seconds = absint($value);
        return max(30, min(3600, $seconds ?: 300));
    }

    public static function sanitize_currency_code_setting($value) {
        $currency = strtoupper(preg_replace('/[^A-Za-z]/', '', (string) $value));
        return strlen($currency) === 3 ? $currency : '';
    }

    public static function sanitize_substitution_policy_setting($value) {
        $policy = sanitize_key((string) $value);
        return in_array($policy, ['approval_required', 'not_allowed', 'merchant_allowed'], true) ? $policy : 'approval_required';
    }

    public static function sanitize_checkout_mode_setting($value) {
        $mode = sanitize_key((string) $value);
        return in_array($mode, ['trusted_token_or_verifier', 'external_verifier_only'], true) ? $mode : 'trusted_token_or_verifier';
    }

    public static function sanitize_signed_request_mode_setting($value) {
        $mode = sanitize_key((string) $value);
        return in_array($mode, ['off', 'allow', 'require_checkout', 'require_mutations', 'require_all_sensitive'], true) ? $mode : 'off';
    }

    public static function sanitize_signed_request_secret_setting($value) {
        $secret = trim(sanitize_text_field((string) $value));
        if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
            return self::signed_request_secret();
        }
        if ($secret === '') {
            delete_option(self::SIGNED_REQUEST_KEYS_OPTION);
            return '';
        }
        self::store_single_signed_request_key($secret, 'settings');
        return $secret;
    }

    public static function sanitize_signed_request_public_key_setting($value) {
        if (defined('AGENTCART_SIGNED_REQUEST_PUBLIC_KEY')) {
            return self::signed_request_public_key();
        }
        return self::normalize_signed_request_public_key((string) $value);
    }

    public static function sanitize_merchant_id_setting($value) {
        $value = strtolower(trim(sanitize_text_field((string) $value)));
        $value = preg_replace('/[^a-z0-9._-]+/', '-', $value);
        $value = trim((string) $value, '.-_');
        return substr($value, 0, 96);
    }

    public static function sanitize_cancellation_window_minutes_setting($value) {
        $minutes = absint($value);
        return min(10080, $minutes);
    }

    public static function render_settings_page() {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('You do not have permission to manage AgentCart ShopBridge.', 'agentcart-shopbridge'));
        }
        self::ensure_token();
        self::maybe_handle_support_diagnostics_download();
        $setup_action_notice = self::maybe_handle_setup_action();
        $product_action_notice = self::maybe_handle_product_exposure_action();
        $credential_action_notice = self::maybe_handle_credential_action();
        $registry_action_notice = self::maybe_handle_registry_action();
        $manifest_url = home_url('/.well-known/agentcart.json');
        $registry_proof_url = self::registry_proof_url();
        $registry_revocation_url = self::registry_revocation_url();
        $registry_bundle_url = self::registry_bundle_url();
        $support_diagnostics_url = rest_url(self::API_NAMESPACE . '/support-diagnostics');
        $registry_record_hash = self::registry_record_hash_value();
        $registry_updated_at = self::registry_updated_at();
        $registry_claim_hash = self::registry_claim_hash();
        $registry_claim_fingerprint = self::registry_claim_fingerprint();
        $registry_public_check = self::registry_public_check_result();
        $registry_connection_status = self::registry_connection_status();
        $catalog_url = rest_url(self::API_NAMESPACE . '/catalog');
        $quote_url = rest_url(self::API_NAMESPACE . '/quote');
        $orders_url = rest_url(self::API_NAMESPACE . '/orders');
        $payment_verifier_url = self::payment_verifier_url();
        $checkout_mode = self::checkout_mode();
        $signed_request_mode = self::signed_request_mode();
        $tempo_recipient = self::tempo_recipient();
        $stripe_profile_id = self::stripe_profile_id();
        $x402_network = self::x402_network();
        $x402_asset = self::x402_asset();
        $x402_asset_symbol = self::x402_asset_symbol();
        $x402_asset_decimals = self::x402_asset_decimals();
        $x402_asset_currency = self::x402_asset_currency();
        $x402_pay_to = self::x402_pay_to();
        $x402_facilitator_url = self::x402_facilitator_url();
        $x402_max_timeout_seconds = self::x402_max_timeout_seconds();
        $support_email = self::support_email();
        $returns_url = self::returns_url();
        $substitution_policy = self::substitution_policy();
        $cancellation_window_minutes = self::cancellation_window_minutes();
        $product_exposure_mode = self::product_exposure_mode();
        $product_exposure_tag = self::product_exposure_tag();
        $product_exposure_categories = self::product_exposure_categories();
        $product_blocked_categories = self::product_blocked_categories();
        $product_exposure_preview = self::product_exposure_preview_result();
        $stock_hold_mode = self::stock_hold_mode();
        $stock_hold_minutes = self::stock_hold_minutes();
        $readiness = self::readiness();
        $setup_guide = self::setup_guide($readiness);
        ?>
        <div class="wrap">
            <h1>AgentCart ShopBridge</h1>
            <?php foreach ([$setup_action_notice, $product_action_notice, $credential_action_notice, $registry_action_notice] as $notice) : ?>
                <?php if ($notice !== null) : ?>
                    <?php
                    $notice_type = 'success';
                    $notice_message = '';
                    if (is_array($notice)) {
                        $notice_type = sanitize_key((string) ($notice['type'] ?? 'success'));
                        $notice_message = (string) ($notice['message'] ?? '');
                    } else {
                        $notice_message = (string) $notice;
                    }
                    $notice_class = in_array($notice_type, ['success', 'warning', 'error', 'info'], true) ? 'notice-' . $notice_type : 'notice-success';
                    ?>
                    <div class="notice <?php echo esc_attr($notice_class); ?> is-dismissible"><p><?php echo esc_html($notice_message); ?></p></div>
                <?php endif; ?>
            <?php endforeach; ?>
            <p>
                Expose this WooCommerce store to household agents through machine-readable discovery,
                catalog, quote, paid-order, and order-status endpoints. WooCommerce stays the source of
                truth for products, stock, tax, shipping, fulfillment, refunds, and support.
            </p>

            <h2>Guided Setup</h2>
            <p style="max-width: 760px;">
                Complete these steps to move from local testing to production-shaped agent checkout.
                The plugin keeps registry proof values and product endpoints generated from WooCommerce settings.
            </p>
            <?php self::render_setup_wizard_panel($setup_guide, $readiness); ?>
            <?php self::render_setup_guide($setup_guide); ?>

            <h2 id="agentcart-readiness">Readiness</h2>
            <table class="widefat striped" style="max-width: 980px;">
                <tbody>
                    <tr>
                        <th scope="row">Discovery manifest</th>
                        <td><code><?php echo esc_html($manifest_url); ?></code></td>
                        <td><?php self::render_admin_status_badge(true, 'Published'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Registry domain proof</th>
                        <td><code><?php echo esc_html($registry_proof_url); ?></code></td>
                        <td><?php self::render_admin_status_badge(self::registry_domain_proof_configured(), 'Auto-managed', 'Needs merchant id'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Registry revocations</th>
                        <td><code><?php echo esc_html($registry_revocation_url); ?></code></td>
                        <td><?php self::render_admin_status_badge(true, 'Published'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Registry onboarding bundle</th>
                        <td><code><?php echo esc_html($registry_bundle_url); ?></code></td>
                        <td><?php self::render_admin_status_badge(self::registry_domain_proof_configured(), 'Ready'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Merchant token</th>
                        <td>Used by a trusted AgentCart gateway for demo or private integrations.</td>
                        <td><?php self::render_admin_status_badge((bool) self::merchant_token_value(), 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Tempo recipient</th>
                        <td><code><?php echo esc_html($tempo_recipient ?: 'not configured'); ?></code></td>
                        <td><?php self::render_admin_status_badge($tempo_recipient !== '', 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Payment verifier</th>
                        <td><code><?php echo esc_html($payment_verifier_url ?: 'trusted gateway token mode'); ?></code></td>
                        <td><?php self::render_admin_status_badge($payment_verifier_url !== '', 'Production shape', 'Demo mode'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Checkout mode</th>
                        <td><?php echo esc_html(self::checkout_mode_label($checkout_mode)); ?></td>
                        <td><?php self::render_admin_status_badge(self::external_verifier_required_for_checkout(), 'Verifier only', 'Token fallback enabled'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Signed HTTP requests</th>
                        <td><?php echo esc_html(self::signed_request_mode_label($signed_request_mode)); ?></td>
                        <td><?php self::render_admin_status_badge(self::signed_request_profile_configured(), 'Configured', 'Off or missing signing key'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Stripe/card MPP</th>
                        <td><code><?php echo esc_html($stripe_profile_id ?: 'not configured'); ?></code></td>
                        <td><?php self::render_admin_status_badge($stripe_profile_id !== '' && $payment_verifier_url !== '', 'Configured', 'Needs Stripe profile + verifier'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">x402 exact profile</th>
                        <td><code><?php echo esc_html(self::x402_profile_configured() ? $x402_network . ' / ' . $x402_asset_symbol : 'not configured'); ?></code></td>
                        <td><?php self::render_admin_status_badge(self::x402_profile_configured(), 'Configured', 'Needs network + asset + payTo + verifier'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Support email</th>
                        <td><code><?php echo esc_html($support_email ?: 'not published'); ?></code></td>
                        <td><?php self::render_admin_status_badge($support_email !== '', 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Public origin</th>
                        <td><code><?php echo esc_html(home_url('/')); ?></code></td>
                        <td><?php self::render_admin_status_badge(self::public_origin_is_https(), 'HTTPS', 'Needs HTTPS'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Legal pages</th>
                        <td><?php echo esc_html(self::legal_pages_configured() ? 'Terms and returns pages are configured.' : 'Terms and returns pages need review.'); ?></td>
                        <td><?php self::render_admin_status_badge(self::legal_pages_configured(), 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Aftercare policy</th>
                        <td><?php echo esc_html(self::merchant_policy_summary()); ?></td>
                        <td><?php self::render_admin_status_badge($returns_url !== '', 'Published', 'Needs returns URL'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Tax and shipping</th>
                        <td><?php echo esc_html(self::tax_and_shipping_configured() ? 'WooCommerce tax and shipping countries are configured.' : 'Review WooCommerce tax and shipping setup before production.'); ?></td>
                        <td><?php self::render_admin_status_badge(self::tax_and_shipping_configured(), 'Configured', 'Needs setup'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">AgentCart-enabled products</th>
                        <td><?php echo esc_html((string) $readiness['agentcart_enabled_product_count']); ?> published simple products are exposed through <?php echo esc_html(self::product_exposure_mode_label($product_exposure_mode)); ?>.</td>
                        <td><?php self::render_admin_status_badge($readiness['agentcart_enabled_product_count'] > 0, 'Configured', 'None enabled'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Demo readiness</th>
                        <td><?php echo esc_html(empty($readiness['missing_for_demo']) ? 'Ready for agent catalog, quote, order, and refund demo.' : implode(', ', $readiness['missing_for_demo'])); ?></td>
                        <td><?php self::render_admin_status_badge($readiness['demo_ready'], 'Demo ready', 'Needs setup'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Production readiness</th>
                        <td><?php echo esc_html(empty($readiness['missing_for_production']) ? 'External payment verifier and merchant rail settings are configured.' : implode(', ', $readiness['missing_for_production'])); ?></td>
                        <td><?php self::render_admin_status_badge($readiness['production_ready'], 'Production-shaped', 'Roadmap'); ?></td>
                    </tr>
                </tbody>
            </table>

            <h2 id="agentcart-endpoints">Endpoints</h2>
            <table class="widefat striped" style="max-width: 980px;">
                <tbody>
                    <tr><th scope="row">Manifest</th><td><code><?php echo esc_html($manifest_url); ?></code></td></tr>
                    <tr><th scope="row">Registry proof</th><td><code><?php echo esc_html($registry_proof_url); ?></code></td></tr>
                    <tr><th scope="row">Registry revocations</th><td><code><?php echo esc_html($registry_revocation_url); ?></code></td></tr>
                    <tr><th scope="row">Registry bundle</th><td><code><?php echo esc_html($registry_bundle_url); ?></code></td></tr>
                    <tr><th scope="row">Catalog</th><td><code><?php echo esc_html($catalog_url); ?></code></td></tr>
                    <tr><th scope="row">Quote</th><td><code><?php echo esc_html($quote_url); ?></code></td></tr>
                    <tr><th scope="row">Paid order</th><td><code><?php echo esc_html($orders_url); ?></code></td></tr>
                    <tr><th scope="row">Support diagnostics</th><td><code><?php echo esc_html($support_diagnostics_url); ?></code></td></tr>
                </tbody>
            </table>

            <h2 id="agentcart-registry-proof">Registry Proof</h2>
            <p style="max-width: 760px;">
                A public AgentCart registry can verify this shop through a merchant-owned
                <code>https-domain-proof</code>. The registry claim, timestamp, and canonical
                record hash are generated automatically from stable merchant, payment, shipping,
                and endpoint settings. Normal product, stock, quote, and readiness changes do not
                require merchants to paste new hashes.
            </p>
            <table class="widefat striped" style="max-width: 980px;">
                <tbody>
                    <tr><th scope="row">Proof URL</th><td><code><?php echo esc_html($registry_proof_url); ?></code></td></tr>
                    <tr><th scope="row">Revocation URL</th><td><code><?php echo esc_html($registry_revocation_url); ?></code></td></tr>
                    <tr><th scope="row">Registry bundle URL</th><td><code><?php echo esc_html($registry_bundle_url); ?></code></td></tr>
                    <tr><th scope="row">Registry claim hash</th><td><code><?php echo esc_html($registry_claim_hash); ?></code></td></tr>
                    <tr><th scope="row">Registry record hash</th><td><code><?php echo esc_html($registry_record_hash); ?></code></td></tr>
                    <tr><th scope="row">Registry updated_at</th><td><code><?php echo esc_html($registry_updated_at); ?></code></td></tr>
                    <tr><th scope="row">Stable claim fingerprint</th><td><code><?php echo esc_html($registry_claim_fingerprint); ?></code></td></tr>
                </tbody>
            </table>
            <?php self::render_registry_transparency_panel($registry_public_check, $registry_connection_status); ?>

            <h2 id="agentcart-settings">Settings</h2>
            <form id="agentcart-settings-form" method="post" action="options.php">
                <?php settings_fields('agentcart_shopbridge'); ?>
                <table class="form-table" role="presentation">
                    <?php self::render_text_setting_row('Merchant id', self::MERCHANT_ID_OPTION, self::merchant_id(), 'AGENTCART_MERCHANT_ID', 'Stable public id for registry records, quote approvals, payment verification, and order audit. Use a domain-like or slug value such as shop.example or my-shop.'); ?>
                    <?php self::render_text_setting_row('Merchant token', self::TOKEN_OPTION, self::merchant_token_value(), 'AGENTCART_SHOPBRIDGE_TOKEN', 'Shared secret for a trusted AgentCart gateway. Production public checkout should use a payment verifier.'); ?>
                    <?php self::render_text_setting_row('Support email', self::SUPPORT_EMAIL_OPTION, $support_email, 'AGENTCART_SUPPORT_EMAIL', 'Published in the merchant-of-record block for customer support.'); ?>
                    <?php self::render_text_setting_row('Returns policy URL', self::RETURNS_URL_OPTION, $returns_url, 'AGENTCART_RETURNS_URL', 'Published to buyer agents for refunds, returns, cancellation requests, and support handoff. Defaults to /returns when no override is set.'); ?>
                    <?php self::render_text_setting_row('Registry connection URL', self::REGISTRY_CONNECTION_URL_OPTION, self::registry_connection_url(), 'AGENTCART_REGISTRY_CONNECTION_URL', 'Optional hosted registry ingestion endpoint. When configured, Registry Proof actions can submit the generated bundle or a revocation request without copy/paste.'); ?>
                    <?php self::render_password_setting_row('Registry connection token', self::REGISTRY_CONNECTION_TOKEN_OPTION, self::registry_connection_token(), 'AGENTCART_REGISTRY_CONNECTION_TOKEN', 'Optional bearer token for the configured registry connection endpoint. Leave blank when the registry is public or uses domain-proof only.'); ?>
                    <?php self::render_aftercare_policy_setting_rows($substitution_policy, $cancellation_window_minutes); ?>
                    <?php self::render_text_setting_row('Tempo network', self::TEMPO_NETWORK_OPTION, self::tempo_network(), 'AGENTCART_TEMPO_NETWORK', 'For the hackathon this is usually testnet.'); ?>
                    <?php self::render_text_setting_row('Tempo recipient address', self::TEMPO_RECIPIENT_OPTION, $tempo_recipient, 'AGENTCART_TEMPO_RECIPIENT_ADDRESS', 'Merchant or payment-provider recipient used by the payment verifier.'); ?>
                    <?php self::render_text_setting_row('Stripe profile / network id', self::STRIPE_PROFILE_ID_OPTION, $stripe_profile_id, 'AGENTCART_STRIPE_PROFILE_ID', 'Optional Stripe Business Network/profile id for card/SPT MPP. Requires a verifier that can validate Stripe credentials and refunds.'); ?>
                    <?php self::render_text_setting_row('x402 network', self::X402_NETWORK_OPTION, $x402_network, 'AGENTCART_X402_NETWORK', 'Optional x402 network identifier such as eip155:84532 or base-sepolia. Leave blank to avoid advertising x402.'); ?>
                    <?php self::render_text_setting_row('x402 asset contract', self::X402_ASSET_OPTION, $x402_asset, 'AGENTCART_X402_ASSET', 'Optional x402 token contract/address. Required before x402-compatible quotes are advertised.'); ?>
                    <?php self::render_text_setting_row('x402 asset symbol', self::X402_ASSET_SYMBOL_OPTION, $x402_asset_symbol, 'AGENTCART_X402_ASSET_SYMBOL', 'Human label for the configured x402 asset, for example USDC.'); ?>
                    <?php self::render_text_setting_row('x402 asset currency', self::X402_ASSET_CURRENCY_OPTION, $x402_asset_currency, 'AGENTCART_X402_ASSET_CURRENCY', 'Three-letter currency represented by the x402 asset. Defaults to the WooCommerce store currency when blank.'); ?>
                    <?php self::render_setting_row('number', 'x402 asset decimals', self::X402_ASSET_DECIMALS_OPTION, $x402_asset_decimals, 'AGENTCART_X402_ASSET_DECIMALS', 'Token decimals used to convert WooCommerce cents into x402 atomic units.'); ?>
                    <?php self::render_text_setting_row('x402 payTo address', self::X402_PAY_TO_OPTION, $x402_pay_to, 'AGENTCART_X402_PAY_TO', 'Merchant or payment-provider wallet address that receives x402 exact payments.'); ?>
                    <?php self::render_text_setting_row('x402 facilitator URL', self::X402_FACILITATOR_URL_OPTION, $x402_facilitator_url, 'AGENTCART_X402_FACILITATOR_URL', 'Optional facilitator URL documented for x402-capable clients. ShopBridge still relies on the payment verifier before creating orders.'); ?>
                    <?php self::render_setting_row('number', 'x402 timeout seconds', self::X402_MAX_TIMEOUT_SECONDS_OPTION, $x402_max_timeout_seconds, 'AGENTCART_X402_MAX_TIMEOUT_SECONDS', 'Maximum x402 authorization window advertised in quote-bound payment requirements.'); ?>
                    <?php self::render_text_setting_row('Payment verifier URL', self::PAYMENT_VERIFIER_URL_OPTION, $payment_verifier_url, 'AGENTCART_PAYMENT_VERIFIER_URL', 'Endpoint that verifies quote-bound Tempo or Stripe MPP receipts before WooCommerce creates a paid order, and rail-bound refunds before recording a production refund.'); ?>
                    <?php self::render_password_setting_row('Payment verifier token', self::PAYMENT_VERIFIER_TOKEN_OPTION, self::payment_verifier_token(), 'AGENTCART_PAYMENT_VERIFIER_TOKEN', 'Optional bearer token sent from this plugin to the verifier.'); ?>
                    <?php self::render_checkout_mode_setting_row($checkout_mode); ?>
                    <?php self::render_signed_request_mode_setting_row($signed_request_mode); ?>
                    <?php self::render_password_setting_row('Active signed request secret', self::SIGNED_REQUEST_SECRET_OPTION, self::signed_request_secret(), 'AGENTCART_SIGNED_REQUEST_SECRET', 'Current HMAC secret for request-bound signatures. Saving this field creates one active signing key; use Credential Actions for rotation with a retirement window.'); ?>
                    <?php self::render_textarea_setting_row('Signed request RSA public key', self::SIGNED_REQUEST_PUBLIC_KEY_OPTION, self::signed_request_public_key(), 'AGENTCART_SIGNED_REQUEST_PUBLIC_KEY', 'Optional RSA public key PEM for asymmetric request signatures. Buyer agents sign the same canonical request with the matching private key and send X-AgentCart-Signature-Alg: rsa-sha256.'); ?>
                    <?php self::render_product_exposure_setting_rows($product_exposure_mode, $product_exposure_tag, $product_exposure_categories, $product_blocked_categories); ?>
                    <?php self::render_stock_hold_setting_rows($stock_hold_mode, $stock_hold_minutes); ?>
                </table>
                <?php submit_button('Save AgentCart settings'); ?>
            </form>

            <h2 id="agentcart-credentials">Credential Actions</h2>
            <p style="max-width: 760px;">
                Generate or rotate local ShopBridge secrets without editing code. Values managed
                in <code>wp-config.php</code> stay locked here so production deployments can keep
                using infrastructure-managed secrets.
            </p>
            <?php self::render_credential_action_forms(); ?>
            <?php self::render_signed_request_audit_panel(); ?>
            <?php self::render_support_diagnostics_panel(); ?>

            <h2 id="agentcart-product-exposure">Product Exposure</h2>
            <p style="max-width: 760px;">
                Products are private by default in manual mode. Merchants can also expose products
                by assigning a normal WooCommerce product tag, or intentionally expose all published
                simple products when the whole catalog is safe for agent checkout.
            </p>
            <p style="max-width: 760px;">
                Current mode: <strong><?php echo esc_html(self::product_exposure_mode_label($product_exposure_mode)); ?></strong>
                <?php if ($product_exposure_mode === 'tag') : ?>
                    using tag <code><?php echo esc_html($product_exposure_tag); ?></code>.
                <?php elseif ($product_exposure_mode === 'category') : ?>
                    using categories <code><?php echo esc_html(implode(', ', $product_exposure_categories) ?: 'none'); ?></code>.
                <?php endif; ?>
            </p>
            <?php self::render_product_exposure_preview_panel($product_exposure_preview); ?>
            <form method="post" style="display: inline-block; margin-right: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_product_action'); ?>
                <input type="hidden" name="agentcart_product_action" value="preview_catalog_exposure" />
                <?php submit_button('Preview catalog exposure', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block; margin-right: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_product_action'); ?>
                <input type="hidden" name="agentcart_product_action" value="save_catalog_snapshot" />
                <?php submit_button('Save current catalog snapshot', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block; margin-right: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_product_action'); ?>
                <input type="hidden" name="agentcart_product_action" value="enable_all_published_simple" />
                <?php submit_button('Enable all published simple products', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block;">
                <?php wp_nonce_field('agentcart_shopbridge_product_action'); ?>
                <input type="hidden" name="agentcart_product_action" value="disable_all" />
                <?php submit_button('Disable all AgentCart product exposure', 'secondary', 'submit', false); ?>
            </form>

            <h2>Merchant Onboarding Checklist</h2>
            <ol>
                <li>Add normal WooCommerce products, prices, stock, VAT/tax, and shipping countries.</li>
                <li>Choose a Product exposure mode: manual product checkbox, WooCommerce tag, or all published simple products.</li>
                <li>Configure this page with support, Tempo recipient, and payment verification settings.</li>
                <li>Share the registry bundle URL with the AgentCart discovery registry, or configure the hosted registry connection and submit it from this page.</li>
                <li>The registry proof hash and timestamp are maintained automatically by the plugin.</li>
                <li>Run a sandbox quote and order test before allowing public agent checkout.</li>
            </ol>
        </div>
        <?php
    }

    private static function maybe_handle_setup_action() {
        if (strtoupper((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'] ?? ''))) !== 'POST') {
            return null;
        }
        if (empty($_POST['agentcart_setup_action'])) {
            return null;
        }
        check_admin_referer('agentcart_shopbridge_setup_action');
        $action = sanitize_key((string) wp_unslash($_POST['agentcart_setup_action']));

        if ($action === 'prepare_sandbox_secrets') {
            return self::prepare_sandbox_defaults();
        }
        if ($action === 'run_sandbox_quote_check') {
            $result = self::run_sandbox_quote_check();
            update_option(self::SANDBOX_QUOTE_CHECK_OPTION, $result, false);
            if (($result['state'] ?? '') === 'passed') {
                return 'Sandbox quote check passed: WooCommerce returned a quote for ' . ($result['product_title'] ?? 'an AgentCart product') . '.';
            }
            return [
                'type' => 'error',
                'message' => 'Sandbox quote check failed: ' . ($result['message'] ?? 'review the Quick Start panel for details.'),
            ];
        }
        if ($action === 'run_sandbox_checkout_test') {
            $result = self::run_sandbox_checkout_test();
            update_option(self::SANDBOX_CHECKOUT_TEST_OPTION, $result, false);
            if (($result['state'] ?? '') === 'passed') {
                return 'Sandbox checkout test passed: test order #' . ($result['order_number'] ?? $result['order_id'] ?? '') . ' was created and cancelled.';
            }
            return [
                'type' => 'error',
                'message' => 'Sandbox checkout test failed: ' . ($result['message'] ?? 'review the Quick Start panel for details.'),
            ];
        }

        return null;
    }

    private static function prepare_sandbox_defaults() {
        $changes = [];
        if (!defined('AGENTCART_SHOPBRIDGE_TOKEN') && !self::merchant_token_value()) {
            update_option(self::TOKEN_OPTION, wp_generate_password(48, false, false), false);
            $changes[] = 'merchant token';
        }
        if (!defined('AGENTCART_SIGNED_REQUEST_SECRET') && !self::signed_request_active_key()) {
            $key = self::create_initial_signed_request_key();
            update_option(self::SIGNED_REQUEST_SECRET_OPTION, (string) ($key['secret'] ?? ''), false);
            $changes[] = 'signed request signing key';
        }
        if (!defined('AGENTCART_SIGNED_REQUEST_MODE') && self::signed_request_mode() === 'off') {
            update_option(self::SIGNED_REQUEST_MODE_OPTION, 'allow', false);
            $changes[] = 'signed request allow mode';
        }
        if (!defined('AGENTCART_REGISTRY_UPDATED_AT')) {
            update_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION, self::registry_claim_fingerprint(), false);
            update_option(self::REGISTRY_UPDATED_AT_OPTION, self::current_registry_timestamp(), false);
            delete_option(self::REGISTRY_PUBLIC_CHECK_OPTION);
            $changes[] = 'registry metadata';
        }

        if (empty($changes)) {
            return 'Sandbox access defaults are already prepared or managed in wp-config.php.';
        }
        return 'Sandbox access prepared: ' . implode(', ', $changes) . '. Review product exposure and payment settings before public checkout.';
    }

    private static function run_sandbox_quote_check() {
        $checked_at = gmdate('c');
        $ship_to = self::sandbox_quote_ship_to();
        $product = self::sandbox_quote_test_product($ship_to['country']);
        if (!$product instanceof WC_Product) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'message' => 'No published, in-stock, AgentCart-enabled simple product can ship to ' . $ship_to['country'] . '.',
                'ship_to' => $ship_to,
            ];
        }

        $request = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/quote');
        $request->set_header('Content-Type', 'application/json');
        $request->set_body(wp_json_encode([
            'items' => [
                [
                    'product_id' => 'woo_' . $product->get_id(),
                    'quantity' => 1,
                ],
            ],
            'ship_to' => $ship_to,
        ]));

        $quote = self::quote($request);
        if (is_wp_error($quote)) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'error_code' => $quote->get_error_code(),
                'message' => $quote->get_error_message(),
                'error_data' => $quote->get_error_data(),
            ];
        }
        if (!is_array($quote)) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'message' => 'Quote endpoint returned an unexpected response.',
            ];
        }

        $quote_id = (string) ($quote['id'] ?? '');
        if ($quote_id !== '') {
            delete_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id);
            self::release_stock_hold($quote_id);
        }
        $shipping = isset($quote['shipping']) && is_array($quote['shipping']) ? $quote['shipping'] : [];
        $vat_lines = isset($quote['vat_lines']) && is_array($quote['vat_lines']) ? $quote['vat_lines'] : [];
        $payment_requirements = isset($quote['payment_requirements']) && is_array($quote['payment_requirements']) ? $quote['payment_requirements'] : [];

        return [
            'state' => 'passed',
            'checked_at' => $checked_at,
            'product_id' => 'woo_' . $product->get_id(),
            'product_title' => $product->get_name(),
            'ship_to' => $ship_to,
            'quote_id' => $quote_id,
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'subtotal_cents' => intval($quote['subtotal_cents'] ?? 0),
            'shipping_cents' => intval($shipping['amount_cents'] ?? 0),
            'shipping_label' => (string) ($shipping['label'] ?? ''),
            'total_cents' => intval($quote['total_cents'] ?? 0),
            'vat_line_count' => count($vat_lines),
            'payment_protocol_profile_ids' => isset($payment_requirements['payment_protocol_profile_ids']) && is_array($payment_requirements['payment_protocol_profile_ids'])
                ? array_values(array_map('strval', $payment_requirements['payment_protocol_profile_ids']))
                : [],
            'cleanup' => 'quote transient deleted and soft stock hold released',
        ];
    }

    private static function run_sandbox_checkout_test() {
        $checked_at = gmdate('c');
        $ship_to = self::sandbox_quote_ship_to();
        $product = self::sandbox_quote_test_product($ship_to['country']);
        if (!$product instanceof WC_Product) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'message' => 'No published, in-stock, AgentCart-enabled simple product can ship to ' . $ship_to['country'] . '.',
                'ship_to' => $ship_to,
            ];
        }

        if (self::merchant_token_value() === '' && self::payment_verifier_url() === '') {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'message' => 'Merchant token or external verifier is required before the checkout test can create a test order.',
            ];
        }

        $quote_request = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/quote');
        $quote_request->set_header('Content-Type', 'application/json');
        $quote_request->set_body(wp_json_encode([
            'items' => [
                [
                    'product_id' => 'woo_' . $product->get_id(),
                    'quantity' => 1,
                ],
            ],
            'ship_to' => $ship_to,
        ]));

        $quote = self::quote($quote_request);
        if (is_wp_error($quote)) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'error_code' => $quote->get_error_code(),
                'message' => $quote->get_error_message(),
                'error_data' => $quote->get_error_data(),
            ];
        }
        if (!is_array($quote)) {
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'message' => 'Quote endpoint returned an unexpected response.',
            ];
        }

        $quote_id = (string) ($quote['id'] ?? '');
        $order_idempotency_key = 'agentcart-sandbox-checkout-' . substr(hash('sha256', $quote_id . '|' . wp_generate_uuid4()), 0, 24);
        $receipt = self::sandbox_checkout_payment_receipt($quote, $order_idempotency_key);
        $approval = self::sandbox_checkout_approval_record($quote, $order_idempotency_key, $checked_at);
        $order_request = new WP_REST_Request('POST', '/' . self::API_NAMESPACE . '/orders');
        $order_request->set_header('Content-Type', 'application/json');
        $order_request->set_header('Idempotency-Key', $order_idempotency_key);
        if (self::merchant_token_value() !== '') {
            $order_request->set_header('X-AgentCart-Merchant-Token', self::merchant_token_value());
        }
        $order_request->set_body(wp_json_encode([
            'agentcart_order_id' => $order_idempotency_key,
            'idempotency_key' => $order_idempotency_key,
            'agentcart_quote_id' => $quote_id,
            'merchant_quote_id' => $quote_id,
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'approval_id' => (string) ($approval['approval_id'] ?? ''),
            'approval_hash' => (string) ($approval['approval_hash'] ?? ''),
            'approval_record_hash' => (string) ($approval['approval_record_hash'] ?? ''),
            'approval_decision_hash' => (string) ($approval['approval_decision_hash'] ?? ''),
            'approval' => $approval,
            'approval_record' => $approval['approval_record'] ?? null,
            'approval_decision_record' => $approval['approval_decision_record'] ?? null,
            'rail' => 'tempo-mpp',
            'reason' => 'AgentCart sandbox checkout test from WooCommerce admin',
            'ship_to' => $ship_to,
            'payment_receipt' => $receipt,
        ]));

        $order_response = self::create_order($order_request);
        if (is_wp_error($order_response)) {
            if ($quote_id !== '') {
                delete_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id);
                self::release_stock_hold($quote_id);
            }
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'quote_id' => $quote_id,
                'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
                'error_code' => $order_response->get_error_code(),
                'message' => $order_response->get_error_message(),
                'error_data' => $order_response->get_error_data(),
                'cleanup' => 'quote transient deleted and soft stock hold released after failed checkout test',
            ];
        }
        if (!is_array($order_response)) {
            if ($quote_id !== '') {
                delete_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id);
                self::release_stock_hold($quote_id);
            }
            return [
                'state' => 'failed',
                'checked_at' => $checked_at,
                'product_id' => 'woo_' . $product->get_id(),
                'product_title' => $product->get_name(),
                'ship_to' => $ship_to,
                'quote_id' => $quote_id,
                'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
                'message' => 'Order endpoint returned an unexpected response.',
                'cleanup' => 'quote transient deleted and soft stock hold released after unexpected checkout response',
            ];
        }

        $order_id = intval($order_response['id'] ?? 0);
        $order = $order_id > 0 ? wc_get_order($order_id) : null;
        if ($quote_id !== '') {
            delete_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id);
            self::release_stock_hold($quote_id, 'sandbox_checkout_cleanup');
        }
        $cleanup = 'test order created; quote transient deleted and soft stock hold released';
        if ($order instanceof WC_Order) {
            $order->update_meta_data('_agentcart_sandbox_checkout_test', 'yes');
            $order->update_meta_data('_agentcart_sandbox_approval_hash', sanitize_text_field((string) ($approval['approval_hash'] ?? '')));
            $order->add_order_note('AgentCart sandbox checkout test created this order. Cancelling it immediately; no rail refund is executed by the setup test.');
            try {
                $order->update_status('cancelled', 'AgentCart sandbox checkout test cleanup cancelled this test order.', true);
                $cleanup = 'test order created and cancelled; quote transient deleted and soft stock hold released; no external refund executed';
            } catch (Exception $exception) {
                $cleanup = 'test order created; quote transient deleted and soft stock hold released; automatic cancellation failed: ' . $exception->getMessage();
            }
            $order->save();
        }

        $payment_verification = is_array($order_response['payment_verification'] ?? null) ? $order_response['payment_verification'] : [];
        $shipping = isset($quote['shipping']) && is_array($quote['shipping']) ? $quote['shipping'] : [];
        $vat_lines = isset($quote['vat_lines']) && is_array($quote['vat_lines']) ? $quote['vat_lines'] : [];
        return [
            'state' => 'passed',
            'checked_at' => $checked_at,
            'product_id' => 'woo_' . $product->get_id(),
            'product_title' => $product->get_name(),
            'ship_to' => $ship_to,
            'quote_id' => $quote_id,
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'approval_id' => (string) ($approval['approval_id'] ?? ''),
            'approval_hash' => (string) ($approval['approval_hash'] ?? ''),
            'approval_record_hash' => (string) ($approval['approval_record_hash'] ?? ''),
            'approval_decision_hash' => (string) ($approval['approval_decision_hash'] ?? ''),
            'order_id' => (string) $order_id,
            'order_number' => (string) ($order_response['number'] ?? ($order instanceof WC_Order ? $order->get_order_number() : '')),
            'order_status' => $order instanceof WC_Order ? $order->get_status() : (string) ($order_response['status'] ?? ''),
            'order_url' => $order instanceof WC_Order ? admin_url('post.php?post=' . $order->get_id() . '&action=edit') : (string) ($order_response['url'] ?? ''),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'total_cents' => intval($quote['total_cents'] ?? 0),
            'shipping_cents' => intval($shipping['amount_cents'] ?? 0),
            'vat_line_count' => count($vat_lines),
            'payment_mode' => (string) ($payment_verification['mode'] ?? ''),
            'payment_contract_hash' => (string) ($payment_verification['payment_contract_hash'] ?? $receipt['payment_contract_hash'] ?? ''),
            'real_settlement_verified' => !empty($payment_verification['real_settlement_verified']),
            'cleanup' => $cleanup,
        ];
    }

    private static function sandbox_checkout_approval_record($quote, $order_idempotency_key, $checked_at) {
        $quote = is_array($quote) ? $quote : [];
        $merchant = isset($quote['merchant']) && is_array($quote['merchant']) ? $quote['merchant'] : self::merchant();
        $quote_id = (string) ($quote['id'] ?? '');
        $quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $approval_id = 'approval_sandbox_' . substr(hash('sha256', $order_idempotency_key), 0, 16);
        $approval_material = [
            'merchant_id' => (string) ($merchant['id'] ?? self::merchant_id()),
            'quote_id' => $quote_id,
            'quote_hash' => $quote_hash,
            'total_cents' => intval($quote['total_cents'] ?? 0),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'payment_destination' => [
                'rail' => 'tempo-mpp',
                'network' => self::tempo_network(),
                'recipient' => self::tempo_recipient(),
            ],
        ];
        $approval_hash = hash('sha256', (string) wp_json_encode($approval_material));
        $approval_record = [
            'schema' => 'agentcart.approval_record.v1',
            'approval_id' => $approval_id,
            'approval_hash' => $approval_hash,
            'approval_material' => $approval_material,
            'human_approval_required' => true,
            'channel' => 'woocommerce_admin',
            'approver' => 'woocommerce_admin_sandbox',
            'approved_at' => $checked_at,
            'record_role' => 'sandbox_admin_approval_contract',
        ];
        $approval_record['approval_record_hash'] = hash('sha256', (string) wp_json_encode($approval_record));
        $decision_record = [
            'schema' => 'agentcart.approval_decision_record.v1',
            'approval_id' => $approval_id,
            'quote_id' => $quote_id,
            'quote_hash' => $quote_hash,
            'approval_record_hash' => $approval_record['approval_record_hash'],
            'decision' => 'approved',
            'channel' => 'woocommerce_admin',
            'approver' => 'woocommerce_admin_sandbox',
            'decided_at' => $checked_at,
            'reason' => 'WooCommerce admin explicitly ran the AgentCart sandbox checkout test.',
        ];
        $decision_record['decision_record_hash'] = hash('sha256', (string) wp_json_encode($decision_record));
        return [
            'approval_id' => $approval_id,
            'approval_hash' => $approval_hash,
            'approval_record_hash' => $approval_record['approval_record_hash'],
            'approval_decision_hash' => $decision_record['decision_record_hash'],
            'approval_record' => $approval_record,
            'approval_decision_record' => $decision_record,
            'approved' => true,
        ];
    }

    private static function sandbox_checkout_payment_receipt($quote, $order_idempotency_key) {
        $quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $contract = self::payment_verification_contract($quote, 'tempo-mpp');
        $contract_hash = self::payment_contract_hash($contract);
        $amount_cents = intval($quote['total_cents'] ?? 0);
        $currency = (string) ($quote['currency'] ?? get_woocommerce_currency());
        $transaction_reference = 'agentcart_sandbox_' . substr(hash('sha256', $order_idempotency_key . '|' . $quote_hash), 0, 24);
        return [
            'id' => 'payrcpt_' . substr(hash('sha256', $transaction_reference), 0, 24),
            'method' => 'tempo-mpp',
            'rail' => 'tempo-mpp',
            'provider' => 'agentcart_sandbox',
            'status' => 'succeeded',
            'amount_cents' => $amount_cents,
            'currency' => $currency,
            'quote_hash' => $quote_hash,
            'payment_contract_hash' => $contract_hash,
            'external_value_proof' => [
                'provider' => 'tempo_mpp',
                'state' => 'succeeded',
                'network' => self::tempo_network(),
                'recipient' => self::tempo_recipient(),
                'body' => [
                    'amount' => number_format($amount_cents / 100, 2, '.', ''),
                    'recipient' => self::tempo_recipient(),
                    'transaction_reference' => $transaction_reference,
                ],
                'payment_receipt' => [
                    'reference' => $transaction_reference,
                    'network' => self::tempo_network(),
                ],
            ],
            'sandbox' => true,
        ];
    }

    private static function sandbox_quote_test_product($country) {
        if (!function_exists('wc_get_products')) {
            return null;
        }
        $products = wc_get_products(array_merge(self::agentcart_product_query_args(), [
            'limit' => 25,
            'return' => 'objects',
        ]));
        foreach ($products as $product) {
            if (!$product instanceof WC_Product || !self::is_product_agentcart_enabled($product)) {
                continue;
            }
            if (!self::product_ships_to_country($product, $country)) {
                continue;
            }
            if (is_wp_error(self::validate_product_stock_for_agentcart($product, 1))) {
                continue;
            }
            return $product;
        }
        return null;
    }

    private static function sandbox_quote_ship_to() {
        $countries = self::shipping_countries();
        $base_country = class_exists('WooCommerce') && WC() && WC()->countries ? strtoupper((string) WC()->countries->get_base_country()) : 'DE';
        $country = in_array($base_country, $countries, true) ? $base_country : (string) ($countries[0] ?? 'DE');
        return [
            'first_name' => 'AgentCart',
            'last_name' => 'Sandbox',
            'address_1' => 'Sandbox Street 1',
            'city' => self::sandbox_quote_city($country),
            'postcode' => self::sandbox_quote_postcode($country),
            'country' => $country,
            'email' => self::support_email() ?: 'agentcart-sandbox@example.invalid',
        ];
    }

    private static function sandbox_quote_postcode($country) {
        $postcodes = [
            'AT' => '1010',
            'BE' => '1000',
            'CH' => '8001',
            'DE' => '10115',
            'DK' => '1050',
            'FR' => '75001',
            'LU' => '1111',
            'NL' => '1012',
            'PL' => '00-001',
            'US' => '10001',
        ];
        return $postcodes[$country] ?? '1000';
    }

    private static function sandbox_quote_city($country) {
        $cities = [
            'AT' => 'Wien',
            'BE' => 'Brussels',
            'CH' => 'Zuerich',
            'DE' => 'Berlin',
            'DK' => 'Copenhagen',
            'FR' => 'Paris',
            'LU' => 'Luxembourg',
            'NL' => 'Amsterdam',
            'PL' => 'Warsaw',
            'US' => 'New York',
        ];
        return $cities[$country] ?? 'Test City';
    }

    private static function maybe_handle_product_exposure_action() {
        if (strtoupper((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'] ?? ''))) !== 'POST') {
            return null;
        }
        if (empty($_POST['agentcart_product_action'])) {
            return null;
        }
        check_admin_referer('agentcart_shopbridge_product_action');
        $action = sanitize_key((string) wp_unslash($_POST['agentcart_product_action']));
        if ($action === 'preview_catalog_exposure') {
            $preview = self::build_product_exposure_preview();
            update_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION, $preview, false);
            if (($preview['state'] ?? '') === 'passed') {
                $diff = is_array($preview['catalog_diff'] ?? null) ? $preview['catalog_diff'] : [];
                return sprintf(
                    'Product exposure preview generated: %d products would enter the AgentCart catalog. Diff: %d added, %d removed, %d changed.',
                    intval($preview['included_count'] ?? 0),
                    intval($diff['added_count'] ?? 0),
                    intval($diff['removed_count'] ?? 0),
                    intval($diff['changed_count'] ?? 0)
                );
            }
            return [
                'type' => 'error',
                'message' => 'Product exposure preview failed: ' . ($preview['message'] ?? 'review product exposure settings.'),
            ];
        }
        if ($action === 'save_catalog_snapshot') {
            $preview = self::build_product_exposure_preview();
            update_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION, $preview, false);
            if (($preview['state'] ?? '') !== 'passed') {
                return [
                    'type' => 'error',
                    'message' => 'Catalog snapshot was not saved: ' . ($preview['message'] ?? 'review product exposure settings.'),
                ];
            }
            $snapshot = self::product_exposure_snapshot_from_preview($preview);
            update_option(self::PRODUCT_EXPOSURE_SNAPSHOT_OPTION, $snapshot, false);
            $preview['catalog_diff'] = self::catalog_snapshot_diff($snapshot, $snapshot);
            update_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION, $preview, false);
            return sprintf(
                'Catalog snapshot saved: %d products are now the comparison baseline for future AgentCart catalog previews.',
                intval($snapshot['included_count'] ?? 0)
            );
        }
        if ($action === 'enable_all_published_simple') {
            $count = self::set_agentcart_exposure_for_published_simple_products('yes');
            delete_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION);
            return sprintf('%d published simple products are now AgentCart-enabled.', $count);
        }
        if ($action === 'disable_all') {
            $count = self::set_agentcart_exposure_for_published_simple_products('no');
            delete_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION);
            return sprintf('%d published simple products are no longer exposed through AgentCart.', $count);
        }
        return null;
    }

    private static function maybe_handle_credential_action() {
        if (strtoupper((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'] ?? ''))) !== 'POST') {
            return null;
        }
        if (empty($_POST['agentcart_credential_action'])) {
            return null;
        }
        check_admin_referer('agentcart_shopbridge_credential_action');
        $action = sanitize_key((string) wp_unslash($_POST['agentcart_credential_action']));

        if ($action === 'rotate_merchant_token') {
            if (defined('AGENTCART_SHOPBRIDGE_TOKEN')) {
                return 'Merchant token is managed in wp-config.php and was not changed.';
            }
            update_option(self::TOKEN_OPTION, wp_generate_password(48, false, false), false);
            return 'Merchant token rotated. Update any trusted AgentCart gateway before using private-token checkout.';
        }

        if ($action === 'rotate_payment_verifier_token') {
            if (defined('AGENTCART_PAYMENT_VERIFIER_TOKEN')) {
                return 'Payment verifier token is managed in wp-config.php and was not changed.';
            }
            update_option(self::PAYMENT_VERIFIER_TOKEN_OPTION, wp_generate_password(48, false, false), false);
            return 'Payment verifier token generated. Configure the same bearer token on the external verifier.';
        }

        if ($action === 'rotate_signed_request_secret' || $action === 'rotate_signed_request_key') {
            if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
                return 'Signed request signing key is managed in wp-config.php and was not changed.';
            }
            $key = self::rotate_signed_request_key();
            return 'Signed request signing key rotated. Configure signer ' . ($key['id'] ?? 'active key') . ' and the new secret in trusted buyer agents or the AgentCart gateway.';
        }

        if ($action === 'add_signed_request_key') {
            if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
                return 'Signed request signing key is managed in wp-config.php and was not changed.';
            }
            $key = self::add_signed_request_key();
            return 'Additional signed request signing key added. Configure signer ' . ($key['id'] ?? 'active key') . ' and the new secret in the intended buyer agent.';
        }

        if ($action === 'revoke_retiring_signed_request_keys') {
            if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
                return 'Signed request signing key is managed in wp-config.php and was not changed.';
            }
            $removed = self::revoke_retiring_signed_request_keys();
            return sprintf('%d retiring signed request key(s) revoked. Active keys remain usable.', $removed);
        }

        return null;
    }

    private static function maybe_handle_registry_action() {
        if (strtoupper((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'] ?? ''))) !== 'POST') {
            return null;
        }
        if (empty($_POST['agentcart_registry_action'])) {
            return null;
        }
        check_admin_referer('agentcart_shopbridge_registry_action');
        $action = sanitize_key((string) wp_unslash($_POST['agentcart_registry_action']));

        if ($action === 'refresh_registry_metadata') {
            if (defined('AGENTCART_REGISTRY_UPDATED_AT')) {
                return 'Registry updated_at is managed in wp-config.php and was not changed.';
            }
            update_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION, self::registry_claim_fingerprint(), false);
            update_option(self::REGISTRY_UPDATED_AT_OPTION, self::current_registry_timestamp(), false);
            delete_option(self::REGISTRY_PUBLIC_CHECK_OPTION);
            return 'Registry claim metadata refreshed. Re-run the public endpoint check before submitting the bundle to a registry.';
        }

        if ($action === 'check_public_registry_endpoints') {
            $result = self::run_registry_public_check();
            update_option(self::REGISTRY_PUBLIC_CHECK_OPTION, $result, false);
            return $result['state'] === 'verified'
                ? 'Registry public endpoint check passed.'
                : 'Registry public endpoint check found issues. Review the Registry Transparency section.';
        }

        if ($action === 'check_registry_health') {
            $result = self::run_registry_health_check();
            update_option(self::REGISTRY_HEALTH_CHECK_OPTION, $result, false);
            if (($result['state'] ?? '') === 'verified') {
                return 'Registry health check passed: the current record is verified and eligible.';
            }
            return [
                'type' => ($result['state'] ?? '') === 'failed' ? 'error' : 'warning',
                'message' => 'Registry health check needs attention: ' . ($result['message'] ?? 'review the Registry Transparency section.'),
            ];
        }

        if ($action === 'submit_registry_bundle') {
            $result = self::submit_registry_connection('upsert');
            update_option(self::REGISTRY_CONNECTION_STATUS_OPTION, $result, false);
            if (($result['state'] ?? '') === 'submitted') {
                return 'Registry bundle submitted to the configured registry connection.';
            }
            return [
                'type' => 'error',
                'message' => 'Registry bundle submission failed: ' . ($result['message'] ?? 'review the Registry Transparency section.'),
            ];
        }

        if ($action === 'revoke_registry_record') {
            if (self::registry_connection_url() === '') {
                return [
                    'type' => 'error',
                    'message' => 'Configure a Registry connection URL before sending a revocation request.',
                ];
            }
            self::record_registry_revocation(self::registry_record_hash_value(), 'merchant_admin_revoke');
            $result = self::submit_registry_connection('revoke');
            update_option(self::REGISTRY_CONNECTION_STATUS_OPTION, $result, false);
            if (($result['state'] ?? '') === 'submitted') {
                return 'Registry revocation request submitted. The merchant-hosted revocation document now marks the current record as revoked.';
            }
            return [
                'type' => 'error',
                'message' => 'Registry revocation request failed: ' . ($result['message'] ?? 'review the Registry Transparency section.'),
            ];
        }

        return null;
    }

    private static function maybe_handle_support_diagnostics_download() {
        if (strtoupper((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'] ?? ''))) !== 'POST') {
            return;
        }
        if (empty($_POST['agentcart_support_action'])) {
            return;
        }
        check_admin_referer('agentcart_shopbridge_support_action');
        $action = sanitize_key((string) wp_unslash($_POST['agentcart_support_action']));
        if ($action !== 'download_support_diagnostics') {
            return;
        }
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('You do not have permission to download AgentCart diagnostics.', 'agentcart-shopbridge'));
        }

        $filename = 'agentcart-shopbridge-diagnostics-' . gmdate('Ymd-His') . '.json';
        nocache_headers();
        header('Content-Type: application/json; charset=utf-8');
        header('Content-Disposition: attachment; filename="' . $filename . '"');
        echo wp_json_encode(self::support_diagnostics_bundle(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- wp_json_encode serializes a redacted diagnostics download.
        exit;
    }

    private static function render_support_diagnostics_panel() {
        ?>
        <h3 id="agentcart-support-diagnostics">Support Diagnostics</h3>
        <p style="max-width: 760px;">
            Download a redacted JSON packet for AgentCart setup, registry, signed-request,
            quote, checkout, verifier, and WooCommerce configuration support. Raw secrets,
            request bodies, payment bodies, nonces, and signatures are excluded.
        </p>
        <form method="post" style="display: inline-block; margin-bottom: 12px;">
            <?php wp_nonce_field('agentcart_shopbridge_support_action'); ?>
            <input type="hidden" name="agentcart_support_action" value="download_support_diagnostics" />
            <?php submit_button('Download diagnostics JSON', 'secondary', 'submit', false); ?>
        </form>
        <?php
    }

    private static function render_registry_transparency_panel($registry_public_check, $registry_connection_status = null) {
        $registry_public_check = is_array($registry_public_check) ? $registry_public_check : [];
        $registry_connection_status = is_array($registry_connection_status) ? $registry_connection_status : self::registry_connection_status();
        $last_state = (string) ($registry_public_check['state'] ?? 'not_checked');
        $last_checked = (string) ($registry_public_check['checked_at'] ?? '');
        $errors = is_array($registry_public_check['errors'] ?? null) ? $registry_public_check['errors'] : [];
        $endpoints = is_array($registry_public_check['endpoints'] ?? null) ? $registry_public_check['endpoints'] : [];
        $registry_health_check = self::registry_health_check_result();
        $registry_connection_url = self::registry_connection_url();
        $registry_health_url = self::registry_connection_endpoint_url('health');
        $registry_monitor_url = self::registry_connection_endpoint_url('monitor');
        $connection_state = (string) ($registry_connection_status['state'] ?? 'not_submitted');
        $connection_operation = (string) ($registry_connection_status['operation'] ?? '');
        $connection_checked_at = (string) ($registry_connection_status['checked_at'] ?? '');
        $connection_message = (string) ($registry_connection_status['message'] ?? '');
        $health_state = (string) ($registry_health_check['state'] ?? 'not_checked');
        $health_checked_at = (string) ($registry_health_check['checked_at'] ?? '');
        $health_message = (string) ($registry_health_check['message'] ?? '');
        $health_errors = is_array($registry_health_check['errors'] ?? null) ? $registry_health_check['errors'] : [];
        $health = is_array($registry_health_check['health'] ?? null) ? $registry_health_check['health'] : [];
        $current_record = is_array($health['current_record'] ?? null) ? $health['current_record'] : [];
        $monitor = is_array($registry_health_check['monitor'] ?? null) ? $registry_health_check['monitor'] : [];
        $alert_delivery_sinks = [];
        if (!empty($monitor['alert_delivery_webhook_configured'])) {
            $alert_delivery_sinks[] = 'webhook';
        }
        if (!empty($monitor['alert_delivery_homeassistant_configured'])) {
            $alert_delivery_sinks[] = 'Home Assistant';
        }
        if (!empty($monitor['alert_delivery_email_configured'])) {
            $alert_delivery_sinks[] = 'email';
        }
        $admin_health_rows = self::registry_admin_health_summary($registry_public_check, $registry_connection_status, $registry_health_check);
        $endpoint_rows = '';
        foreach (['manifest', 'proof', 'revocations', 'bundle'] as $key) {
            $endpoint = is_array($endpoints[$key] ?? null) ? $endpoints[$key] : [];
            $endpoint_rows .= '<tr><th scope="row">' . esc_html(ucfirst($key)) . '</th><td><code>' . esc_html((string) ($endpoint['url'] ?? self::registry_transparency_url_for_key($key))) . '</code></td><td>' . self::admin_status_badge(!empty($endpoint['ok']), 'OK', 'Needs check') . '</td></tr>';
        }
        ?>
        <h3>Registry Transparency</h3>
        <p style="max-width: 760px;">
            Refresh the merchant-owned registry claim when stable identity, endpoint, payment,
            shipping, or policy settings change. Run the public endpoint check before asking a
            registry to ingest this shop.
        </p>
        <h4>Registry Health Summary</h4>
        <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
            <thead>
                <tr>
                    <th scope="col">Check</th>
                    <th scope="col">Status</th>
                    <th scope="col">Detail</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($admin_health_rows as $row) : ?>
                    <tr>
                        <th scope="row"><?php echo esc_html((string) ($row['label'] ?? 'Registry check')); ?></th>
                        <td><?php self::render_admin_status_badge(!empty($row['ok']), (string) ($row['ok_label'] ?? 'OK'), (string) ($row['missing_label'] ?? 'Needs attention')); ?></td>
                        <td><?php echo esc_html((string) ($row['detail'] ?? '')); ?></td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        <table class="widefat striped" style="max-width: 980px;">
            <tbody>
                <tr>
                    <th scope="row">Last public check</th>
                    <td>
                        <?php self::render_admin_status_badge($last_state === 'verified', $last_state === 'verified' ? 'Verified' : 'Needs check', $last_state === 'failed' ? 'Failed' : 'Not checked'); ?>
                        <?php if ($last_checked !== '') : ?>
                            <br><span class="description"><?php echo esc_html($last_checked); ?></span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <?php if (!empty($errors)) : ?>
                            <code><?php echo esc_html(implode(', ', array_map('strval', $errors))); ?></code>
                        <?php else : ?>
                            <span class="description">No stored public endpoint errors.</span>
                        <?php endif; ?>
                    </td>
                </tr>
                <?php echo $endpoint_rows; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                <tr>
                    <th scope="row">Registry connection</th>
                    <td>
                        <code><?php echo esc_html($registry_connection_url ?: 'not configured'); ?></code>
                        <p class="description">
                            Optional hosted registry endpoint for submitting the generated bundle or a revocation request.
                        </p>
                    </td>
                    <td><?php self::render_admin_status_badge($registry_connection_url !== '', 'Configured', 'Not configured'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Last registry submission</th>
                    <td>
                        <?php echo esc_html($connection_operation !== '' ? $connection_operation : 'none'); ?>
                        <?php if ($connection_checked_at !== '') : ?>
                            <br><span class="description"><?php echo esc_html($connection_checked_at); ?></span>
                        <?php endif; ?>
                        <?php if ($connection_message !== '') : ?>
                            <br><span class="description"><?php echo esc_html($connection_message); ?></span>
                        <?php endif; ?>
                    </td>
                    <td><?php self::render_admin_status_badge($connection_state === 'submitted', 'Submitted', $connection_state === 'failed' ? 'Failed' : 'Not submitted'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Registry health endpoint</th>
                    <td>
                        <code><?php echo esc_html($registry_health_url ?: 'not configured'); ?></code>
                        <?php if ($registry_monitor_url !== '') : ?>
                            <br><span class="description">Monitor: <code><?php echo esc_html($registry_monitor_url); ?></code></span>
                        <?php endif; ?>
                    </td>
                    <td><?php self::render_admin_status_badge($registry_health_url !== '', 'Available', 'Needs registry connection'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Last registry health</th>
                    <td>
                        <?php self::render_admin_status_badge($health_state === 'verified', 'Verified', $health_state === 'failed' ? 'Failed' : ($health_state === 'attention' ? 'Needs attention' : 'Not checked')); ?>
                        <?php if ($health_checked_at !== '') : ?>
                            <br><span class="description"><?php echo esc_html($health_checked_at); ?></span>
                        <?php endif; ?>
                        <?php if ($health_message !== '') : ?>
                            <br><span class="description"><?php echo esc_html($health_message); ?></span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <?php if (!empty($health_errors)) : ?>
                            <code><?php echo esc_html(implode(', ', array_map('strval', $health_errors))); ?></code>
                        <?php else : ?>
                            <span class="description">No stored registry health errors.</span>
                        <?php endif; ?>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Registry entry health</th>
                    <td>
                        <?php if (!empty($current_record)) : ?>
                            State: <code><?php echo esc_html((string) ($current_record['state'] ?? 'unknown')); ?></code>
                            &middot; eligible: <code><?php echo !empty($current_record['eligible']) ? esc_html('yes') : esc_html('no'); ?></code>
                            <?php if (isset($current_record['age_days'])) : ?>
                                <br><span class="description">Manifest freshness: <?php echo esc_html((string) intval($current_record['age_days'])); ?> days old; updated_at <?php echo esc_html((string) ($current_record['updated_at'] ?? 'unknown')); ?></span>
                            <?php endif; ?>
                            <?php if (!empty($current_record['checked_at'])) : ?>
                                <br><span class="description">Registry checked_at <?php echo esc_html((string) $current_record['checked_at']); ?></span>
                            <?php endif; ?>
                        <?php else : ?>
                            <span class="description">Run registry health after submitting the bundle.</span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <?php self::render_admin_status_badge(!empty($current_record['eligible']) && ($current_record['state'] ?? '') === 'verified', 'Eligible', 'Not eligible'); ?>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Registry monitor snapshot</th>
                    <td>
                        <?php if (($monitor['state'] ?? '') === 'fetched') : ?>
                            last run <?php echo esc_html((string) ($monitor['last_run_at'] ?? 'never')); ?>
                            &middot; snapshots <?php echo esc_html((string) intval($monitor['snapshot_count'] ?? 0)); ?>
                            <br><span class="description">Last snapshot state: <?php echo esc_html((string) ($monitor['last_snapshot_state'] ?? 'unknown')); ?>; alerts <?php echo esc_html((string) intval($monitor['last_snapshot_alert_count'] ?? 0)); ?>; new/resolved <?php echo esc_html((string) intval($monitor['last_changes_new_alert_count'] ?? 0)); ?>/<?php echo esc_html((string) intval($monitor['last_changes_resolved_alert_count'] ?? 0)); ?></span>
                        <?php elseif (!empty($monitor['error'])) : ?>
                            <span class="description"><?php echo esc_html((string) $monitor['error']); ?></span>
                        <?php else : ?>
                            <span class="description">No registry monitor status fetched yet.</span>
                        <?php endif; ?>
                    </td>
                    <td><?php self::render_admin_status_badge(($monitor['state'] ?? '') === 'fetched', 'Fetched', ($monitor['state'] ?? '') === 'unauthorized' ? 'Needs token' : 'Not available'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Registry alert delivery</th>
                    <td>
                        <?php if (($monitor['state'] ?? '') === 'fetched') : ?>
                            state <code><?php echo esc_html((string) (($monitor['last_notifications_state'] ?? '') ?: 'not-run')); ?></code>
                            &middot; sinks <?php echo esc_html((string) intval($monitor['alert_delivery_sink_count'] ?? 0)); ?>
                            <?php if (!empty($alert_delivery_sinks)) : ?>
                                <br><span class="description">Configured sinks: <?php echo esc_html(implode(', ', $alert_delivery_sinks)); ?>; minimum severity <?php echo esc_html((string) ($monitor['alert_delivery_min_severity'] ?? 'warning')); ?></span>
                            <?php endif; ?>
                            <?php if (!empty($monitor['last_notifications_reason'])) : ?>
                                <br><span class="description"><?php echo esc_html((string) $monitor['last_notifications_reason']); ?></span>
                            <?php endif; ?>
                            <?php if (intval($monitor['last_notifications_failed_result_count'] ?? 0) > 0) : ?>
                                <br><span class="description"><?php echo esc_html((string) intval($monitor['last_notifications_failed_result_count'])); ?> of <?php echo esc_html((string) intval($monitor['last_notifications_result_count'])); ?> delivery sinks failed.</span>
                            <?php endif; ?>
                        <?php else : ?>
                            <span class="description">Run registry health after configuring the registry monitor token.</span>
                        <?php endif; ?>
                    </td>
                    <td><?php self::render_admin_status_badge(in_array(($monitor['last_notifications_state'] ?? ''), ['sent', 'skipped'], true), 'OK', 'Needs attention'); ?></td>
                </tr>
            </tbody>
        </table>
        <div style="margin-top: 12px;">
            <form method="post" style="display: inline-block; margin-right: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_registry_action'); ?>
                <input type="hidden" name="agentcart_registry_action" value="refresh_registry_metadata" />
                <?php submit_button('Refresh registry metadata', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block;">
                <?php wp_nonce_field('agentcart_shopbridge_registry_action'); ?>
                <input type="hidden" name="agentcart_registry_action" value="check_public_registry_endpoints" />
                <?php submit_button('Check public registry endpoints', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block; margin-left: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_registry_action'); ?>
                <input type="hidden" name="agentcart_registry_action" value="check_registry_health" />
                <?php submit_button('Check registry health', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block; margin-left: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_registry_action'); ?>
                <input type="hidden" name="agentcart_registry_action" value="submit_registry_bundle" />
                <?php submit_button('Submit registry bundle', 'secondary', 'submit', false); ?>
            </form>
            <form method="post" style="display: inline-block; margin-left: 8px;">
                <?php wp_nonce_field('agentcart_shopbridge_registry_action'); ?>
                <input type="hidden" name="agentcart_registry_action" value="revoke_registry_record" />
                <?php submit_button('Send revocation request', 'secondary', 'submit', false); ?>
            </form>
            <p class="description" style="max-width: 760px;">
                Revocation marks the current registry record hash in the merchant-hosted revocation document and sends that intent to the configured registry. Use it when removing this shop record from discovery.
            </p>
        </div>
        <?php
    }

    private static function registry_admin_health_summary($registry_public_check, $registry_connection_status, $registry_health_check) {
        $registry_public_check = is_array($registry_public_check) ? $registry_public_check : [];
        $registry_connection_status = is_array($registry_connection_status) ? $registry_connection_status : [];
        $registry_health_check = is_array($registry_health_check) ? $registry_health_check : [];
        $health = is_array($registry_health_check['health'] ?? null) ? $registry_health_check['health'] : [];
        $current_record = is_array($health['current_record'] ?? null) ? $health['current_record'] : [];
        $monitor = is_array($registry_health_check['monitor'] ?? null) ? $registry_health_check['monitor'] : [];
        $registry_connection_url = self::registry_connection_url();
        $registry_updated_at = self::registry_updated_at();
        $age_days = isset($current_record['age_days']) && is_numeric($current_record['age_days']) ? intval($current_record['age_days']) : null;
        $manifest_fresh = $age_days !== null ? $age_days <= 180 : $registry_updated_at !== '';
        $manifest_detail = $age_days !== null
            ? 'Registry record updated_at ' . (string) ($current_record['updated_at'] ?? 'unknown') . '; age ' . $age_days . ' day(s).'
            : 'Local registry updated_at ' . ($registry_updated_at !== '' ? $registry_updated_at : 'not set') . '; run registry health to fetch remote age.';
        $connection_state = (string) ($registry_connection_status['state'] ?? 'not_submitted');
        $public_state = (string) ($registry_public_check['state'] ?? 'not_checked');
        $monitor_state = (string) ($monitor['state'] ?? 'not_available');
        $notification_state = (string) ($monitor['last_notifications_state'] ?? '');
        return [
            [
                'id' => 'hosted_registry_connection',
                'label' => 'Hosted registry connection',
                'ok' => $registry_connection_url !== '',
                'ok_label' => 'Configured',
                'missing_label' => 'Not configured',
                'detail' => $registry_connection_url !== ''
                    ? 'Connection URL is configured; last submission state ' . $connection_state . '.'
                    : 'Add a registry connection URL to submit, revoke, and fetch health from WordPress.',
            ],
            [
                'id' => 'domain_proof',
                'label' => 'Domain proof',
                'ok' => self::registry_domain_proof_configured() && $public_state === 'verified',
                'ok_label' => 'Verified',
                'missing_label' => self::registry_domain_proof_configured() ? 'Needs check' : 'Needs merchant id',
                'detail' => self::registry_domain_proof_configured()
                    ? 'Proof URL is generated; public endpoint check state ' . $public_state . '.'
                    : 'Set a stable merchant id so the proof document can bind this domain.',
            ],
            [
                'id' => 'manifest_freshness',
                'label' => 'Manifest freshness',
                'ok' => $manifest_fresh,
                'ok_label' => 'Fresh',
                'missing_label' => 'Stale or unknown',
                'detail' => $manifest_detail,
            ],
            [
                'id' => 'registry_entry',
                'label' => 'Current registry entry',
                'ok' => !empty($current_record['eligible']) && ($current_record['state'] ?? '') === 'verified',
                'ok_label' => 'Eligible',
                'missing_label' => empty($current_record) ? 'Not checked' : 'Not eligible',
                'detail' => empty($current_record)
                    ? 'Run registry health after submitting the bundle.'
                    : 'Record state ' . (string) ($current_record['state'] ?? 'unknown') . '; error count ' . (string) intval($current_record['error_count'] ?? 0) . '.',
            ],
            [
                'id' => 'monitor_snapshot',
                'label' => 'Monitor snapshot',
                'ok' => $monitor_state === 'fetched',
                'ok_label' => 'Fetched',
                'missing_label' => $monitor_state === 'unauthorized' ? 'Needs token' : 'Not fetched',
                'detail' => $monitor_state === 'fetched'
                    ? 'Last run ' . (string) ($monitor['last_run_at'] ?? 'unknown') . '; snapshots ' . (string) intval($monitor['snapshot_count'] ?? 0) . '; alerts ' . (string) intval($monitor['last_snapshot_alert_count'] ?? 0) . '.'
                    : 'Fetch monitor status from the configured registry to see scheduled checks and alert deltas.',
            ],
            [
                'id' => 'alert_delivery',
                'label' => 'Alert delivery',
                'ok' => in_array($notification_state, ['sent', 'skipped'], true),
                'ok_label' => 'OK',
                'missing_label' => 'Needs attention',
                'detail' => $notification_state !== ''
                    ? 'Last notification state ' . $notification_state . '; failed sinks ' . (string) intval($monitor['last_notifications_failed_result_count'] ?? 0) . '.'
                    : 'Run registry monitor health to confirm webhook, Home Assistant, or email delivery state.',
            ],
        ];
    }

    private static function registry_transparency_url_for_key($key) {
        if ($key === 'manifest') {
            return home_url('/.well-known/agentcart.json');
        }
        if ($key === 'proof') {
            return self::registry_proof_url();
        }
        if ($key === 'revocations') {
            return self::registry_revocation_url();
        }
        if ($key === 'bundle') {
            return self::registry_bundle_url();
        }
        return '';
    }

    private static function render_credential_action_forms() {
        ?>
        <table class="widefat striped" style="max-width: 980px;">
            <tbody>
                <tr>
                    <th scope="row">Trusted gateway merchant token</th>
                    <td>
                        Private shared secret for demo or gateway-backed checkout. Rotating it
                        does not change existing WooCommerce orders, but trusted gateways must be
                        updated before they can create new token-authorized orders.
                    </td>
                    <td>
                        <?php if (defined('AGENTCART_SHOPBRIDGE_TOKEN')) : ?>
                            <?php self::render_admin_status_badge(true, 'Managed in wp-config.php'); ?>
                        <?php else : ?>
                            <form method="post">
                                <?php wp_nonce_field('agentcart_shopbridge_credential_action'); ?>
                                <input type="hidden" name="agentcart_credential_action" value="rotate_merchant_token" />
                                <?php submit_button('Rotate merchant token', 'secondary', 'submit', false); ?>
                            </form>
                        <?php endif; ?>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Payment verifier bearer token</th>
                    <td>
                        Shared secret sent from ShopBridge to the external verifier. Use this
                        when the verifier validates quote-bound Tempo, Stripe/card MPP, or future
                        payment/refund credentials before WooCommerce records a paid order or refund.
                    </td>
                    <td>
                        <?php if (defined('AGENTCART_PAYMENT_VERIFIER_TOKEN')) : ?>
                            <?php self::render_admin_status_badge(true, 'Managed in wp-config.php'); ?>
                        <?php else : ?>
                            <form method="post">
                                <?php wp_nonce_field('agentcart_shopbridge_credential_action'); ?>
                                <input type="hidden" name="agentcart_credential_action" value="rotate_payment_verifier_token" />
                                <?php submit_button('Generate / rotate verifier token', 'secondary', 'submit', false); ?>
                            </form>
                        <?php endif; ?>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Signed request signing keys</th>
                    <td>
                        HMAC secrets or RSA public keys used to verify method, path, body digest,
                        nonce, and expiry for request-bound quote, checkout, status, refund, and
                        cancellation calls.
                        <br>
                        <?php echo esc_html(self::signed_request_key_status_summary()); ?>
                    </td>
                    <td>
                        <?php if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) : ?>
                            <?php self::render_admin_status_badge(true, 'Managed in wp-config.php'); ?>
                        <?php else : ?>
                            <form method="post" style="display: inline-block; margin-right: 8px;">
                                <?php wp_nonce_field('agentcart_shopbridge_credential_action'); ?>
                                <input type="hidden" name="agentcart_credential_action" value="add_signed_request_key" />
                                <?php submit_button('Add active key', 'secondary', 'submit', false); ?>
                            </form>
                            <form method="post" style="display: inline-block; margin-right: 8px;">
                                <?php wp_nonce_field('agentcart_shopbridge_credential_action'); ?>
                                <input type="hidden" name="agentcart_credential_action" value="rotate_signed_request_key" />
                                <?php submit_button('Rotate signing key', 'secondary', 'submit', false); ?>
                            </form>
                            <?php if (self::signed_request_retiring_key_count() > 0) : ?>
                                <form method="post" style="display: inline-block;">
                                    <?php wp_nonce_field('agentcart_shopbridge_credential_action'); ?>
                                    <input type="hidden" name="agentcart_credential_action" value="revoke_retiring_signed_request_keys" />
                                    <?php submit_button('Revoke retiring keys', 'secondary', 'submit', false); ?>
                                </form>
                            <?php endif; ?>
                        <?php endif; ?>
                    </td>
                </tr>
            </tbody>
        </table>
        <?php
    }

    private static function render_signed_request_audit_panel() {
        $events = array_reverse(self::signed_request_audit_events());
        $visible_events = array_slice($events, 0, 10);
        $summary = self::signed_request_audit_summary();
        ?>
        <h2 id="agentcart-signed-request-audit">Signed Request Audit</h2>
        <p class="description" style="max-width: 760px;">
            Recent signed request verification outcomes. Raw request bodies,
            signatures, and nonces are not stored; this panel keeps hashes and
            normalized error codes for support and dispute review.
        </p>
        <table class="widefat striped" style="max-width: 980px;">
            <tbody>
                <tr>
                    <th scope="row">Stored events</th>
                    <td><?php echo esc_html((string) intval($summary['event_count'] ?? 0)); ?> / <?php echo esc_html((string) self::SIGNED_REQUEST_AUDIT_LIMIT); ?></td>
                    <td><?php self::render_admin_status_badge(!empty($summary['event_count']), 'Audit active', 'No signed requests recorded'); ?></td>
                </tr>
            </tbody>
        </table>
        <?php if (empty($visible_events)) : ?>
            <p class="description" style="max-width: 760px;">No signed request events have been recorded yet.</p>
            <?php return; ?>
        <?php endif; ?>
        <table class="widefat striped" style="max-width: 980px;">
            <thead>
                <tr>
                    <th scope="col">Time</th>
                    <th scope="col">State</th>
                    <th scope="col">Bucket</th>
                    <th scope="col">Signer</th>
                    <th scope="col">Error</th>
                    <th scope="col">Nonce hash</th>
                    <th scope="col">Digest hash</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($visible_events as $event) : ?>
                    <tr>
                        <td><?php echo esc_html((string) ($event['checked_at'] ?? '')); ?></td>
                        <td><?php echo esc_html((string) ($event['state'] ?? '')); ?></td>
                        <td><?php echo esc_html((string) ($event['bucket'] ?? '')); ?></td>
                        <td>
                            <?php echo esc_html((string) ($event['signer'] ?? '')); ?>
                            <?php if (!empty($event['key_id'])) : ?>
                                <br><span class="description"><?php echo esc_html((string) $event['key_id']); ?></span>
                            <?php endif; ?>
                        </td>
                        <td><?php echo esc_html((string) ($event['error_code'] ?? '')); ?></td>
                        <td><code><?php echo esc_html(substr((string) ($event['nonce_hash'] ?? ''), 0, 16)); ?></code></td>
                        <td><code><?php echo esc_html(substr((string) ($event['supplied_digest_hash'] ?? ''), 0, 16)); ?></code></td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        <?php
    }

    public static function render_product_agentcart_options() {
        if (!function_exists('woocommerce_wp_checkbox')) {
            return;
        }
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_ENABLED_META,
            'label' => __('Expose through AgentCart', 'agentcart-shopbridge'),
            'description' => __('Used in manual exposure mode. Tag and all-product modes are controlled from WooCommerce -> AgentCart.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_BLOCKED_META,
            'label' => __('Exclude from AgentCart checkout', 'agentcart-shopbridge'),
            'description' => __('Overrides every exposure mode. Use for age-gated, regulated, local-pickup-only, deposit, or manual-review products.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META,
            'label' => __('Allow restricted AgentCart checkout', 'agentcart-shopbridge'),
            'description' => __('By default, products matching restricted-goods labels are blocked from AgentCart catalog and checkout. Enable only after confirming the shop has the required legal, age-gate, and human-review flow.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_PERISHABLE_META,
            'label' => __('AgentCart perishable item', 'agentcart-shopbridge'),
            'description' => __('Marks this product as perishable or temperature-sensitive for agent refund, return, cancellation, and delivery review.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_DEPOSIT_META,
            'label' => __('AgentCart deposit possible', 'agentcart-shopbridge'),
            'description' => __('Marks this product as potentially deposit-bearing, for example Pfand or reusable packaging.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_FINAL_SALE_META,
            'label' => __('AgentCart final sale / non-returnable', 'agentcart-shopbridge'),
            'description' => __('Marks this product as final sale or normally non-returnable so buyer agents do not imply standard returns.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_SUBSTITUTION_SENSITIVE_META,
            'label' => __('AgentCart substitution-sensitive', 'agentcart-shopbridge'),
            'description' => __('Marks this product as needing explicit buyer approval before any substitution.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
        if (function_exists('woocommerce_wp_text_input')) {
            woocommerce_wp_text_input([
                'id' => self::PRODUCT_MAX_QUANTITY_META,
                'label' => __('AgentCart max quantity', 'agentcart-shopbridge'),
                'description' => __('Maximum quantity a buyer agent may quote for this product. Defaults to 20, or 1 for sold-individually products.', 'agentcart-shopbridge'),
                'desc_tip' => true,
                'type' => 'number',
                'custom_attributes' => [
                    'min' => '1',
                    'max' => '999',
                    'step' => '1',
                ],
            ]);
            woocommerce_wp_text_input([
                'id' => self::PRODUCT_SHIPPING_COUNTRIES_META,
                'label' => __('AgentCart shipping countries', 'agentcart-shopbridge'),
                'description' => __('Optional comma-separated ISO country codes for this product. Leave empty to inherit store shipping countries.', 'agentcart-shopbridge'),
                'desc_tip' => true,
                'type' => 'text',
            ]);
        }
    }

    public static function save_product_agentcart_options($product) {
        if (!$product instanceof WC_Product) {
            return;
        }
        // phpcs:disable WordPress.Security.NonceVerification.Missing -- WooCommerce verifies the product edit nonce before woocommerce_admin_process_product_object runs.
        $product->update_meta_data(self::PRODUCT_ENABLED_META, isset($_POST[self::PRODUCT_ENABLED_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_BLOCKED_META, isset($_POST[self::PRODUCT_BLOCKED_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META, isset($_POST[self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_PERISHABLE_META, isset($_POST[self::PRODUCT_PERISHABLE_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_DEPOSIT_META, isset($_POST[self::PRODUCT_DEPOSIT_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_FINAL_SALE_META, isset($_POST[self::PRODUCT_FINAL_SALE_META]) ? 'yes' : 'no');
        $product->update_meta_data(self::PRODUCT_SUBSTITUTION_SENSITIVE_META, isset($_POST[self::PRODUCT_SUBSTITUTION_SENSITIVE_META]) ? 'yes' : 'no');
        $max_quantity = isset($_POST[self::PRODUCT_MAX_QUANTITY_META]) ? absint(wp_unslash($_POST[self::PRODUCT_MAX_QUANTITY_META])) : 20;
        $product->update_meta_data(self::PRODUCT_MAX_QUANTITY_META, (string) max(1, min(999, $max_quantity ?: 20)));
        // phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotSanitized -- sanitize_country_list_setting() sanitizes the unslashed country-code list.
        $raw_shipping_countries = isset($_POST[self::PRODUCT_SHIPPING_COUNTRIES_META]) ? wp_unslash($_POST[self::PRODUCT_SHIPPING_COUNTRIES_META]) : '';
        $shipping_countries = self::sanitize_country_list_setting($raw_shipping_countries);
        $product->update_meta_data(self::PRODUCT_SHIPPING_COUNTRIES_META, $shipping_countries);
        // phpcs:enable WordPress.Security.NonceVerification.Missing
    }

    public static function maybe_serve_well_known_manifest() {
        $path = wp_parse_url((string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_URI'] ?? '')), PHP_URL_PATH);
        if (!in_array($path, ['/.well-known/agentcart.json', '/.well-known/agentcart-registry-proof.json', '/.well-known/agentcart-registry-revocations.json', '/.well-known/agentcart-registry-bundle.json'], true)) {
            return;
        }
        $rate_limit = self::enforce_well_known_rate_limit($path);
        if (is_wp_error($rate_limit)) {
            $data = $rate_limit->get_error_data();
            $status = is_array($data) ? intval($data['status'] ?? 429) : 429;
            $retry_after = is_array($data) ? intval($data['retry_after_seconds'] ?? self::RATE_LIMIT_WINDOW_SECONDS) : self::RATE_LIMIT_WINDOW_SECONDS;
            status_header($status);
            header('Retry-After: ' . max(1, $retry_after));
            wp_send_json([
                'code' => $rate_limit->get_error_code(),
                'message' => $rate_limit->get_error_message(),
                'data' => $data,
            ], $status);
        }
        if (!class_exists('WooCommerce')) {
            wp_send_json(['error' => 'WooCommerce is required.'], 503);
        }
        if ($path === '/.well-known/agentcart-registry-proof.json') {
            wp_send_json(self::registry_domain_proof());
        }
        if ($path === '/.well-known/agentcart-registry-revocations.json') {
            wp_send_json(self::registry_revocations());
        }
        if ($path === '/.well-known/agentcart-registry-bundle.json') {
            wp_send_json(self::registry_onboarding_bundle());
        }
        wp_send_json(self::capability_document());
    }

    public static function authorize_public_read(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        $rate_limit = self::enforce_rate_limit($request);
        if (is_wp_error($rate_limit)) {
            return $rate_limit;
        }
        $signed_request = self::enforce_signed_request_policy($request, self::rate_limit_bucket_for_request($request));
        if (is_wp_error($signed_request)) {
            return $signed_request;
        }
        return true;
    }

    public static function authorize_support_diagnostics(WP_REST_Request $request) {
        unset($request);
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        if (!current_user_can('manage_woocommerce')) {
            return new WP_Error('agentcart_forbidden', 'Support diagnostics require WooCommerce manager access.', ['status' => 403]);
        }
        return true;
    }

    public static function authorize(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        if (!self::has_valid_merchant_token($request)) {
            return new WP_Error('agentcart_unauthorized', 'Missing or invalid AgentCart merchant token.', ['status' => 401]);
        }
        return true;
    }

    public static function authorize_checkout(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        $rate_limit = self::enforce_rate_limit($request, 'checkout');
        if (is_wp_error($rate_limit)) {
            return $rate_limit;
        }
        $signed_request = self::enforce_signed_request_policy($request, 'checkout');
        if (is_wp_error($signed_request)) {
            return $signed_request;
        }
        if (self::external_verifier_required_for_checkout()) {
            if (self::payment_verifier_url() !== '') {
                return true;
            }
            return new WP_Error(
                'agentcart_payment_verifier_required',
                'External-verifier-only checkout requires a payment verifier URL.',
                ['status' => 401]
            );
        }
        if (self::has_valid_merchant_token($request)) {
            return true;
        }
        if (self::payment_verifier_url() !== '') {
            return true;
        }
        return new WP_Error(
            'agentcart_unauthorized',
            'Order creation requires the merchant token unless an external payment verifier is configured.',
            ['status' => 401]
        );
    }

    public static function authorize_order_status(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        $rate_limit = self::enforce_rate_limit($request, 'order_status');
        if (is_wp_error($rate_limit)) {
            return $rate_limit;
        }
        $signed_request = self::enforce_signed_request_policy($request, 'order_status');
        if (is_wp_error($signed_request)) {
            return $signed_request;
        }
        if (self::signed_request_verified($request)) {
            return true;
        }
        if (self::has_valid_merchant_token($request)) {
            return true;
        }
        $order = wc_get_order(intval($request['id']));
        if (!$order) {
            return new WP_Error('agentcart_not_found', 'Order not found.', ['status' => 404]);
        }
        $configured = (string) $order->get_meta(self::STATUS_TOKEN_META, true);
        $supplied = (string) $request->get_header('x-agentcart-order-token');
        if ($configured !== '' && $supplied !== '' && hash_equals($configured, $supplied)) {
            return true;
        }
        return new WP_Error('agentcart_unauthorized', 'Missing or invalid AgentCart order status token.', ['status' => 401]);
    }

    public static function authorize_refund(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        $rate_limit = self::enforce_rate_limit($request, 'refund');
        if (is_wp_error($rate_limit)) {
            return $rate_limit;
        }
        $signed_request = self::enforce_signed_request_policy($request, 'refund');
        if (is_wp_error($signed_request)) {
            return $signed_request;
        }
        if (self::signed_request_verified($request)) {
            return true;
        }
        if (self::has_valid_merchant_token($request)) {
            return true;
        }
        return new WP_Error(
            'agentcart_unauthorized',
            'Refund creation requires the merchant token. Buyer-facing refund requests should be approved by the merchant or trusted gateway before this endpoint is called.',
            ['status' => 401]
        );
    }

    public static function authorize_cancellation(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
        }
        $rate_limit = self::enforce_rate_limit($request, 'cancellation');
        if (is_wp_error($rate_limit)) {
            return $rate_limit;
        }
        $signed_request = self::enforce_signed_request_policy($request, 'cancellation');
        if (is_wp_error($signed_request)) {
            return $signed_request;
        }
        if (self::signed_request_verified($request)) {
            return true;
        }
        if (self::has_valid_merchant_token($request)) {
            return true;
        }
        return new WP_Error(
            'agentcart_unauthorized',
            'Cancellation creation requires the merchant token. Buyer-facing cancellation requests should be approved by the merchant or trusted gateway before this endpoint is called.',
            ['status' => 401]
        );
    }

    private static function enforce_signed_request_policy(WP_REST_Request $request, $bucket) {
        $bucket = sanitize_key((string) $bucket);
        $mode = self::signed_request_mode();
        if ($mode === 'off') {
            return true;
        }

        $required = self::signed_request_required_for_bucket($bucket);
        $has_signature = trim((string) $request->get_header('x-agentcart-signature')) !== '';
        if (!$required && !$has_signature) {
            return true;
        }

        if (empty(self::signed_request_keys())) {
            $error = new WP_Error(
                'agentcart_signed_request_not_configured',
                'Signed request mode requires at least one active or retiring signing key.',
                ['status' => 401, 'bucket' => $bucket]
            );
            self::record_signed_request_audit_event($request, $bucket, 'rejected', ['error' => $error]);
            return $error;
        }
        if ($required && !$has_signature) {
            $error = new WP_Error(
                'agentcart_signed_request_required',
                'This AgentCart endpoint requires a signed HTTP request.',
                ['status' => 401, 'bucket' => $bucket]
            );
            self::record_signed_request_audit_event($request, $bucket, 'rejected', ['error' => $error]);
            return $error;
        }

        $verification = self::verify_signed_request($request, $bucket);
        if (is_wp_error($verification)) {
            self::record_signed_request_audit_event($request, $bucket, 'rejected', ['error' => $verification]);
            return $verification;
        }
        self::record_signed_request_audit_event($request, $bucket, 'verified', $verification);
        $request->set_param('_agentcart_signed_request_verified', true);
        $request->set_param('_agentcart_signed_request_signer', (string) ($verification['signer'] ?? ''));
        $request->set_param('_agentcart_signed_request_key_id', (string) ($verification['key_id'] ?? ''));
        return true;
    }

    private static function verify_signed_request(WP_REST_Request $request, $bucket) {
        $method = strtoupper(trim((string) $request->get_header('x-agentcart-signed-method')));
        if ($method === '') {
            return new WP_Error('agentcart_signed_request_missing_method', 'Signed request header X-AgentCart-Signed-Method is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        if ($method !== strtoupper((string) $request->get_method())) {
            return new WP_Error('agentcart_signed_request_method_mismatch', 'Signed request method does not match the HTTP method.', ['status' => 401, 'bucket' => $bucket]);
        }

        $path = trim((string) $request->get_header('x-agentcart-signed-path'));
        if ($path === '') {
            return new WP_Error('agentcart_signed_request_missing_path', 'Signed request header X-AgentCart-Signed-Path is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        if (!hash_equals(self::current_request_path_with_query(), $path)) {
            return new WP_Error('agentcart_signed_request_path_mismatch', 'Signed request path does not match the HTTP request target.', ['status' => 401, 'bucket' => $bucket]);
        }

        $digest = strtolower(trim((string) $request->get_header('x-agentcart-content-digest')));
        if ($digest === '') {
            return new WP_Error('agentcart_signed_request_missing_digest', 'Signed request header X-AgentCart-Content-Digest is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        $expected_digest = self::signed_request_content_digest($request);
        if (!hash_equals($expected_digest, $digest)) {
            return new WP_Error('agentcart_signed_request_digest_mismatch', 'Signed request body digest does not match the request body.', ['status' => 401, 'bucket' => $bucket]);
        }

        $nonce = trim((string) $request->get_header('x-agentcart-nonce'));
        if ($nonce === '') {
            return new WP_Error('agentcart_signed_request_missing_nonce', 'Signed request header X-AgentCart-Nonce is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        if (strlen($nonce) < 12 || strlen($nonce) > 128 || preg_match('/[^A-Za-z0-9._:-]/', $nonce)) {
            return new WP_Error('agentcart_signed_request_invalid_nonce', 'Signed request nonce must be 12-128 safe characters.', ['status' => 401, 'bucket' => $bucket]);
        }

        $expires_raw = trim((string) $request->get_header('x-agentcart-expires-at'));
        if ($expires_raw === '') {
            return new WP_Error('agentcart_signed_request_missing_expiry', 'Signed request header X-AgentCart-Expires-At is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        if (!ctype_digit($expires_raw)) {
            return new WP_Error('agentcart_signed_request_invalid_expiry', 'Signed request expiry must be a Unix timestamp in seconds.', ['status' => 401, 'bucket' => $bucket]);
        }
        $expires_at = intval($expires_raw);
        $now = time();
        if ($expires_at + self::SIGNED_REQUEST_CLOCK_SKEW_SECONDS < $now) {
            return new WP_Error('agentcart_signed_request_expired', 'Signed request has expired.', ['status' => 401, 'bucket' => $bucket]);
        }
        if ($expires_at > $now + self::SIGNED_REQUEST_MAX_TTL_SECONDS) {
            return new WP_Error('agentcart_signed_request_expiry_too_far', 'Signed request expiry is too far in the future.', ['status' => 401, 'bucket' => $bucket]);
        }

        $signer = sanitize_text_field((string) ($request->get_header('x-agentcart-signer') ?: 'agentcart'));
        $signature_header = trim((string) $request->get_header('x-agentcart-signature'));
        $signature_alg = self::signed_request_signature_alg($request, $signature_header);
        if ($signature_alg === '') {
            return new WP_Error('agentcart_signed_request_unsupported_signature_alg', 'Signed request signature algorithm is not supported.', ['status' => 401, 'bucket' => $bucket]);
        }
        $signature = self::normalize_signed_request_signature($signature_header, $signature_alg);
        if ($signature === '') {
            return new WP_Error('agentcart_signed_request_missing_signature', 'Signed request header X-AgentCart-Signature is required.', ['status' => 401, 'bucket' => $bucket]);
        }
        if (!self::signed_request_signature_format_valid($signature, $signature_alg)) {
            return new WP_Error('agentcart_signed_request_invalid_signature', 'Signed request signature format is invalid for the selected algorithm.', ['status' => 401, 'bucket' => $bucket, 'signature_alg' => $signature_alg]);
        }

        $candidates = self::signed_request_key_candidates_for_signer($signer);
        if (!$candidates) {
            return new WP_Error('agentcart_signed_request_unknown_signer', 'Signed request signer is not accepted by this merchant.', ['status' => 401, 'bucket' => $bucket]);
        }

        $canonical = self::signed_request_canonical_string($method, $path, $expected_digest, $nonce, $expires_raw, $signer);
        $matched_key = null;
        foreach ($candidates as $key) {
            if (self::signed_request_key_alg($key) !== $signature_alg) {
                continue;
            }
            if (self::signed_request_signature_matches($canonical, $signature, $signature_alg, $key)) {
                $matched_key = $key;
                break;
            }
        }
        if (!$matched_key) {
            return new WP_Error('agentcart_signed_request_signature_mismatch', 'Signed request signature does not match the canonical request.', ['status' => 401, 'bucket' => $bucket]);
        }

        $nonce_key = self::signed_request_nonce_transient_name($signer, $nonce);
        if (get_transient($nonce_key) !== false) {
            return new WP_Error('agentcart_signed_request_replay', 'Signed request nonce has already been used.', ['status' => 409, 'bucket' => $bucket]);
        }
        set_transient($nonce_key, '1', max(60, ($expires_at - $now) + self::SIGNED_REQUEST_CLOCK_SKEW_SECONDS));

        return [
            'state' => 'verified',
            'signer' => $signer,
            'key_id' => (string) ($matched_key['id'] ?? ''),
            'key_state' => (string) ($matched_key['state'] ?? ''),
            'signature_alg' => $signature_alg,
            'bucket' => $bucket,
            'expires_at' => $expires_at,
        ];
    }

    private static function signed_request_verified(WP_REST_Request $request) {
        return $request->get_param('_agentcart_signed_request_verified') === true;
    }

    private static function signed_request_required_for_bucket($bucket) {
        $mode = self::signed_request_mode();
        $bucket = sanitize_key((string) $bucket);
        if ($mode === 'require_checkout') {
            return $bucket === 'checkout';
        }
        if ($mode === 'require_mutations') {
            return in_array($bucket, ['checkout', 'refund', 'cancellation'], true);
        }
        if ($mode === 'require_all_sensitive') {
            return in_array($bucket, ['quote', 'checkout', 'order_status', 'refund', 'cancellation'], true);
        }
        return false;
    }

    private static function signed_request_content_digest(WP_REST_Request $request) {
        return 'sha-256=' . hash('sha256', (string) $request->get_body());
    }

    private static function signed_request_canonical_string($method, $path, $digest, $nonce, $expires_at, $signer) {
        return implode("\n", [
            'agentcart-signed-request-v1',
            strtoupper((string) $method),
            (string) $path,
            strtolower((string) $digest),
            (string) $nonce,
            (string) $expires_at,
            (string) $signer,
        ]);
    }

    private static function signed_request_signature_alg(WP_REST_Request $request, $signature_header = '') {
        $alg = sanitize_key((string) $request->get_header('x-agentcart-signature-alg'));
        if ($alg === '') {
            $signature_header = trim((string) $signature_header);
            if (stripos($signature_header, 'rsa-sha256=') === 0) {
                return 'rsa-sha256';
            }
            return 'hmac-sha256';
        }
        if (in_array($alg, ['hmac-sha256', 'agentcart-hmac-sha256-v1'], true)) {
            return 'hmac-sha256';
        }
        if (in_array($alg, ['rsa-sha256', 'agentcart-rsa-sha256-v1'], true)) {
            return 'rsa-sha256';
        }
        return '';
    }

    private static function normalize_signed_request_signature($signature_header, $signature_alg) {
        $signature = trim((string) $signature_header);
        if ($signature_alg === 'hmac-sha256') {
            $signature = strtolower($signature);
            if (strpos($signature, 'sha256=') === 0) {
                $signature = substr($signature, 7);
            } elseif (strpos($signature, 'hmac-sha256=') === 0) {
                $signature = substr($signature, 12);
            }
            return $signature;
        }
        if ($signature_alg === 'rsa-sha256') {
            if (stripos($signature, 'rsa-sha256=') === 0) {
                $signature = substr($signature, 11);
            }
            return preg_replace('/\s+/', '', $signature);
        }
        return '';
    }

    private static function signed_request_signature_format_valid($signature, $signature_alg) {
        if ($signature_alg === 'hmac-sha256') {
            return preg_match('/^[a-f0-9]{64}$/', (string) $signature) === 1;
        }
        if ($signature_alg === 'rsa-sha256') {
            // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_decode -- Decodes a request signature, not executable code.
            $decoded = base64_decode((string) $signature, true);
            return is_string($decoded) && strlen($decoded) >= 64;
        }
        return false;
    }

    private static function signed_request_signature_matches($canonical, $signature, $signature_alg, $key) {
        if ($signature_alg === 'hmac-sha256') {
            $expected_signature = hash_hmac('sha256', (string) $canonical, (string) ($key['secret'] ?? ''));
            return hash_equals($expected_signature, (string) $signature);
        }
        if ($signature_alg === 'rsa-sha256') {
            if (!function_exists('openssl_verify')) {
                return false;
            }
            $public_key = (string) ($key['public_key'] ?? '');
            // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_decode -- Decodes a request signature, not executable code.
            $decoded = base64_decode((string) $signature, true);
            if ($public_key === '' || !is_string($decoded)) {
                return false;
            }
            return openssl_verify((string) $canonical, $decoded, $public_key, OPENSSL_ALGO_SHA256) === 1;
        }
        return false;
    }

    private static function signed_request_key_candidates_for_signer($signer) {
        $keys = self::signed_request_keys();
        if (!$keys) {
            return [];
        }
        $matches = [];
        foreach ($keys as $key) {
            if (hash_equals((string) ($key['id'] ?? ''), (string) $signer)) {
                $matches[] = $key;
            }
        }
        if ($matches) {
            return $matches;
        }
        if (preg_match('/^(sig_[a-f0-9]{16}|sig_rsa_[a-f0-9]{16}|legacy|wp-config)$/', (string) $signer)) {
            return [];
        }
        return $keys;
    }

    private static function signed_request_key_alg($key) {
        $alg = sanitize_key((string) ($key['alg'] ?? ''));
        if ($alg === '') {
            $alg = !empty($key['public_key']) ? 'rsa-sha256' : 'hmac-sha256';
        }
        if (in_array($alg, ['rsa-sha256', 'agentcart-rsa-sha256-v1'], true)) {
            return 'rsa-sha256';
        }
        return 'hmac-sha256';
    }

    private static function signed_request_nonce_transient_name($signer, $nonce) {
        return self::SIGNED_REQUEST_NONCE_PREFIX . hash('sha256', (string) $signer . '|' . (string) $nonce);
    }

    private static function signed_request_audit_events() {
        $stored = get_option(self::SIGNED_REQUEST_AUDIT_OPTION, []);
        if (!is_array($stored)) {
            return [];
        }
        return array_values(array_filter($stored, 'is_array'));
    }

    private static function record_signed_request_audit_event(WP_REST_Request $request, $bucket, $state, $detail = []) {
        $detail = is_array($detail) ? $detail : [];
        $event = self::signed_request_audit_event($request, $bucket, $state, $detail);
        $events = self::signed_request_audit_events();
        $events[] = $event;
        if (count($events) > self::SIGNED_REQUEST_AUDIT_LIMIT) {
            $events = array_slice($events, -1 * self::SIGNED_REQUEST_AUDIT_LIMIT);
        }
        update_option(self::SIGNED_REQUEST_AUDIT_OPTION, $events, false);
    }

    private static function signed_request_audit_event(WP_REST_Request $request, $bucket, $state, $detail) {
        $error = isset($detail['error']) && is_wp_error($detail['error']) ? $detail['error'] : null;
        $error_data = $error ? $error->get_error_data() : null;
        $error_data = is_array($error_data) ? $error_data : [];
        $method_header = strtoupper(trim((string) $request->get_header('x-agentcart-signed-method')));
        $path_header = trim((string) $request->get_header('x-agentcart-signed-path'));
        $digest_header = strtolower(trim((string) $request->get_header('x-agentcart-content-digest')));
        $nonce = trim((string) $request->get_header('x-agentcart-nonce'));
        $expires_raw = trim((string) $request->get_header('x-agentcart-expires-at'));
        $signer = sanitize_text_field((string) ($request->get_header('x-agentcart-signer') ?: 'agentcart'));
        $signature_header = trim((string) $request->get_header('x-agentcart-signature'));
        $signature_alg = self::signed_request_signature_alg($request, $signature_header);
        $signature = $signature_alg ? self::normalize_signed_request_signature($signature_header, $signature_alg) : $signature_header;
        $expected_digest = self::signed_request_content_digest($request);
        return [
            'id' => 'sigreq_' . substr(hash('sha256', wp_generate_uuid4() . '|' . microtime(true)), 0, 16),
            'checked_at' => gmdate('c'),
            'bucket' => sanitize_key((string) $bucket),
            'state' => sanitize_key((string) $state),
            'error_code' => $error ? $error->get_error_code() : '',
            'error_status' => intval($error_data['status'] ?? 0),
            'method' => $method_header ?: strtoupper((string) $request->get_method()),
            'request_method' => strtoupper((string) $request->get_method()),
            'path_hash' => self::signed_request_audit_hash($path_header ?: self::current_request_path_with_query()),
            'supplied_digest_hash' => self::signed_request_audit_hash($digest_header),
            'expected_digest_hash' => self::signed_request_audit_hash($expected_digest),
            'nonce_hash' => $nonce === '' ? '' : self::signed_request_audit_hash($signer . '|' . $nonce),
            'signature_hash' => $signature === '' ? '' : self::signed_request_audit_hash($signature),
            'expires_at' => ctype_digit($expires_raw) ? intval($expires_raw) : null,
            'signer' => $signer,
            'key_id' => sanitize_text_field((string) ($detail['key_id'] ?? '')),
            'key_state' => sanitize_key((string) ($detail['key_state'] ?? '')),
            'signature_alg' => sanitize_key((string) ($detail['signature_alg'] ?? ($signature_alg ?: 'unsupported'))),
            'required' => self::signed_request_required_for_bucket($bucket),
            'mode' => self::signed_request_mode(),
        ];
    }

    private static function signed_request_audit_hash($value) {
        $value = (string) $value;
        return $value === '' ? '' : hash('sha256', $value);
    }

    private static function signed_request_audit_summary() {
        $events = self::signed_request_audit_events();
        $latest = $events ? end($events) : null;
        return [
            'enabled' => true,
            'retention_limit' => self::SIGNED_REQUEST_AUDIT_LIMIT,
            'event_count' => count($events),
            'latest' => is_array($latest) ? [
                'checked_at' => (string) ($latest['checked_at'] ?? ''),
                'bucket' => (string) ($latest['bucket'] ?? ''),
                'state' => (string) ($latest['state'] ?? ''),
                'error_code' => (string) ($latest['error_code'] ?? ''),
                'signer' => (string) ($latest['signer'] ?? ''),
                'key_id' => (string) ($latest['key_id'] ?? ''),
            ] : null,
        ];
    }

    private static function current_request_path_with_query() {
        $uri = (string) sanitize_text_field(wp_unslash($_SERVER['REQUEST_URI'] ?? ''));
        $parts = wp_parse_url($uri);
        $path = (string) ($parts['path'] ?? '');
        $query = (string) ($parts['query'] ?? '');
        return $query !== '' ? $path . '?' . $query : $path;
    }

    private static function has_valid_merchant_token(WP_REST_Request $request) {
        $configured = self::merchant_token_value();
        $supplied = $request->get_header('x-agentcart-merchant-token');
        return $configured && $supplied && hash_equals((string) $configured, (string) $supplied);
    }

    private static function enforce_rate_limit(WP_REST_Request $request, $bucket = null) {
        $bucket = $bucket ?: self::rate_limit_bucket_for_request($request);
        return self::enforce_rate_limit_for_client($bucket, self::rate_limit_client_key($request));
    }

    private static function enforce_well_known_rate_limit($path) {
        $bucket = self::well_known_rate_limit_bucket_for_path($path);
        return self::enforce_rate_limit_for_client($bucket, self::rate_limit_client_key_from_server(''));
    }

    private static function enforce_rate_limit_for_client($bucket, $client_key) {
        $policy = self::rate_limit_policy($bucket);
        if (!$policy || intval($policy['limit'] ?? 0) <= 0) {
            return true;
        }
        $window = intval($policy['window'] ?? self::RATE_LIMIT_WINDOW_SECONDS);
        $limit = intval($policy['limit']);
        $window_start = self::rate_limit_window_start($window);
        $transient = self::rate_limit_transient_name_for_client((string) $policy['bucket'], $window, $window_start, $client_key);
        $count = intval(get_transient($transient));
        if ($count >= $limit) {
            return self::rate_limit_error($policy, $window_start, $window, $count);
        }
        set_transient($transient, (string) ($count + 1), $window);
        return true;
    }

    private static function rate_limit_policy($bucket) {
        $bucket = sanitize_key((string) $bucket);
        $policies = [
            'capability' => ['bucket' => 'capability', 'limit' => 120, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'catalog' => ['bucket' => 'catalog', 'limit' => 120, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'product' => ['bucket' => 'product', 'limit' => 120, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'registry' => ['bucket' => 'registry', 'limit' => 60, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'quote' => ['bucket' => 'quote', 'limit' => 30, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'checkout' => ['bucket' => 'checkout', 'limit' => 12, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'order_status' => ['bucket' => 'order_status', 'limit' => 60, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'refund' => ['bucket' => 'refund', 'limit' => 10, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'cancellation' => ['bucket' => 'cancellation', 'limit' => 10, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
            'public_read' => ['bucket' => 'public_read', 'limit' => 120, 'window' => self::RATE_LIMIT_WINDOW_SECONDS],
        ];
        return $policies[$bucket] ?? $policies['public_read'];
    }

    private static function public_rate_limits_document() {
        $document = [];
        foreach (['capability', 'catalog', 'product', 'registry', 'quote', 'checkout', 'order_status', 'refund', 'cancellation'] as $bucket) {
            $policy = self::rate_limit_policy($bucket);
            $document[$bucket] = [
                'limit' => intval($policy['limit']),
                'window_seconds' => intval($policy['window']),
                'scope' => 'hashed_client',
            ];
        }
        return $document;
    }

    private static function rate_limit_bucket_for_request(WP_REST_Request $request) {
        $route = (string) $request->get_route();
        $method = strtoupper((string) $request->get_method());
        if (strpos($route, '/quote') !== false && $method === 'POST') {
            return 'quote';
        }
        if (strpos($route, '/catalog') !== false) {
            return 'catalog';
        }
        if (strpos($route, '/products/') !== false) {
            return 'product';
        }
        if (strpos($route, '/capability') !== false) {
            return 'capability';
        }
        return 'public_read';
    }

    private static function rate_limit_transient_name(WP_REST_Request $request, $bucket, $window) {
        return self::rate_limit_transient_name_for_client(
            $bucket,
            $window,
            self::rate_limit_window_start($window),
            self::rate_limit_client_key($request)
        );
    }

    private static function rate_limit_transient_name_for_client($bucket, $window, $window_start, $client_key) {
        return self::RATE_LIMIT_TRANSIENT_PREFIX . hash('sha256', implode('|', [
            sanitize_key((string) $bucket),
            (string) intval($window_start),
            (string) intval($window),
            (string) $client_key,
        ]));
    }

    private static function rate_limit_client_key(WP_REST_Request $request) {
        $token_hint = '';
        if (self::has_valid_merchant_token($request)) {
            $token_hint = hash('sha256', self::merchant_token_value());
        }
        return self::rate_limit_client_key_from_server($token_hint);
    }

    private static function rate_limit_client_key_from_server($token_hint = '') {
        $ip = sanitize_text_field((string) wp_unslash($_SERVER['REMOTE_ADDR'] ?? 'unknown'));
        $agent = sanitize_text_field((string) wp_unslash($_SERVER['HTTP_USER_AGENT'] ?? ''));
        return hash('sha256', implode('|', [$ip, $agent, $token_hint]));
    }

    private static function rate_limit_window_start($window) {
        $window = max(1, intval($window));
        return intval(floor(time() / $window)) * $window;
    }

    private static function rate_limit_error($policy, $window_start, $window, $count) {
        $reset_at = intval($window_start) + max(1, intval($window));
        $retry_after = max(1, $reset_at - time());
        $limit = intval($policy['limit']);
        return new WP_Error(
            'agentcart_rate_limited',
            'Too many AgentCart requests. Try again shortly.',
            [
                'status' => 429,
                'bucket' => (string) $policy['bucket'],
                'limit' => $limit,
                'window_seconds' => intval($window),
                'retry_after_seconds' => $retry_after,
                'remaining' => max(0, $limit - intval($count)),
                'reset_at' => gmdate('c', $reset_at),
            ]
        );
    }

    private static function well_known_rate_limit_bucket_for_path($path) {
        return $path === '/.well-known/agentcart.json' ? 'capability' : 'registry';
    }

    private static function merchant_token_value() {
        return defined('AGENTCART_SHOPBRIDGE_TOKEN') ? (string) AGENTCART_SHOPBRIDGE_TOKEN : (string) get_option(self::TOKEN_OPTION, '');
    }

    private static function registry_record_hash_value() {
        return self::registry_record_hash(self::suggested_registry_record());
    }

    private static function registry_public_check_result() {
        $stored = get_option(self::REGISTRY_PUBLIC_CHECK_OPTION, []);
        return is_array($stored) ? $stored : [];
    }

    private static function registry_connection_status() {
        $stored = get_option(self::REGISTRY_CONNECTION_STATUS_OPTION, []);
        return is_array($stored) ? $stored : [];
    }

    private static function registry_health_check_result() {
        $stored = get_option(self::REGISTRY_HEALTH_CHECK_OPTION, []);
        return is_array($stored) ? $stored : [];
    }

    private static function registry_connection_url() {
        if (defined('AGENTCART_REGISTRY_CONNECTION_URL')) {
            $value = esc_url_raw((string) AGENTCART_REGISTRY_CONNECTION_URL);
            if ($value !== '') {
                return $value;
            }
        }
        return esc_url_raw((string) get_option(self::REGISTRY_CONNECTION_URL_OPTION, ''));
    }

    private static function registry_connection_token() {
        if (defined('AGENTCART_REGISTRY_CONNECTION_TOKEN')) {
            $value = trim((string) AGENTCART_REGISTRY_CONNECTION_TOKEN);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::REGISTRY_CONNECTION_TOKEN_OPTION, ''));
    }

    private static function submit_registry_connection($operation) {
        $operation = sanitize_key((string) $operation);
        if (!in_array($operation, ['upsert', 'revoke'], true)) {
            $operation = 'upsert';
        }
        $registry_url = self::registry_connection_url();
        $record_hash = self::registry_record_hash_value();
        if ($registry_url === '') {
            return [
                'schema' => 'agentcart.shopbridge.registry_connection_status.v1',
                'state' => 'failed',
                'operation' => $operation,
                'checked_at' => self::current_registry_timestamp(),
                'record_hash' => $record_hash,
                'message' => 'Registry connection URL is not configured.',
            ];
        }

        $payload = self::registry_connection_payload($operation);
        $result = self::call_registry_connection($registry_url, $payload);
        $result['schema'] = 'agentcart.shopbridge.registry_connection_status.v1';
        $result['operation'] = $operation;
        $result['checked_at'] = self::current_registry_timestamp();
        $result['registry_url'] = $registry_url;
        $result['record_hash'] = $record_hash;
        return $result;
    }

    private static function registry_connection_payload($operation) {
        $record = self::suggested_registry_record();
        $record_hash = self::registry_record_hash($record);
        return [
            'schema' => 'agentcart.shopbridge.registry_connection_request.v1',
            'operation' => sanitize_key((string) $operation),
            'generated_at' => self::current_registry_timestamp(),
            'merchant_id' => self::merchant()['id'],
            'domain' => self::public_origin_host(),
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'registry_bundle_url' => self::registry_bundle_url(),
            'registry_record' => $record,
            'record_hash' => $record_hash,
            'registry_onboarding_bundle' => self::registry_onboarding_bundle(),
            'proof_document' => self::registry_domain_proof(),
            'revocation_document' => self::registry_revocations(),
            'public_check' => self::registry_public_check_result(),
            'idempotency_key' => hash('sha256', implode('|', [
                sanitize_key((string) $operation),
                $record_hash,
                self::registry_updated_at(),
            ])),
        ];
    }

    private static function call_registry_connection($registry_url, $payload) {
        $headers = [
            'Content-Type' => 'application/json',
            'Accept' => 'application/json',
            'X-AgentCart-Registry-Operation' => sanitize_key((string) ($payload['operation'] ?? 'upsert')),
        ];
        $token = self::registry_connection_token();
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
        }
        $response = wp_remote_post($registry_url, [
            'timeout' => 12,
            'redirection' => 0,
            'headers' => $headers,
            'body' => wp_json_encode($payload, JSON_UNESCAPED_SLASHES),
        ]);
        if (is_wp_error($response)) {
            return [
                'state' => 'failed',
                'status' => 0,
                'message' => $response->get_error_message(),
                'response' => null,
            ];
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        $message = is_array($decoded)
            ? sanitize_text_field((string) ($decoded['message'] ?? $decoded['state'] ?? ''))
            : sanitize_text_field(substr((string) $raw_body, 0, 240));
        return [
            'state' => ($status >= 200 && $status < 300) ? 'submitted' : 'failed',
            'status' => $status,
            'message' => $message !== '' ? $message : (($status >= 200 && $status < 300) ? 'Registry accepted the request.' : 'Registry returned HTTP ' . $status . '.'),
            'response' => is_array($decoded) ? self::canonicalize_json_value($decoded) : null,
        ];
    }

    private static function run_registry_health_check() {
        $checked_at = self::current_registry_timestamp();
        $record_hash = self::registry_record_hash_value();
        $merchant_id = self::merchant()['id'];
        $health_url = self::registry_connection_endpoint_url('health');
        $monitor_url = self::registry_connection_endpoint_url('monitor');
        if (self::registry_connection_url() === '' || $health_url === '') {
            return [
                'schema' => 'agentcart.shopbridge.registry_health_check.v1',
                'state' => 'failed',
                'checked_at' => $checked_at,
                'record_hash' => $record_hash,
                'merchant_id' => $merchant_id,
                'message' => 'Registry connection URL is not configured.',
                'errors' => ['registry_connection_url_missing'],
            ];
        }

        $health_result = self::fetch_registry_connection_json($health_url, false);
        $monitor_result = $monitor_url !== '' ? self::fetch_registry_connection_json($monitor_url, true) : [
            'ok' => false,
            'status' => 0,
            'error' => 'registry_monitor_url_missing',
            'body' => null,
        ];
        $errors = [];
        $health_summary = [];
        $current_record = [];
        if (empty($health_result['ok'])) {
            $errors[] = 'registry_health_fetch_failed';
        } else {
            $health_body = is_array($health_result['body'] ?? null) ? $health_result['body'] : [];
            $health_summary = self::registry_health_response_summary($health_body);
            $current_record = self::registry_health_current_record_check($health_body, $record_hash, $merchant_id);
            if (empty($current_record)) {
                $errors[] = 'current_record_not_found_in_registry_health';
            } else {
                $record_state = sanitize_key((string) ($current_record['state'] ?? 'unknown'));
                if ($record_state !== 'verified') {
                    $errors[] = 'current_record_' . ($record_state ?: 'unknown');
                }
                if (empty($current_record['eligible'])) {
                    $errors[] = 'current_record_not_eligible';
                }
                $record_errors = is_array($current_record['errors'] ?? null) ? $current_record['errors'] : [];
                foreach ($record_errors as $record_error) {
                    $errors[] = 'registry_' . sanitize_key((string) $record_error);
                }
            }
        }

        $monitor_summary = self::registry_monitor_response_summary($monitor_result);
        $errors = array_values(array_unique(array_filter($errors)));
        $state = empty($health_result['ok']) ? 'failed' : (empty($errors) ? 'verified' : 'attention');
        return [
            'schema' => 'agentcart.shopbridge.registry_health_check.v1',
            'state' => $state,
            'checked_at' => $checked_at,
            'registry_url' => self::registry_connection_endpoint_url('registry'),
            'health_url' => $health_url,
            'monitor_url' => $monitor_url,
            'record_hash' => $record_hash,
            'merchant_id' => $merchant_id,
            'message' => $state === 'verified'
                ? 'Current registry record is verified and eligible.'
                : 'Current registry record is not verified, not eligible, or could not be found.',
            'errors' => $errors,
            'health' => [
                'ok' => !empty($health_result['ok']),
                'status' => intval($health_result['status'] ?? 0),
                'error' => sanitize_text_field((string) ($health_result['error'] ?? '')),
                'summary' => $health_summary,
                'current_record' => $current_record,
            ],
            'monitor' => $monitor_summary,
        ];
    }

    private static function registry_connection_endpoint_url($endpoint) {
        $endpoint = sanitize_key((string) $endpoint);
        if (!in_array($endpoint, ['registry', 'records', 'health', 'monitor'], true)) {
            return '';
        }
        $registry_url = self::registry_connection_url();
        if ($registry_url === '') {
            return '';
        }
        $parts = wp_parse_url($registry_url);
        if (!is_array($parts) || empty($parts['scheme']) || empty($parts['host'])) {
            return '';
        }
        $scheme = strtolower((string) $parts['scheme']);
        if (!in_array($scheme, ['http', 'https'], true)) {
            return '';
        }
        $host = strtolower((string) $parts['host']);
        $port = isset($parts['port']) ? ':' . intval($parts['port']) : '';
        $path = (string) ($parts['path'] ?? '');
        $registry_path = '/v1/registry';
        $position = strpos($path, '/v1/registry');
        if ($position !== false) {
            $registry_path = substr($path, 0, $position + strlen('/v1/registry'));
        }
        $base = $scheme . '://' . $host . $port . $registry_path;
        if ($endpoint === 'registry') {
            return esc_url_raw($base);
        }
        return esc_url_raw($base . '/' . $endpoint);
    }

    private static function fetch_registry_connection_json($url, $authenticated = false) {
        $headers = [
            'Accept' => 'application/json',
        ];
        $token = self::registry_connection_token();
        if ($authenticated && $token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
            $headers['X-AgentCart-Token'] = $token;
            $headers['X-AgentCart-Registry-Token'] = $token;
        }
        $response = wp_remote_get(esc_url_raw((string) $url), [
            'timeout' => 8,
            'redirection' => 0,
            'headers' => $headers,
        ]);
        if (is_wp_error($response)) {
            return [
                'ok' => false,
                'status' => 0,
                'error' => $response->get_error_message(),
                'body' => null,
            ];
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded)) {
            return [
                'ok' => false,
                'status' => $status,
                'error' => $status === 401 ? 'unauthorized' : 'invalid_json_or_http_status',
                'body' => null,
            ];
        }
        return [
            'ok' => true,
            'status' => $status,
            'error' => '',
            'body' => self::canonicalize_json_value($decoded),
        ];
    }

    private static function registry_health_response_summary($health_body) {
        $summary = is_array($health_body['summary'] ?? null) ? $health_body['summary'] : [];
        return [
            'state' => sanitize_key((string) ($summary['state'] ?? 'unknown')),
            'entry_count' => intval($summary['entry_count'] ?? 0),
            'eligible_count' => intval($summary['eligible_count'] ?? 0),
            'ineligible_count' => intval($summary['ineligible_count'] ?? 0),
            'alert_count' => intval($summary['alert_count'] ?? 0),
            'critical_count' => intval($summary['critical_count'] ?? 0),
            'warning_count' => intval($summary['warning_count'] ?? 0),
            'hosted_entry_count' => intval($summary['hosted_entry_count'] ?? 0),
            'hosted_revocation_count' => intval($summary['hosted_revocation_count'] ?? 0),
            'source_error_count' => intval($summary['source_error_count'] ?? 0),
        ];
    }

    private static function registry_health_current_record_check($health_body, $record_hash, $merchant_id) {
        $checks = is_array($health_body['checks'] ?? null) ? $health_body['checks'] : [];
        $merchant_match = [];
        foreach ($checks as $check) {
            if (!is_array($check)) {
                continue;
            }
            $candidate_hash = (string) ($check['registry_record_hash'] ?? $check['record_hash'] ?? '');
            $candidate_merchant_id = (string) ($check['merchant_id'] ?? '');
            $summary = self::registry_health_record_summary($check);
            if ($candidate_hash !== '' && hash_equals((string) $record_hash, $candidate_hash)) {
                return $summary;
            }
            if ($merchant_match === [] && $candidate_merchant_id !== '' && hash_equals((string) $merchant_id, $candidate_merchant_id)) {
                $merchant_match = $summary;
            }
        }
        return $merchant_match;
    }

    private static function registry_health_record_summary($check) {
        $errors = is_array($check['errors'] ?? null) ? $check['errors'] : [];
        return [
            'merchant_id' => sanitize_text_field((string) ($check['merchant_id'] ?? '')),
            'name' => sanitize_text_field((string) ($check['name'] ?? '')),
            'domain' => sanitize_text_field((string) ($check['domain'] ?? '')),
            'manifest_url' => esc_url_raw((string) ($check['manifest_url'] ?? '')),
            'registry_record_hash' => sanitize_text_field((string) ($check['registry_record_hash'] ?? $check['record_hash'] ?? '')),
            'state' => sanitize_key((string) ($check['state'] ?? 'unknown')),
            'eligible' => !empty($check['eligible']),
            'reason' => sanitize_text_field((string) ($check['reason'] ?? '')),
            'errors' => array_values(array_map('sanitize_text_field', array_map('strval', $errors))),
            'error_count' => intval($check['error_count'] ?? count($errors)),
            'checked_at' => sanitize_text_field((string) ($check['checked_at'] ?? '')),
            'updated_at' => sanitize_text_field((string) ($check['updated_at'] ?? '')),
            'age_days' => isset($check['age_days']) && is_numeric($check['age_days']) ? intval($check['age_days']) : null,
            'manifest_fetched' => !empty($check['manifest_fetched']),
            'manifest_source' => sanitize_text_field((string) ($check['manifest_source'] ?? '')),
            'payment_recipient_configured' => !empty($check['payment_recipient_configured']),
        ];
    }

    private static function registry_monitor_response_summary($monitor_result) {
        if (empty($monitor_result['ok'])) {
            $error = sanitize_text_field((string) ($monitor_result['error'] ?? 'not_fetched'));
            return [
                'ok' => false,
                'state' => $error === 'unauthorized' ? 'unauthorized' : 'failed',
                'status' => intval($monitor_result['status'] ?? 0),
                'error' => $error,
            ];
        }
        $body = is_array($monitor_result['body'] ?? null) ? $monitor_result['body'] : [];
        $configured = is_array($body['configured'] ?? null) ? $body['configured'] : [];
        $alert_delivery = is_array($configured['alert_delivery'] ?? null) ? $configured['alert_delivery'] : [];
        $last_snapshot = is_array($body['last_snapshot'] ?? null) ? $body['last_snapshot'] : [];
        $last_snapshot_summary = is_array($last_snapshot['summary'] ?? null) ? $last_snapshot['summary'] : [];
        $last_changes = is_array($body['last_changes'] ?? null) ? $body['last_changes'] : [];
        $last_notifications = is_array($body['last_notifications'] ?? null) ? $body['last_notifications'] : [];
        $last_notification_results = is_array($last_notifications['results'] ?? null) ? $last_notifications['results'] : [];
        $failed_notification_results = 0;
        foreach ($last_notification_results as $notification_result) {
            if (is_array($notification_result) && empty($notification_result['ok'])) {
                $failed_notification_results++;
            }
        }
        return [
            'ok' => true,
            'state' => 'fetched',
            'status' => intval($monitor_result['status'] ?? 0),
            'scheduled' => !empty($configured['scheduled']),
            'last_run_at' => sanitize_text_field((string) ($body['last_run_at'] ?? '')),
            'snapshot_count' => intval($body['snapshot_count'] ?? 0),
            'last_snapshot_id' => sanitize_text_field((string) ($last_snapshot['id'] ?? '')),
            'last_snapshot_state' => sanitize_key((string) ($last_snapshot_summary['state'] ?? 'unknown')),
            'last_snapshot_alert_count' => intval($last_snapshot_summary['alert_count'] ?? 0),
            'last_snapshot_eligible_count' => intval($last_snapshot_summary['eligible_count'] ?? 0),
            'last_changes_new_alert_count' => intval($last_changes['new_alert_count'] ?? 0),
            'last_changes_resolved_alert_count' => intval($last_changes['resolved_alert_count'] ?? 0),
            'last_notifications_state' => sanitize_key((string) ($last_notifications['state'] ?? '')),
            'last_notifications_reason' => sanitize_text_field((string) ($last_notifications['reason'] ?? '')),
            'last_notifications_result_count' => count($last_notification_results),
            'last_notifications_failed_result_count' => $failed_notification_results,
            'alert_delivery_sink_count' => intval($alert_delivery['sink_count'] ?? 0),
            'alert_delivery_min_severity' => sanitize_key((string) ($alert_delivery['min_severity'] ?? 'warning')),
            'alert_delivery_webhook_configured' => !empty($alert_delivery['webhook_configured']),
            'alert_delivery_homeassistant_configured' => !empty($alert_delivery['homeassistant_configured']),
            'alert_delivery_email_configured' => !empty($alert_delivery['email_configured']),
            'alert_delivery_email_recipient_count' => intval($alert_delivery['email_recipient_count'] ?? 0),
        ];
    }

    private static function run_registry_public_check() {
        $record = self::suggested_registry_record();
        $record_hash = self::registry_record_hash($record);
        $claim_hash = self::registry_claim_hash();
        $errors = [];
        $endpoints = [];

        $manifest = self::fetch_public_json(home_url('/.well-known/agentcart.json'));
        $endpoints['manifest'] = self::public_check_endpoint_summary(home_url('/.well-known/agentcart.json'), $manifest);
        if (!$manifest['ok']) {
            $errors[] = 'manifest_fetch_failed';
        } else {
            $manifest_body = $manifest['body'];
            $discovery = is_array($manifest_body['discovery'] ?? null) ? $manifest_body['discovery'] : [];
            if (($discovery['registry_claim_hash'] ?? '') !== $claim_hash) {
                $errors[] = 'manifest_registry_claim_hash_mismatch';
            }
            if (($discovery['registry_record_hash'] ?? '') !== $record_hash) {
                $errors[] = 'manifest_registry_record_hash_mismatch';
            }
        }

        $proof = self::fetch_public_json(self::registry_proof_url());
        $endpoints['proof'] = self::public_check_endpoint_summary(self::registry_proof_url(), $proof);
        if (!$proof['ok']) {
            $errors[] = 'domain_proof_fetch_failed';
        } else {
            $proof_body = $proof['body'];
            foreach ([
                'record_hash' => $record_hash,
                'registry_claim_hash' => $claim_hash,
                'manifest_url' => home_url('/.well-known/agentcart.json'),
                'revocation_url' => self::registry_revocation_url(),
            ] as $field => $expected) {
                if ((string) ($proof_body[$field] ?? '') !== (string) $expected) {
                    $errors[] = 'domain_proof_' . $field . '_mismatch';
                }
            }
        }

        $revocations = self::fetch_public_json(self::registry_revocation_url());
        $endpoints['revocations'] = self::public_check_endpoint_summary(self::registry_revocation_url(), $revocations);
        if (!$revocations['ok']) {
            $errors[] = 'revocation_fetch_failed';
        } else {
            $revocation_body = $revocations['body'];
            if (($revocation_body['type'] ?? '') !== 'agentcart-registry-revocations') {
                $errors[] = 'revocation_type_mismatch';
            }
            if (self::revocation_document_revokes_record_hash($revocation_body, $record_hash)) {
                $errors[] = 'current_record_revoked';
            }
        }

        $bundle = self::fetch_public_json(self::registry_bundle_url());
        $endpoints['bundle'] = self::public_check_endpoint_summary(self::registry_bundle_url(), $bundle);
        if (!$bundle['ok']) {
            $errors[] = 'registry_bundle_fetch_failed';
        } else {
            $bundle_body = $bundle['body'];
            if (($bundle_body['record_hash'] ?? '') !== $record_hash) {
                $errors[] = 'registry_bundle_record_hash_mismatch';
            }
            $bundle_record = is_array($bundle_body['registry_record'] ?? null) ? $bundle_body['registry_record'] : [];
            if ($bundle_record && self::registry_record_hash($bundle_record) !== $record_hash) {
                $errors[] = 'registry_bundle_record_rehash_mismatch';
            }
        }

        return [
            'schema' => 'agentcart.shopbridge.registry_public_check.v1',
            'state' => empty($errors) ? 'verified' : 'failed',
            'checked_at' => self::current_registry_timestamp(),
            'record_hash' => $record_hash,
            'registry_claim_hash' => $claim_hash,
            'errors' => array_values(array_unique($errors)),
            'endpoints' => $endpoints,
        ];
    }

    private static function fetch_public_json($url) {
        $response = wp_remote_get(esc_url_raw((string) $url), [
            'timeout' => 8,
            'redirection' => 2,
            'headers' => [
                'Accept' => 'application/json',
            ],
        ]);
        if (is_wp_error($response)) {
            return [
                'ok' => false,
                'status' => 0,
                'error' => $response->get_error_message(),
                'body' => null,
            ];
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded)) {
            return [
                'ok' => false,
                'status' => $status,
                'error' => 'invalid_json_or_http_status',
                'body' => null,
            ];
        }
        return [
            'ok' => true,
            'status' => $status,
            'error' => '',
            'body' => $decoded,
        ];
    }

    private static function public_check_endpoint_summary($url, $result) {
        return [
            'url' => (string) $url,
            'ok' => !empty($result['ok']),
            'status' => intval($result['status'] ?? 0),
            'error' => sanitize_text_field((string) ($result['error'] ?? '')),
        ];
    }

    private static function revocation_document_revokes_record_hash($document, $record_hash) {
        if (!is_array($document)) {
            return false;
        }
        $candidates = [$document];
        foreach (['revocations', 'revoked_records', 'records'] as $key) {
            if (isset($document[$key]) && is_array($document[$key])) {
                foreach ($document[$key] as $entry) {
                    if (is_array($entry)) {
                        $candidates[] = $entry;
                    }
                }
            }
        }
        foreach ($candidates as $candidate) {
            $revoked = !empty($candidate['revoked']) || !empty($candidate['revoked_at']);
            if (!$revoked) {
                continue;
            }
            $supplied_hash = (string) ($candidate['record_hash'] ?? $candidate['registry_record_hash'] ?? '');
            if ($supplied_hash !== '' && hash_equals((string) $record_hash, $supplied_hash)) {
                return true;
            }
        }
        return false;
    }

    private static function registry_updated_at() {
        self::ensure_registry_claim_version();
        if (defined('AGENTCART_REGISTRY_UPDATED_AT')) {
            $value = self::sanitize_registry_updated_at_value((string) AGENTCART_REGISTRY_UPDATED_AT);
            if ($value !== '') {
                return $value;
            }
        }
        $value = self::sanitize_registry_updated_at_value((string) get_option(self::REGISTRY_UPDATED_AT_OPTION, ''));
        if ($value !== '') {
            return $value;
        }
        $now = self::current_registry_timestamp();
        update_option(self::REGISTRY_UPDATED_AT_OPTION, $now, false);
        return $now;
    }

    private static function sanitize_registry_updated_at_value($value) {
        $value = trim((string) $value);
        if ($value === '') {
            return '';
        }
        return preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/', $value) ? $value : '';
    }

    private static function current_registry_timestamp() {
        return gmdate('Y-m-d\TH:i:s\Z');
    }

    private static function ensure_registry_claim_version() {
        $fingerprint = self::registry_claim_fingerprint();
        $stored_fingerprint = (string) get_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION, '');
        $stored_updated_at = self::sanitize_registry_updated_at_value((string) get_option(self::REGISTRY_UPDATED_AT_OPTION, ''));
        if ($fingerprint !== $stored_fingerprint || $stored_updated_at === '') {
            update_option(self::REGISTRY_CLAIM_FINGERPRINT_OPTION, $fingerprint, false);
            update_option(self::REGISTRY_UPDATED_AT_OPTION, self::current_registry_timestamp(), false);
        }
    }

    private static function registry_proof_url() {
        return home_url('/.well-known/agentcart-registry-proof.json');
    }

    private static function registry_revocation_url() {
        return home_url('/.well-known/agentcart-registry-revocations.json');
    }

    private static function registry_bundle_url() {
        return home_url('/.well-known/agentcart-registry-bundle.json');
    }

    private static function public_origin_host() {
        $host = wp_parse_url(home_url('/'), PHP_URL_HOST);
        return is_string($host) ? strtolower($host) : '';
    }

    private static function registry_domain_proof_configured() {
        return self::merchant()['id'] !== '' && self::registry_record_hash_value() !== '' && self::registry_updated_at() !== '';
    }

    private static function registry_domain_proof() {
        $record = self::suggested_registry_record();
        return [
            'type' => 'https-well-known',
            'configured' => self::registry_domain_proof_configured(),
            'merchant_id' => self::merchant()['id'],
            'domain' => self::public_origin_host(),
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'registry_claim_hash' => self::registry_claim_hash(),
            'payment_network' => self::tempo_network(),
            'payment_recipient' => self::tempo_recipient(),
            'updated_at' => self::registry_updated_at(),
            'revocation_url' => self::registry_revocation_url(),
            'record_hash' => self::registry_record_hash($record),
        ];
    }

    private static function registry_revocations() {
        $revocations = self::registry_revoked_records();
        return [
            'type' => 'agentcart-registry-revocations',
            'merchant_id' => self::merchant()['id'],
            'domain' => self::public_origin_host(),
            'updated_at' => self::registry_updated_at(),
            'revocations' => $revocations,
        ];
    }

    private static function registry_revoked_records() {
        $stored = get_option(self::REGISTRY_REVOKED_RECORDS_OPTION, []);
        $stored = is_array($stored) ? $stored : [];
        $records = [];
        foreach ($stored as $entry) {
            if (!is_array($entry)) {
                continue;
            }
            $record_hash = sanitize_text_field((string) ($entry['record_hash'] ?? ''));
            if ($record_hash === '') {
                continue;
            }
            $records[] = [
                'record_hash' => $record_hash,
                'revoked' => true,
                'revoked_at' => self::sanitize_registry_updated_at_value((string) ($entry['revoked_at'] ?? '')) ?: self::current_registry_timestamp(),
                'reason' => sanitize_text_field((string) ($entry['reason'] ?? 'merchant_admin_revoke')),
            ];
        }
        return $records;
    }

    private static function record_registry_revocation($record_hash, $reason) {
        $record_hash = sanitize_text_field((string) $record_hash);
        if ($record_hash === '') {
            return;
        }
        $records = self::registry_revoked_records();
        $updated = false;
        foreach ($records as &$entry) {
            if (hash_equals((string) ($entry['record_hash'] ?? ''), $record_hash)) {
                $entry['revoked_at'] = self::current_registry_timestamp();
                $entry['reason'] = sanitize_text_field((string) $reason);
                $updated = true;
                break;
            }
        }
        unset($entry);
        if (!$updated) {
            $records[] = [
                'record_hash' => $record_hash,
                'revoked' => true,
                'revoked_at' => self::current_registry_timestamp(),
                'reason' => sanitize_text_field((string) $reason),
            ];
        }
        update_option(self::REGISTRY_REVOKED_RECORDS_OPTION, $records, false);
        delete_option(self::REGISTRY_PUBLIC_CHECK_OPTION);
    }

    private static function registry_onboarding_bundle() {
        $record = self::suggested_registry_record();
        return [
            'type' => 'agentcart-registry-onboarding-bundle',
            'version' => '0.1',
            'merchant_id' => self::merchant()['id'],
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'registry_record' => $record,
            'record_hash' => self::registry_record_hash($record),
            'merchant_action' => 'none',
            'proof_document_expected' => self::registry_domain_proof(),
            'revocation_document' => self::registry_revocations(),
            'registry_feed' => [
                'entries' => [$record],
            ],
            'next_steps' => [
                'Add registry_record to a public AgentCart registry, append-only feed, or onchain registry adapter.',
                'Keep this bundle URL available so registries can refresh the auto-managed claim.',
                'Only expose the catalog and quote endpoints after products, shipping, and payment verifier settings are ready.',
                'Run registry verification after HTTPS is configured for the shop domain.',
            ],
        ];
    }

    private static function registry_claim() {
        return [
            'merchant_id' => self::merchant()['id'],
            'name' => self::merchant()['name'],
            'domain' => self::public_origin_host(),
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'endpoints' => [
                'catalog' => rest_url(self::API_NAMESPACE . '/catalog'),
                'quote' => rest_url(self::API_NAMESPACE . '/quote'),
                'orders' => rest_url(self::API_NAMESPACE . '/orders'),
                'order_status' => rest_url(self::API_NAMESPACE . '/orders/{id}/status'),
                'refunds' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
            ],
            'supported_protocols' => self::registry_supported_protocols(),
            'protocol_profile_ids' => self::protocol_profile_ids(),
            'payment_network' => self::tempo_network(),
            'payment_recipient' => self::tempo_recipient(),
            'stripe_profile_id' => self::stripe_profile_id(),
            'ship_to_countries' => self::shipping_countries(),
            'returns_url' => self::returns_url(),
            'merchant_policy_hash' => self::canonical_json_hash(self::merchant_policy()),
            'proof_url' => self::registry_proof_url(),
            'revocation_url' => self::registry_revocation_url(),
        ];
    }

    private static function registry_supported_protocols() {
        $protocols = ['agentcart-shopbridge'];
        if (self::tempo_recipient() !== '') {
            $protocols[] = 'tempo-mpp';
        }
        if (self::stripe_profile_id() !== '' && self::payment_verifier_url() !== '') {
            $protocols[] = 'stripe-card-mpp';
        }
        if (self::x402_profile_configured()) {
            $protocols[] = 'x402-compatible';
        }
        if (self::signed_request_profile_configured()) {
            $protocols[] = 'signed-http-ready';
        }
        return $protocols;
    }

    private static function legacy_protocols() {
        return [
            [
                'id' => 'agentcart-shopbridge',
                'version' => '0.1',
                'role' => 'merchant_catalog_quote_checkout',
            ],
            [
                'id' => 'tempo-mpp',
                'network' => self::tempo_network(),
                'recipient' => self::tempo_recipient(),
                'verifier_configured' => self::payment_verifier_url() !== '',
            ],
            [
                'id' => 'stripe-card-mpp',
                'network_id' => self::stripe_profile_id(),
                'verifier_configured' => self::payment_verifier_url() !== '',
                'configured' => self::stripe_payment_profile_configured(),
            ],
        ];
    }

    private static function protocol_profiles() {
        $profiles = [
            [
                'id' => 'agentcart-shopbridge',
                'type' => 'commerce',
                'version' => '0.1',
                'status' => 'available',
                'role' => 'merchant_catalog_quote_checkout',
                'adapter' => 'agentcart.shopbridge.v1',
                'endpoints' => [
                    'manifest' => home_url('/.well-known/agentcart.json'),
                    'capability' => rest_url(self::API_NAMESPACE . '/capability'),
                    'catalog' => rest_url(self::API_NAMESPACE . '/catalog'),
                    'quote' => rest_url(self::API_NAMESPACE . '/quote'),
                    'orders' => rest_url(self::API_NAMESPACE . '/orders'),
                    'order_status' => rest_url(self::API_NAMESPACE . '/orders/{id}/status'),
                    'refunds' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
                    'cancellations' => rest_url(self::API_NAMESPACE . '/orders/{id}/cancellations'),
                ],
                'features' => [
                    'catalog',
                    'final_quote',
                    'quote_bound_checkout',
                    'woocommerce_order_status',
                    'refund_request',
                    'cancellation_request',
                    'merchant_audit_metadata',
                ],
            ],
        ];

        if (self::merchant_registry_profile_configured()) {
            $profiles[] = [
                'id' => 'erc8004-ready',
                'type' => 'registry',
                'standard' => 'ERC-8004',
                'status' => 'ready_for_mapping',
                'scope' => 'merchant_identity_registration',
                'domain_proof' => [
                    'type' => 'https-well-known',
                    'proof_url' => self::registry_proof_url(),
                    'revocation_url' => self::registry_revocation_url(),
                ],
                'note' => 'Publishes a domain-bound merchant registry record that can be mapped by an ERC-8004/onchain registry adapter. The plugin does not submit an onchain registration.',
            ];
        }

        if (self::tempo_payment_profile_configured()) {
            $profiles[] = [
                'id' => 'mpp-http-auth',
                'type' => 'payment',
                'standard' => 'MPP',
                'status' => 'available',
                'auth_scheme' => 'Payment',
                'payment_protocol_id' => 'tempo-mpp',
                'network' => self::tempo_network(),
                'recipient' => self::tempo_recipient(),
                'settlement_asset' => self::tempo_settlement_asset(),
                'verifier_required' => true,
            ];
        }

        if (self::stripe_payment_profile_configured()) {
            $profiles[] = [
                'id' => 'stripe-card-mpp',
                'type' => 'payment',
                'standard' => 'Stripe Machine Payments',
                'status' => 'available',
                'payment_protocol_id' => 'stripe-card-mpp',
                'network_id' => self::stripe_profile_id(),
                'verifier_required' => true,
            ];
        }

        if (self::x402_profile_configured()) {
            $profiles[] = [
                'id' => 'x402-compatible',
                'type' => 'payment',
                'standard' => 'x402',
                'status' => 'available',
                'x402_version' => 2,
                'scheme' => 'exact',
                'network' => self::x402_network(),
                'asset' => self::x402_asset(),
                'asset_symbol' => self::x402_asset_symbol(),
                'asset_decimals' => self::x402_asset_decimals(),
                'asset_currency' => self::x402_asset_currency(),
                'pay_to' => self::x402_pay_to(),
                'facilitator_url' => self::x402_facilitator_url(),
                'payment_required_header' => 'PAYMENT-REQUIRED',
                'payment_signature_header' => 'PAYMENT-SIGNATURE',
                'payment_response_header' => 'PAYMENT-RESPONSE',
                'verifier_required' => true,
            ];
        }

        if (self::signed_request_profile_configured()) {
            $profiles[] = [
                'id' => 'signed-http-ready',
                'type' => 'auth',
                'standard' => 'ERC-8128-style signed HTTP',
                'status' => 'available',
                'signature_scheme' => self::signed_request_preferred_signature_scheme(),
                'signature_schemes' => self::signed_request_supported_signature_schemes(),
                'mode' => self::signed_request_mode(),
                'required_for' => self::signed_request_required_buckets(),
                'max_ttl_seconds' => self::SIGNED_REQUEST_MAX_TTL_SECONDS,
                'clock_skew_seconds' => self::SIGNED_REQUEST_CLOCK_SKEW_SECONDS,
                'replay_protection' => 'nonce_transient',
                'active_signer' => self::signed_request_active_key_id(),
                'accepted_signers' => self::signed_request_public_key_summaries(),
                'key_rotation' => [
                    'supported' => !defined('AGENTCART_SIGNED_REQUEST_SECRET'),
                    'retirement_seconds' => self::SIGNED_REQUEST_KEY_RETIREMENT_SECONDS,
                ],
                'canonical' => [
                    'version' => 'agentcart-signed-request-v1',
                    'fields' => ['method', 'path', 'content_digest', 'nonce', 'expires_at', 'signer'],
                    'separator' => '\\n',
                ],
                'headers' => [
                    'signed_method' => 'X-AgentCart-Signed-Method',
                    'signed_path' => 'X-AgentCart-Signed-Path',
                    'content_digest' => 'X-AgentCart-Content-Digest',
                    'nonce' => 'X-AgentCart-Nonce',
                    'expires_at' => 'X-AgentCart-Expires-At',
                    'signer' => 'X-AgentCart-Signer',
                    'signature_alg' => 'X-AgentCart-Signature-Alg',
                    'signature' => 'X-AgentCart-Signature',
                ],
            ];
        }

        return $profiles;
    }

    private static function protocol_profile_ids() {
        return array_values(array_map(function ($profile) {
            return (string) ($profile['id'] ?? '');
        }, self::protocol_profiles()));
    }

    private static function payment_protocol_profile_ids() {
        return array_values(array_filter(self::protocol_profile_ids(), function ($id) {
            return in_array($id, ['mpp-http-auth', 'stripe-card-mpp', 'x402-compatible'], true);
        }));
    }

    private static function tempo_payment_profile_configured() {
        return self::tempo_recipient() !== '' && self::payment_verifier_url() !== '';
    }

    private static function stripe_payment_profile_configured() {
        return self::stripe_profile_id() !== '' && self::payment_verifier_url() !== '';
    }

    private static function x402_profile_configured() {
        return self::x402_quote_configured_for_currency(get_woocommerce_currency());
    }

    private static function x402_quote_configured_for_currency($currency) {
        return self::payment_verifier_url() !== ''
            && self::x402_network() !== ''
            && self::x402_asset() !== ''
            && self::x402_pay_to() !== ''
            && strtoupper((string) $currency) === strtoupper(self::x402_asset_currency());
    }

    private static function merchant_registry_profile_configured() {
        return self::stable_merchant_id_configured() && self::public_origin_is_https();
    }

    private static function registry_claim_fingerprint() {
        return self::canonical_json_hash(self::registry_claim());
    }

    private static function registry_claim_hash() {
        return self::canonical_json_hash(self::registry_claim());
    }

    private static function suggested_registry_record() {
        $claim = self::registry_claim();
        return array_merge($claim, [
            'registry_claim_hash_alg' => 'sha-256',
            'registry_claim_hash' => self::registry_claim_hash(),
            'updated_at' => self::registry_updated_at(),
            'revoked_at' => null,
            'signature_alg' => 'https-domain-proof',
            'signature' => '',
            'proof' => [
                'type' => 'https-well-known',
                'url' => self::registry_proof_url(),
            ],
        ]);
    }

    private static function registry_record_hash($record) {
        return self::canonical_json_hash(self::registry_signature_payload($record));
    }

    private static function registry_signature_payload($record) {
        $payload = [];
        foreach ($record as $key => $value) {
            if (in_array($key, ['signature', 'verification', 'manifest', 'manifest_snapshot', 'proof_snapshot', 'revocation_snapshot'], true)) {
                continue;
            }
            $payload[$key] = $value;
        }
        return $payload;
    }

    private static function canonical_json_hash($value) {
        return hash('sha256', self::canonical_json($value));
    }

    private static function canonical_json($value) {
        return wp_json_encode(self::canonicalize_json_value($value), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }

    private static function canonicalize_json_value($value) {
        if (!is_array($value)) {
            return $value;
        }
        $keys = array_keys($value);
        $is_list = $keys === array_keys($keys);
        if ($is_list) {
            return array_map([__CLASS__, 'canonicalize_json_value'], $value);
        }
        ksort($value, SORT_STRING);
        foreach ($value as $key => $item) {
            $value[$key] = self::canonicalize_json_value($item);
        }
        return $value;
    }

    private static function admin_status_badge($ok, $ok_label, $missing_label = 'Missing') {
        $color = $ok ? '#008a20' : '#996800';
        $background = $ok ? '#edfaef' : '#fff8e5';
        $label = $ok ? $ok_label : $missing_label;
        return '<span style="display:inline-block;padding:3px 8px;border-radius:999px;background:' . esc_attr($background) . ';color:' . esc_attr($color) . ';font-weight:600;">' . esc_html($label) . '</span>';
    }

    private static function render_admin_status_badge($ok, $ok_label, $missing_label = 'Missing') {
        echo self::admin_status_badge($ok, $ok_label, $missing_label); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- admin_status_badge() escapes label and style values before returning fixed badge markup.
    }

    private static function render_setup_wizard_panel($setup_guide, $readiness) {
        $steps = is_array($setup_guide['steps'] ?? null) ? $setup_guide['steps'] : [];
        $complete_count = 0;
        foreach ($steps as $step) {
            if (($step['state'] ?? '') === 'complete') {
                $complete_count++;
            }
        }
        $total_count = max(1, count($steps));
        $progress = min(100, max(0, intval(round(($complete_count / $total_count) * 100))));
        $next_step = is_array($setup_guide['next_step'] ?? null) ? $setup_guide['next_step'] : [];
        $manifest_url = home_url('/.well-known/agentcart.json');
        $catalog_url = rest_url(self::API_NAMESPACE . '/catalog');
        $quote_url = rest_url(self::API_NAMESPACE . '/quote');
        $registry_bundle_url = self::registry_bundle_url();
        $signed_request_ready = self::signed_request_profile_configured();
        $sandbox_quote_check = self::sandbox_quote_check_result();
        $sandbox_checkout_test = self::sandbox_checkout_test_result();
        ?>
        <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
            <tbody>
                <tr>
                    <th scope="row">Quick start progress</th>
                    <td>
                        <div style="max-width: 360px; height: 10px; background: #f0f0f1; border-radius: 999px; overflow: hidden;">
                            <div style="width: <?php echo esc_attr((string) $progress); ?>%; height: 10px; background: #2271b1;"></div>
                        </div>
                        <p class="description"><?php echo esc_html($complete_count . ' of ' . count($steps) . ' setup steps complete.'); ?></p>
                    </td>
                    <td><?php self::render_admin_status_badge(!empty($readiness['demo_ready']), 'Demo ready', 'Needs setup'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Next action</th>
                    <td>
                        <strong><?php echo esc_html($next_step['label'] ?? 'Ready for testing'); ?></strong>
                        <?php if (!empty($next_step['summary'])) : ?>
                            <p class="description"><?php echo esc_html($next_step['summary']); ?></p>
                        <?php endif; ?>
                    </td>
                    <td>
                        <a class="button" href="<?php echo esc_attr($next_step['settings_anchor'] ?? '#agentcart-readiness'); ?>"><?php echo esc_html($next_step['action_label'] ?? 'Review readiness'); ?></a>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Sandbox access defaults</th>
                    <td>
                        Creates missing local secrets, enables optional signed-request compatibility,
                        and refreshes registry metadata. This does not expose products or configure
                        payment recipients.
                    </td>
                    <td>
                        <form method="post">
                            <?php wp_nonce_field('agentcart_shopbridge_setup_action'); ?>
                            <input type="hidden" name="agentcart_setup_action" value="prepare_sandbox_secrets" />
                            <?php submit_button('Prepare sandbox access', 'secondary', 'submit', false); ?>
                        </form>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Buyer-agent endpoints</th>
                    <td>
                        <code><?php echo esc_html($manifest_url); ?></code><br>
                        <code><?php echo esc_html($catalog_url); ?></code><br>
                        <code><?php echo esc_html($quote_url); ?></code><br>
                        <code><?php echo esc_html($registry_bundle_url); ?></code>
                    </td>
                    <td><?php self::render_admin_status_badge($signed_request_ready, 'Signed profile ready', 'Unsigned allowed'); ?></td>
                </tr>
                <tr>
                    <th scope="row">Sandbox quote check</th>
                    <td>
                        Runs the same WooCommerce-backed quote path used by buyer agents against
                        one currently AgentCart-enabled product. The test deletes its quote
                        transient and releases its own soft stock hold after the check.
                    </td>
                    <td>
                        <form method="post">
                            <?php wp_nonce_field('agentcart_shopbridge_setup_action'); ?>
                            <input type="hidden" name="agentcart_setup_action" value="run_sandbox_quote_check" />
                            <?php submit_button('Run quote check', 'secondary', 'submit', false); ?>
                        </form>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Guided checkout test</th>
                    <td>
                        Runs quote, payment verification, WooCommerce paid-order creation, and
                        immediate test-order cancellation. If a payment verifier URL is configured,
                        the sandbox receipt is sent through that verifier; otherwise the trusted
                        merchant-token demo path is used.
                    </td>
                    <td>
                        <form method="post">
                            <?php wp_nonce_field('agentcart_shopbridge_setup_action'); ?>
                            <input type="hidden" name="agentcart_setup_action" value="run_sandbox_checkout_test" />
                            <?php submit_button('Run checkout test', 'secondary', 'submit', false); ?>
                        </form>
                    </td>
                </tr>
                <?php if (!empty($sandbox_quote_check)) : ?>
                    <tr>
                        <th scope="row">Last quote check</th>
                        <td colspan="2">
                            <?php self::render_admin_status_badge(($sandbox_quote_check['state'] ?? '') === 'passed', 'Passed', 'Failed'); ?>
                            <p class="description">
                                <?php echo esc_html((string) ($sandbox_quote_check['checked_at'] ?? '')); ?>
                                <?php if (($sandbox_quote_check['state'] ?? '') === 'passed') : ?>
                                    &middot;
                                    <?php echo esc_html((string) ($sandbox_quote_check['product_title'] ?? 'AgentCart product')); ?>
                                    to <?php echo esc_html((string) (($sandbox_quote_check['ship_to']['country'] ?? '') ?: 'configured country')); ?>
                                    &middot;
                                    total <?php echo esc_html(self::admin_money_from_cents(intval($sandbox_quote_check['total_cents'] ?? 0), (string) ($sandbox_quote_check['currency'] ?? get_woocommerce_currency()))); ?>
                                    &middot;
                                    shipping <?php echo esc_html(self::admin_money_from_cents(intval($sandbox_quote_check['shipping_cents'] ?? 0), (string) ($sandbox_quote_check['currency'] ?? get_woocommerce_currency()))); ?>
                                    &middot;
                                    VAT lines <?php echo esc_html((string) intval($sandbox_quote_check['vat_line_count'] ?? 0)); ?>
                                <?php else : ?>
                                    &middot;
                                    <?php echo esc_html((string) ($sandbox_quote_check['message'] ?? 'Quote check failed.')); ?>
                                <?php endif; ?>
                            </p>
                            <?php if (!empty($sandbox_quote_check['quote_hash'])) : ?>
                                <p class="description">Quote hash: <code><?php echo esc_html((string) $sandbox_quote_check['quote_hash']); ?></code></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_quote_check['cleanup'])) : ?>
                                <p class="description"><?php echo esc_html((string) $sandbox_quote_check['cleanup']); ?></p>
                            <?php endif; ?>
                        </td>
                    </tr>
                <?php endif; ?>
                <?php if (!empty($sandbox_checkout_test)) : ?>
                    <tr>
                        <th scope="row">Last checkout test</th>
                        <td colspan="2">
                            <?php self::render_admin_status_badge(($sandbox_checkout_test['state'] ?? '') === 'passed', 'Passed', 'Failed'); ?>
                            <p class="description">
                                <?php echo esc_html((string) ($sandbox_checkout_test['checked_at'] ?? '')); ?>
                                <?php if (($sandbox_checkout_test['state'] ?? '') === 'passed') : ?>
                                    &middot;
                                    order <?php echo esc_html((string) ($sandbox_checkout_test['order_number'] ?? $sandbox_checkout_test['order_id'] ?? '')); ?>
                                    &middot;
                                    status <?php echo esc_html((string) ($sandbox_checkout_test['order_status'] ?? '')); ?>
                                    &middot;
                                    <?php echo esc_html((string) ($sandbox_checkout_test['product_title'] ?? 'AgentCart product')); ?>
                                    &middot;
                                    total <?php echo esc_html(self::admin_money_from_cents(intval($sandbox_checkout_test['total_cents'] ?? 0), (string) ($sandbox_checkout_test['currency'] ?? get_woocommerce_currency()))); ?>
                                    &middot;
                                    payment <?php echo esc_html((string) ($sandbox_checkout_test['payment_mode'] ?? 'unknown')); ?>
                                    &middot;
                                    settlement <?php echo !empty($sandbox_checkout_test['real_settlement_verified']) ? esc_html('real verified') : esc_html('sandbox/demo'); ?>
                                <?php else : ?>
                                    &middot;
                                    <?php echo esc_html((string) ($sandbox_checkout_test['message'] ?? 'Checkout test failed.')); ?>
                                <?php endif; ?>
                            </p>
                            <?php if (!empty($sandbox_checkout_test['order_url'])) : ?>
                                <p class="description">Order: <a href="<?php echo esc_url((string) $sandbox_checkout_test['order_url']); ?>"><?php echo esc_html((string) ($sandbox_checkout_test['order_url'])); ?></a></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_checkout_test['quote_hash'])) : ?>
                                <p class="description">Quote hash: <code><?php echo esc_html((string) $sandbox_checkout_test['quote_hash']); ?></code></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_checkout_test['approval_hash'])) : ?>
                                <p class="description">Approval hash: <code><?php echo esc_html((string) $sandbox_checkout_test['approval_hash']); ?></code></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_checkout_test['approval_record_hash'])) : ?>
                                <p class="description">Approval record hash: <code><?php echo esc_html((string) $sandbox_checkout_test['approval_record_hash']); ?></code></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_checkout_test['payment_contract_hash'])) : ?>
                                <p class="description">Payment contract hash: <code><?php echo esc_html((string) $sandbox_checkout_test['payment_contract_hash']); ?></code></p>
                            <?php endif; ?>
                            <?php if (!empty($sandbox_checkout_test['cleanup'])) : ?>
                                <p class="description"><?php echo esc_html((string) $sandbox_checkout_test['cleanup']); ?></p>
                            <?php endif; ?>
                        </td>
                    </tr>
                <?php endif; ?>
            </tbody>
        </table>
        <?php
    }

    private static function sandbox_quote_check_result() {
        $result = get_option(self::SANDBOX_QUOTE_CHECK_OPTION, []);
        return is_array($result) ? $result : [];
    }

    private static function sandbox_checkout_test_result() {
        $result = get_option(self::SANDBOX_CHECKOUT_TEST_OPTION, []);
        return is_array($result) ? $result : [];
    }

    private static function admin_money_from_cents($cents, $currency) {
        return number_format_i18n(max(0, intval($cents)) / 100, 2) . ' ' . strtoupper(sanitize_text_field((string) $currency));
    }

    private static function render_setup_guide($setup_guide) {
        $steps = is_array($setup_guide['steps'] ?? null) ? $setup_guide['steps'] : [];
        ?>
        <table class="widefat striped" style="max-width: 980px;">
            <thead>
                <tr>
                    <th scope="col">Step</th>
                    <th scope="col">Status</th>
                    <th scope="col">Action</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($steps as $step): ?>
                    <tr>
                        <th scope="row"><?php echo esc_html($step['label']); ?></th>
                        <td>
                            <?php self::render_admin_status_badge(($step['state'] ?? '') === 'complete', 'Complete', 'Needs setup'); ?>
                            <p class="description"><?php echo esc_html($step['summary']); ?></p>
                        </td>
                        <td>
                            <a href="<?php echo esc_attr($step['settings_anchor']); ?>"><?php echo esc_html($step['action_label']); ?></a>
                        </td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        <p style="max-width: 760px;">
            Next step: <strong><?php echo esc_html($setup_guide['next_step']['label'] ?? 'Ready for testing'); ?></strong>
            <?php if (!empty($setup_guide['next_step']['summary'])): ?>
                &mdash; <?php echo esc_html($setup_guide['next_step']['summary']); ?>
            <?php endif; ?>
        </p>
        <?php
    }

    private static function setup_guide($readiness = null) {
        $readiness = is_array($readiness) ? $readiness : self::readiness();
        $payment_configured = self::payment_verifier_url() !== ''
            && self::payment_verifier_token() !== ''
            && (self::tempo_recipient() !== '' || self::stripe_profile_id() !== '')
            && self::external_verifier_required_for_checkout();
        $registry_ready = self::public_origin_is_https() && self::registry_domain_proof_configured();
        $steps = [
            self::setup_guide_step(
                'merchant_identity',
                'Merchant identity and support',
                self::support_email() !== '' && self::stable_merchant_id_configured(),
                'Set support contact and a stable merchant id so buyers and registry records can identify the shop.',
                'Review identity settings',
                '#agentcart-settings',
                ['production']
            ),
            self::setup_guide_step(
                'products',
                'Agent-safe products',
                intval($readiness['agentcart_enabled_product_count'] ?? 0) > 0,
                'Choose manual, tag, category, or all-product exposure and keep blocked products out of the catalog.',
                'Review product exposure',
                '#agentcart-product-exposure',
                ['demo', 'production']
            ),
            self::setup_guide_step(
                'tax_shipping',
                'WooCommerce tax and shipping',
                self::tax_and_shipping_configured(),
                'Configure WooCommerce tax rates, shipping methods, and ship-to countries before accepting final quotes.',
                'Review tax and shipping',
                '#agentcart-readiness',
                ['production']
            ),
            self::setup_guide_step(
                'payment_verifier',
                'Quote-bound payment verifier',
                $payment_configured,
                'Configure an external verifier, a Tempo recipient or Stripe/card profile, and external-verifier-only checkout before public agents create paid orders.',
                'Review payment settings',
                '#agentcart-settings',
                ['production']
            ),
            self::setup_guide_step(
                'registry',
                'Verified merchant discovery',
                $registry_ready,
                'Publish the well-known manifest and domain proof over HTTPS, then add the generated record to a registry.',
                'Review registry proof',
                '#agentcart-registry-proof',
                ['production']
            ),
            self::setup_guide_step(
                'sandbox_test',
                'Sandbox quote and order test',
                !empty($readiness['demo_ready']),
                'Run a quote and non-production order test before allowing buyer agents to check out.',
                'Open endpoints',
                '#agentcart-endpoints',
                ['demo', 'production']
            ),
        ];
        $next_step = null;
        foreach ($steps as $step) {
            if ($step['state'] !== 'complete') {
                $next_step = $step;
                break;
            }
        }
        if ($next_step === null) {
            $next_step = [
                'id' => 'ready',
                'label' => !empty($readiness['production_ready']) ? 'Ready for production-shaped testing' : 'Ready for sandbox testing',
                'summary' => !empty($readiness['production_ready'])
                    ? 'Run final sandbox orders and connect the public registry.'
                    : 'Demo prerequisites are complete; production rail, HTTPS, or legal checks may still be missing.',
                'settings_anchor' => '#agentcart-readiness',
            ];
        }
        return [
            'demo_complete' => !empty($readiness['demo_ready']),
            'production_complete' => !empty($readiness['production_ready']),
            'next_step' => $next_step,
            'steps' => $steps,
        ];
    }

    private static function setup_guide_step($id, $label, $complete, $summary, $action_label, $settings_anchor, $required_for) {
        return [
            'id' => $id,
            'label' => $label,
            'state' => $complete ? 'complete' : 'needs_setup',
            'summary' => $summary,
            'action_label' => $action_label,
            'settings_anchor' => $settings_anchor,
            'required_for' => $required_for,
        ];
    }

    private static function readiness() {
        $missing_demo = [];
        if (!self::merchant_token_value()) {
            $missing_demo[] = 'merchant token';
        }
        if (!self::support_email()) {
            $missing_demo[] = 'support email';
        }
        if (!self::shipping_countries()) {
            $missing_demo[] = 'shipping countries';
        }
        $enabled_product_count = self::agentcart_enabled_product_count();
        if ($enabled_product_count <= 0) {
            $missing_demo[] = 'AgentCart-enabled product';
        }

        $missing_production = [];
        if (!self::public_origin_is_https()) {
            $missing_production[] = 'public HTTPS origin';
        }
        if (!self::stable_merchant_id_configured()) {
            $missing_production[] = 'stable merchant id';
        }
        if (!self::payment_verifier_url()) {
            $missing_production[] = 'external payment verifier';
        }
        if (self::payment_verifier_url() && !self::payment_verifier_token()) {
            $missing_production[] = 'payment verifier token';
        }
        if (!self::external_verifier_required_for_checkout()) {
            $missing_production[] = 'external-verifier-only checkout mode';
        }
        if (!self::signed_request_required_for_bucket('checkout')) {
            $missing_production[] = 'signed checkout request gate';
        } elseif (!self::signed_request_active_key()) {
            $missing_production[] = 'active signed request signing key';
        }
        if (self::tempo_recipient() === '' && self::stripe_profile_id() === '') {
            $missing_production[] = 'Tempo recipient or Stripe profile';
        }
        if (!self::support_email()) {
            $missing_production[] = 'support email';
        }
        if (!self::legal_pages_configured()) {
            $missing_production[] = 'terms and returns pages';
        }
        if (!self::tax_and_shipping_configured()) {
            $missing_production[] = 'WooCommerce tax and shipping setup';
        }
        if ($enabled_product_count <= 0) {
            $missing_production[] = 'AgentCart-enabled product';
        }

        return [
            'demo_ready' => empty($missing_demo),
            'production_ready' => empty($missing_production),
            'mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token_demo',
            'checkout_mode' => self::checkout_mode(),
            'external_verifier_required_for_checkout' => self::external_verifier_required_for_checkout(),
            'trusted_token_checkout_enabled' => !self::external_verifier_required_for_checkout(),
            'signed_request_mode' => self::signed_request_mode(),
            'signed_request_configured' => self::signed_request_profile_configured(),
            'signed_request_required_for' => self::signed_request_required_buckets(),
            'signed_request_active_signer' => self::signed_request_active_key_id(),
            'signed_request_active_key_count' => self::signed_request_active_key_count(),
            'signed_request_retiring_key_count' => self::signed_request_retiring_key_count(),
            'agentcart_enabled_product_count' => $enabled_product_count,
            'product_exposure_mode' => self::product_exposure_mode(),
            'product_exposure_tag' => self::product_exposure_mode() === 'tag' ? self::product_exposure_tag() : null,
            'missing_for_demo' => $missing_demo,
            'missing_for_production' => $missing_production,
            'demo_note' => 'Demo readiness means an AgentCart gateway can create quote-bound WooCommerce orders after its own approval and payment proof flow.',
            'production_note' => 'Production readiness requires rail-bound payment/refund verification, legal terms, fulfillment operations, and merchant compliance beyond this plugin status.',
        ];
    }

    private static function public_origin_is_https() {
        return strpos(home_url('/'), 'https://') === 0;
    }

    private static function stable_merchant_id_configured() {
        $merchant_id = self::merchant_id();
        return $merchant_id !== '' && $merchant_id !== 'woocommerce-demo-shop';
    }

    private static function legal_pages_configured() {
        $terms_id = function_exists('wc_get_page_id') ? intval(wc_get_page_id('terms')) : 0;
        $terms_ok = $terms_id > 0 && get_post_status($terms_id) === 'publish';
        $returns_page = get_page_by_path('returns');
        $returns_ok = $returns_page && get_post_status($returns_page) === 'publish';
        return $terms_ok && $returns_ok;
    }

    private static function tax_and_shipping_configured() {
        return self::tax_rates_configured() && count(self::shipping_countries()) > 0 && self::shipping_methods_configured();
    }

    private static function tax_rates_configured() {
        if (!function_exists('wc_tax_enabled') || !wc_tax_enabled() || !class_exists('WC_Tax')) {
            return false;
        }
        if (method_exists('WC_Tax', 'get_rates_for_tax_class')) {
            return count(WC_Tax::get_rates_for_tax_class('')) > 0;
        }
        return count(WC_Tax::get_rates('')) > 0;
    }

    private static function shipping_methods_configured() {
        if (!class_exists('WC_Shipping_Zones')) {
            return false;
        }
        $zones = WC_Shipping_Zones::get_zones();
        $zones[] = ['zone_id' => 0];
        foreach ($zones as $zone_data) {
            $zone = new WC_Shipping_Zone(intval($zone_data['zone_id'] ?? 0));
            foreach ($zone->get_shipping_methods(true) as $method) {
                if ($method && isset($method->enabled) && $method->enabled === 'yes') {
                    return true;
                }
            }
        }
        return false;
    }

    private static function support_diagnostics_bundle() {
        $readiness = self::readiness();
        $payment_verifier_token = self::payment_verifier_token();
        $merchant_token = self::merchant_token_value();
        $registry_connection_token = self::registry_connection_token();
        $support_email = self::support_email();
        $tempo_recipient = self::tempo_recipient();
        $stripe_profile_id = self::stripe_profile_id();

        return [
            'schema' => 'agentcart.shopbridge.support_diagnostics.v1',
            'generated_at' => self::current_registry_timestamp(),
            'redaction' => [
                'secrets_included' => false,
                'request_bodies_included' => false,
                'payment_bodies_included' => false,
                'raw_signatures_included' => false,
                'raw_nonces_included' => false,
                'token_fields' => 'presence_and_hash_only',
            ],
            'plugin' => [
                'name' => 'AgentCart ShopBridge',
                'version' => '0.1.0',
                'wordpress_version' => get_bloginfo('version'),
                'woocommerce_version' => defined('WC_VERSION') ? WC_VERSION : '',
                'php_version' => PHP_VERSION,
                'environment_type' => function_exists('wp_get_environment_type') ? wp_get_environment_type() : '',
                'site_url_hash' => self::support_diagnostics_hash(home_url('/')),
                'public_origin_is_https' => self::public_origin_is_https(),
            ],
            'merchant' => [
                'merchant_id' => self::merchant_id(),
                'stable_merchant_id_configured' => self::stable_merchant_id_configured(),
                'support_email_configured' => $support_email !== '',
                'support_email_hash' => self::support_diagnostics_hash($support_email),
                'terms_url_configured' => self::terms_url() !== '',
                'returns_url_configured' => self::returns_url() !== '',
            ],
            'readiness' => $readiness,
            'setup_guide' => self::support_diagnostics_setup_summary(self::setup_guide($readiness)),
            'endpoints' => [
                'manifest' => home_url('/.well-known/agentcart.json'),
                'registry_proof' => self::registry_proof_url(),
                'registry_revocations' => self::registry_revocation_url(),
                'registry_bundle' => self::registry_bundle_url(),
                'capability' => rest_url(self::API_NAMESPACE . '/capability'),
                'catalog' => rest_url(self::API_NAMESPACE . '/catalog'),
                'quote' => rest_url(self::API_NAMESPACE . '/quote'),
                'orders' => rest_url(self::API_NAMESPACE . '/orders'),
                'support_diagnostics' => rest_url(self::API_NAMESPACE . '/support-diagnostics'),
            ],
            'tokens' => [
                'merchant_token_configured' => $merchant_token !== '',
                'merchant_token_hash' => self::support_diagnostics_hash($merchant_token),
                'payment_verifier_token_configured' => $payment_verifier_token !== '',
                'payment_verifier_token_hash' => self::support_diagnostics_hash($payment_verifier_token),
                'registry_connection_token_configured' => $registry_connection_token !== '',
                'registry_connection_token_hash' => self::support_diagnostics_hash($registry_connection_token),
            ],
            'payment' => [
                'checkout_mode' => self::checkout_mode(),
                'external_verifier_required_for_checkout' => self::external_verifier_required_for_checkout(),
                'payment_verifier_configured' => self::payment_verifier_url() !== '',
                'payment_verifier_host_hash' => self::support_diagnostics_url_host_hash(self::payment_verifier_url()),
                'tempo_network' => self::tempo_network(),
                'tempo_recipient_configured' => $tempo_recipient !== '',
                'tempo_recipient_hash' => self::support_diagnostics_hash($tempo_recipient),
                'stripe_profile_configured' => $stripe_profile_id !== '',
                'stripe_profile_hash' => self::support_diagnostics_hash($stripe_profile_id),
                'x402_configured' => self::x402_profile_configured(),
                'x402_network' => self::x402_network(),
                'x402_asset_symbol' => self::x402_asset_symbol(),
                'x402_asset_currency' => self::x402_asset_currency(),
            ],
            'signed_requests' => [
                'mode' => self::signed_request_mode(),
                'configured' => self::signed_request_profile_configured(),
                'required_for' => self::signed_request_required_buckets(),
                'active_signer' => self::signed_request_active_key_id(),
                'active_key_count' => self::signed_request_active_key_count(),
                'retiring_key_count' => self::signed_request_retiring_key_count(),
                'signature_schemes' => self::signed_request_supported_signature_schemes(),
                'accepted_signers' => self::signed_request_public_key_summaries(),
                'audit_summary' => self::signed_request_audit_summary(),
                'recent_audit_events' => array_slice(array_reverse(self::signed_request_audit_events()), 0, 20),
            ],
            'registry' => [
                'claim_hash' => self::registry_claim_hash(),
                'claim_fingerprint' => self::registry_claim_fingerprint(),
                'record_hash' => self::registry_record_hash_value(),
                'updated_at' => self::registry_updated_at(),
                'domain_proof_configured' => self::registry_domain_proof_configured(),
                'connection_configured' => self::registry_connection_url() !== '',
                'connection_host_hash' => self::support_diagnostics_url_host_hash(self::registry_connection_url()),
                'public_check' => self::support_diagnostics_sanitize(self::registry_public_check_result()),
                'connection_status' => self::support_diagnostics_sanitize(self::registry_connection_status()),
                'health_check' => self::support_diagnostics_sanitize(self::registry_health_check_result()),
            ],
            'catalog' => [
                'product_exposure_mode' => self::product_exposure_mode(),
                'product_exposure_label' => self::product_exposure_mode_label(),
                'product_exposure_tag_hash' => self::support_diagnostics_hash(self::product_exposure_tag()),
                'product_exposure_category_count' => count(self::product_exposure_categories()),
                'blocked_category_count' => count(self::product_blocked_categories()),
                'agentcart_enabled_product_count' => self::agentcart_enabled_product_count(),
                'stock_hold_mode' => self::stock_hold_mode(),
                'stock_hold_minutes' => self::stock_hold_minutes(),
                'snapshot' => self::product_exposure_snapshot_summary(),
                'exposure_preview' => self::support_diagnostics_exposure_preview_summary(self::product_exposure_preview_result()),
            ],
            'sandbox_checks' => [
                'quote' => self::support_diagnostics_check_summary(get_option(self::SANDBOX_QUOTE_CHECK_OPTION, [])),
                'checkout' => self::support_diagnostics_check_summary(get_option(self::SANDBOX_CHECKOUT_TEST_OPTION, [])),
            ],
            'woocommerce' => [
                'currency' => function_exists('get_woocommerce_currency') ? get_woocommerce_currency() : '',
                'base_country' => class_exists('WooCommerce') && WC() && WC()->countries ? WC()->countries->get_base_country() : '',
                'tax_enabled' => function_exists('wc_tax_enabled') ? wc_tax_enabled() : false,
                'tax_rates_configured' => self::tax_rates_configured(),
                'shipping_country_count' => count(self::shipping_countries()),
                'shipping_methods_configured' => self::shipping_methods_configured(),
                'legal_pages_configured' => self::legal_pages_configured(),
            ],
            'recommendations' => self::support_diagnostics_recommendations($readiness),
        ];
    }

    private static function support_diagnostics_setup_summary($guide) {
        $guide = is_array($guide) ? $guide : [];
        $steps = [];
        foreach (($guide['steps'] ?? []) as $step) {
            if (!is_array($step)) {
                continue;
            }
            $steps[] = [
                'id' => (string) ($step['id'] ?? ''),
                'label' => (string) ($step['label'] ?? ''),
                'state' => (string) ($step['state'] ?? ''),
                'required_for' => is_array($step['required_for'] ?? null) ? array_values(array_map('strval', $step['required_for'])) : [],
            ];
        }
        $next_step = is_array($guide['next_step'] ?? null) ? $guide['next_step'] : [];
        return [
            'demo_complete' => !empty($guide['demo_complete']),
            'production_complete' => !empty($guide['production_complete']),
            'next_step' => [
                'id' => (string) ($next_step['id'] ?? ''),
                'label' => (string) ($next_step['label'] ?? ''),
                'settings_anchor' => (string) ($next_step['settings_anchor'] ?? ''),
            ],
            'steps' => $steps,
        ];
    }

    private static function support_diagnostics_exposure_preview_summary($preview) {
        $preview = is_array($preview) ? $preview : [];
        if (!$preview) {
            return [];
        }
        $blocked_reason_counts = [];
        $blocked_products = is_array($preview['blocked_products'] ?? null) ? $preview['blocked_products'] : [];
        foreach ($blocked_products as $product) {
            if (!is_array($product)) {
                continue;
            }
            $reasons = is_array($product['blocked_reasons'] ?? null) ? $product['blocked_reasons'] : [];
            foreach ($reasons as $reason) {
                $reason = sanitize_key((string) $reason);
                if ($reason === '') {
                    continue;
                }
                $blocked_reason_counts[$reason] = intval($blocked_reason_counts[$reason] ?? 0) + 1;
            }
        }
        ksort($blocked_reason_counts);
        return [
            'schema' => (string) ($preview['schema'] ?? ''),
            'state' => (string) ($preview['state'] ?? ''),
            'checked_at' => (string) ($preview['checked_at'] ?? ''),
            'settings_fingerprint' => (string) ($preview['settings_fingerprint'] ?? ''),
            'mode' => (string) ($preview['mode'] ?? ''),
            'published_simple_count' => intval($preview['published_simple_count'] ?? 0),
            'included_count' => intval($preview['included_count'] ?? 0),
            'blocked_count' => intval($preview['blocked_count'] ?? 0),
            'not_matching_count' => intval($preview['not_matching_count'] ?? 0),
            'preview_limit' => intval($preview['preview_limit'] ?? 0),
            'catalog_snapshot' => self::product_exposure_snapshot_summary(is_array($preview['catalog_snapshot'] ?? null) ? $preview['catalog_snapshot'] : null),
            'catalog_diff' => self::support_diagnostics_catalog_diff_summary(is_array($preview['catalog_diff'] ?? null) ? $preview['catalog_diff'] : []),
            'blocked_reason_counts' => $blocked_reason_counts,
        ];
    }

    private static function support_diagnostics_catalog_diff_summary($diff) {
        $diff = is_array($diff) ? $diff : [];
        return [
            'state' => (string) ($diff['state'] ?? ''),
            'baseline_saved_at' => (string) ($diff['baseline_saved_at'] ?? ''),
            'baseline_catalog_hash' => (string) ($diff['baseline_catalog_hash'] ?? ''),
            'current_catalog_hash' => (string) ($diff['current_catalog_hash'] ?? ''),
            'added_count' => intval($diff['added_count'] ?? 0),
            'removed_count' => intval($diff['removed_count'] ?? 0),
            'changed_count' => intval($diff['changed_count'] ?? 0),
            'unchanged_count' => intval($diff['unchanged_count'] ?? 0),
        ];
    }

    private static function support_diagnostics_check_summary($check) {
        $check = is_array($check) ? $check : [];
        if (!$check) {
            return [];
        }
        $summary = [
            'state' => (string) ($check['state'] ?? ''),
            'checked_at' => (string) ($check['checked_at'] ?? ''),
            'message' => self::support_diagnostics_trim_string((string) ($check['message'] ?? '')),
            'error_code' => (string) ($check['error_code'] ?? ''),
            'currency' => (string) ($check['currency'] ?? ''),
            'quote_hash' => (string) ($check['quote_hash'] ?? ''),
            'payment_contract_hash' => (string) ($check['payment_contract_hash'] ?? ''),
            'payment_mode' => (string) ($check['payment_mode'] ?? ''),
            'real_settlement_verified' => !empty($check['real_settlement_verified']),
            'cleanup' => self::support_diagnostics_trim_string((string) ($check['cleanup'] ?? '')),
        ];
        foreach (['subtotal_cents', 'shipping_cents', 'total_cents', 'vat_line_count'] as $key) {
            if (array_key_exists($key, $check)) {
                $summary[$key] = intval($check[$key]);
            }
        }
        if (!empty($check['product_id'])) {
            $summary['product_id_hash'] = self::support_diagnostics_hash((string) $check['product_id']);
        }
        if (!empty($check['order_id'])) {
            $summary['order_id_hash'] = self::support_diagnostics_hash((string) $check['order_id']);
        }
        if (is_array($check['ship_to'] ?? null)) {
            $summary['ship_to_country'] = strtoupper(sanitize_text_field((string) ($check['ship_to']['country'] ?? '')));
        }
        if (is_array($check['error_data'] ?? null)) {
            $summary['error_data'] = self::support_diagnostics_sanitize($check['error_data']);
        }
        return $summary;
    }

    private static function support_diagnostics_recommendations($readiness) {
        $readiness = is_array($readiness) ? $readiness : [];
        $recommendations = [];
        foreach (($readiness['missing_for_demo'] ?? []) as $missing) {
            $recommendations[] = 'Demo setup: configure ' . (string) $missing . '.';
        }
        foreach (($readiness['missing_for_production'] ?? []) as $missing) {
            $recommendations[] = 'Production setup: configure ' . (string) $missing . '.';
        }
        if (self::payment_verifier_url() !== '' && self::payment_verifier_token() === '') {
            $recommendations[] = 'Generate and configure a matching payment verifier token.';
        }
        if (self::registry_connection_url() !== '' && !self::registry_connection_status()) {
            $recommendations[] = 'Submit the registry bundle and run the registry health check.';
        }
        if (!self::product_exposure_preview_result()) {
            $recommendations[] = 'Run Product Exposure preview after changing product exposure settings.';
        }
        return array_values(array_unique($recommendations));
    }

    private static function support_diagnostics_sanitize($value) {
        if (is_array($value)) {
            $sanitized = [];
            foreach ($value as $key => $item) {
                $sanitized_key = is_int($key) ? $key : sanitize_key((string) $key);
                if (!is_int($key) && self::support_diagnostics_key_sensitive((string) $key)) {
                    $sanitized[$sanitized_key] = '[redacted]';
                    continue;
                }
                $sanitized[$sanitized_key] = self::support_diagnostics_sanitize($item);
            }
            return $sanitized;
        }
        if (is_bool($value) || is_int($value) || is_float($value) || $value === null) {
            return $value;
        }
        return self::support_diagnostics_trim_string((string) $value);
    }

    private static function support_diagnostics_key_sensitive($key) {
        $key = strtolower((string) $key);
        if ($key === '') {
            return false;
        }
        $safe_keys = [
            'approval_decision_hash',
            'approval_hash',
            'approval_record_hash',
            'claim_hash',
            'expected_digest_hash',
            'nonce_hash',
            'path_hash',
            'payment_contract_hash',
            'public_key_fingerprint',
            'quote_hash',
            'record_hash',
            'settings_fingerprint',
            'signature_alg',
            'signature_hash',
            'signature_schemes',
            'supplied_digest_hash',
        ];
        if (in_array($key, $safe_keys, true)) {
            return false;
        }
        if (substr($key, -5) === '_hash' || substr($key, -12) === '_fingerprint') {
            return false;
        }
        return (bool) preg_match('/(authorization|body|credential|nonce|password|private_key|public_key|receipt|secret|signature|token)/', $key);
    }

    private static function support_diagnostics_trim_string($value) {
        $value = sanitize_text_field((string) $value);
        if (strlen($value) <= 300) {
            return $value;
        }
        return substr($value, 0, 300) . '...';
    }

    private static function support_diagnostics_hash($value) {
        $value = trim((string) $value);
        return $value === '' ? '' : hash('sha256', $value);
    }

    private static function support_diagnostics_url_host_hash($url) {
        $host = wp_parse_url((string) $url, PHP_URL_HOST);
        $host = strtolower(trim((string) $host));
        return $host === '' ? '' : self::support_diagnostics_hash($host);
    }

    private static function render_text_setting_row($label, $option, $value, $constant, $description) {
        self::render_setting_row('text', $label, $option, $value, $constant, $description);
    }

    private static function render_password_setting_row($label, $option, $value, $constant, $description) {
        self::render_setting_row('password', $label, $option, $value, $constant, $description);
    }

    private static function render_textarea_setting_row($label, $option, $value, $constant, $description) {
        $constant_defined = defined($constant);
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr($option); ?>"><?php echo esc_html($label); ?></label></th>
            <td>
                <textarea
                    id="<?php echo esc_attr($option); ?>"
                    name="<?php echo esc_attr($option); ?>"
                    class="large-text code"
                    rows="6"
                    autocomplete="off"
                    <?php disabled($constant_defined); ?>
                ><?php echo esc_textarea((string) $value); ?></textarea>
                <p class="description">
                    <?php echo esc_html($description); ?>
                    <?php if ($constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code><?php echo esc_html($constant); ?></code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_setting_row($type, $label, $option, $value, $constant, $description) {
        $constant_defined = defined($constant);
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr($option); ?>"><?php echo esc_html($label); ?></label></th>
            <td>
                <input
                    id="<?php echo esc_attr($option); ?>"
                    name="<?php echo esc_attr($option); ?>"
                    type="<?php echo esc_attr($type); ?>"
                    class="regular-text"
                    value="<?php echo esc_attr((string) $value); ?>"
                    autocomplete="off"
                    <?php disabled($constant_defined); ?>
                >
                <?php if ($type === 'password') : ?>
                    <button
                        type="button"
                        class="button"
                        onclick="var input=document.getElementById('<?php echo esc_js($option); ?>'); input.type = input.type === 'password' ? 'text' : 'password'; this.textContent = input.type === 'password' ? 'Show' : 'Hide';"
                    >Show</button>
                <?php endif; ?>
                <p class="description">
                    <?php echo esc_html($description); ?>
                    <?php if ($constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code><?php echo esc_html($constant); ?></code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_checkout_mode_setting_row($checkout_mode) {
        $constant_defined = defined('AGENTCART_CHECKOUT_MODE');
        $modes = [
            'trusted_token_or_verifier' => 'Trusted gateway token or external verifier',
            'external_verifier_only' => 'External verifier only',
        ];
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::CHECKOUT_MODE_OPTION); ?>">Checkout mode</label></th>
            <td>
                <select
                    id="<?php echo esc_attr(self::CHECKOUT_MODE_OPTION); ?>"
                    name="<?php echo esc_attr(self::CHECKOUT_MODE_OPTION); ?>"
                    <?php disabled($constant_defined); ?>
                >
                    <?php foreach ($modes as $value => $label): ?>
                        <option value="<?php echo esc_attr($value); ?>" <?php selected($checkout_mode, $value); ?>><?php echo esc_html($label); ?></option>
                    <?php endforeach; ?>
                </select>
                <p class="description">
                    Use trusted gateway token mode for private demos. Use external verifier only before allowing public buyer agents to create paid WooCommerce orders.
                    <?php if ($constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_CHECKOUT_MODE</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_signed_request_mode_setting_row($signed_request_mode) {
        $constant_defined = defined('AGENTCART_SIGNED_REQUEST_MODE');
        $modes = [
            'off' => 'Off',
            'allow' => 'Allow signed requests',
            'require_checkout' => 'Require for checkout',
            'require_mutations' => 'Require for checkout, refunds, and cancellations',
            'require_all_sensitive' => 'Require for quote, checkout, status, refunds, and cancellations',
        ];
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::SIGNED_REQUEST_MODE_OPTION); ?>">Signed request mode</label></th>
            <td>
                <select
                    id="<?php echo esc_attr(self::SIGNED_REQUEST_MODE_OPTION); ?>"
                    name="<?php echo esc_attr(self::SIGNED_REQUEST_MODE_OPTION); ?>"
                    <?php disabled($constant_defined); ?>
                >
                    <?php foreach ($modes as $value => $label): ?>
                        <option value="<?php echo esc_attr($value); ?>" <?php selected($signed_request_mode, $value); ?>><?php echo esc_html($label); ?></option>
                    <?php endforeach; ?>
                </select>
                <p class="description">
                    Optional request-bound HMAC signatures for quote, checkout, status, refund, and cancellation calls. This is the current ERC-8128-style adapter seam; wallet signatures can replace the HMAC signer later without changing commerce payloads.
                    <?php if ($constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_SIGNED_REQUEST_MODE</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_aftercare_policy_setting_rows($substitution_policy, $cancellation_window_minutes) {
        $substitution_constant_defined = defined('AGENTCART_SUBSTITUTION_POLICY');
        $cancellation_constant_defined = defined('AGENTCART_CANCELLATION_WINDOW_MINUTES');
        $policies = [
            'approval_required' => 'Require buyer approval for substitutions',
            'not_allowed' => 'Do not allow substitutions',
            'merchant_allowed' => 'Merchant may substitute comparable items',
        ];
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::SUBSTITUTION_POLICY_OPTION); ?>">Substitution policy</label></th>
            <td>
                <select
                    id="<?php echo esc_attr(self::SUBSTITUTION_POLICY_OPTION); ?>"
                    name="<?php echo esc_attr(self::SUBSTITUTION_POLICY_OPTION); ?>"
                    <?php disabled($substitution_constant_defined); ?>
                >
                    <?php foreach ($policies as $value => $label): ?>
                        <option value="<?php echo esc_attr($value); ?>" <?php selected($substitution_policy, $value); ?>><?php echo esc_html($label); ?></option>
                    <?php endforeach; ?>
                </select>
                <p class="description">
                    Buyer agents use this store-level default when a product does not carry stricter item-level policy metadata.
                    <?php if ($substitution_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_SUBSTITUTION_POLICY</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::CANCELLATION_WINDOW_MINUTES_OPTION); ?>">Cancellation request window</label></th>
            <td>
                <input
                    id="<?php echo esc_attr(self::CANCELLATION_WINDOW_MINUTES_OPTION); ?>"
                    name="<?php echo esc_attr(self::CANCELLATION_WINDOW_MINUTES_OPTION); ?>"
                    type="number"
                    min="0"
                    max="10080"
                    step="1"
                    value="<?php echo esc_attr((string) $cancellation_window_minutes); ?>"
                    <?php disabled($cancellation_constant_defined); ?>
                >
                <p class="description">
                    Minutes after checkout where buyer agents may surface a cancellation request action. Requests still require merchant review; 0 means no self-service cancellation window is advertised.
                    <?php if ($cancellation_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_CANCELLATION_WINDOW_MINUTES</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_product_exposure_setting_rows($mode, $tag, $categories, $blocked_categories) {
        $mode_constant_defined = defined('AGENTCART_PRODUCT_EXPOSURE_MODE');
        $tag_constant_defined = defined('AGENTCART_PRODUCT_EXPOSURE_TAG');
        $categories_constant_defined = defined('AGENTCART_PRODUCT_EXPOSURE_CATEGORIES');
        $blocked_categories_constant_defined = defined('AGENTCART_PRODUCT_BLOCKED_CATEGORIES');
        $modes = [
            'manual' => 'Manual product checkbox',
            'tag' => 'WooCommerce product tag',
            'category' => 'WooCommerce product categories',
            'all' => 'All published simple products',
        ];
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::PRODUCT_EXPOSURE_MODE_OPTION); ?>">Product exposure mode</label></th>
            <td>
                <select
                    id="<?php echo esc_attr(self::PRODUCT_EXPOSURE_MODE_OPTION); ?>"
                    name="<?php echo esc_attr(self::PRODUCT_EXPOSURE_MODE_OPTION); ?>"
                    <?php disabled($mode_constant_defined); ?>
                >
                    <?php foreach ($modes as $value => $label): ?>
                        <option value="<?php echo esc_attr($value); ?>" <?php selected($mode, $value); ?>><?php echo esc_html($label); ?></option>
                    <?php endforeach; ?>
                </select>
                <p class="description">
                    Manual mode preserves the explicit per-product checkbox. Tag and category modes let merchants use normal WooCommerce taxonomy workflows. All mode is for shops whose entire simple-product catalog is safe for agent checkout.
                    <?php if ($mode_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_PRODUCT_EXPOSURE_MODE</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::PRODUCT_EXPOSURE_TAG_OPTION); ?>">Agent-safe product tag</label></th>
            <td>
                <input
                    id="<?php echo esc_attr(self::PRODUCT_EXPOSURE_TAG_OPTION); ?>"
                    name="<?php echo esc_attr(self::PRODUCT_EXPOSURE_TAG_OPTION); ?>"
                    type="text"
                    class="regular-text"
                    value="<?php echo esc_attr($tag); ?>"
                    <?php disabled($tag_constant_defined); ?>
                >
                <p class="description">
                    Used only in tag mode. Add this WooCommerce product tag to products that should appear in AgentCart catalog and quote endpoints.
                    <?php if ($tag_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_PRODUCT_EXPOSURE_TAG</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::PRODUCT_EXPOSURE_CATEGORIES_OPTION); ?>">Agent-safe product categories</label></th>
            <td>
                <input
                    id="<?php echo esc_attr(self::PRODUCT_EXPOSURE_CATEGORIES_OPTION); ?>"
                    name="<?php echo esc_attr(self::PRODUCT_EXPOSURE_CATEGORIES_OPTION); ?>"
                    type="text"
                    class="regular-text"
                    value="<?php echo esc_attr(implode(',', $categories)); ?>"
                    <?php disabled($categories_constant_defined); ?>
                >
                <p class="description">
                    Used only in category mode. Enter WooCommerce product category slugs, separated by commas.
                    <?php if ($categories_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_PRODUCT_EXPOSURE_CATEGORIES</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::PRODUCT_BLOCKED_CATEGORIES_OPTION); ?>">Blocked product categories</label></th>
            <td>
                <input
                    id="<?php echo esc_attr(self::PRODUCT_BLOCKED_CATEGORIES_OPTION); ?>"
                    name="<?php echo esc_attr(self::PRODUCT_BLOCKED_CATEGORIES_OPTION); ?>"
                    type="text"
                    class="regular-text"
                    value="<?php echo esc_attr(implode(',', $blocked_categories)); ?>"
                    <?php disabled($blocked_categories_constant_defined); ?>
                >
                <p class="description">
                    These WooCommerce category slugs are excluded from catalog, quote, and checkout in every exposure mode.
                    <?php if ($blocked_categories_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_PRODUCT_BLOCKED_CATEGORIES</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    private static function render_product_exposure_preview_panel($preview) {
        $preview = is_array($preview) ? $preview : [];
        if (empty($preview)) {
            ?>
            <p class="description" style="max-width: 760px;">
                Run a preview to see which currently published simple products would enter the AgentCart catalog under this exposure policy.
            </p>
            <?php
            return;
        }
        $state = (string) ($preview['state'] ?? 'not_run');
        $checked_at = (string) ($preview['checked_at'] ?? '');
        $is_current = !empty($preview['settings_fingerprint'])
            && hash_equals((string) $preview['settings_fingerprint'], self::product_exposure_settings_fingerprint());
        $included_products = is_array($preview['included_products'] ?? null) ? $preview['included_products'] : [];
        $blocked_products = is_array($preview['blocked_products'] ?? null) ? $preview['blocked_products'] : [];
        $visible_included = array_slice($included_products, 0, self::PRODUCT_EXPOSURE_PREVIEW_LIMIT);
        $visible_blocked = array_slice($blocked_products, 0, min(50, self::PRODUCT_EXPOSURE_PREVIEW_LIMIT));
        $snapshot = self::product_exposure_snapshot_result();
        $diff = is_array($preview['catalog_diff'] ?? null)
            ? $preview['catalog_diff']
            : self::catalog_snapshot_diff($snapshot, self::product_exposure_snapshot_from_preview($preview));
        $diff_rows = self::catalog_snapshot_diff_rows($diff);
        $visible_diff_rows = array_slice($diff_rows, 0, 25);
        ?>
        <h3>Product Exposure Preview</h3>
        <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
            <tbody>
                <tr>
                    <th scope="row">Last preview</th>
                    <td>
                        <?php self::render_admin_status_badge($state === 'passed', $state === 'passed' ? 'Generated' : 'Failed', 'Failed'); ?>
                        <?php self::render_admin_status_badge($is_current, 'Current settings', 'Settings changed'); ?>
                        <?php if ($checked_at !== '') : ?>
                            <br><span class="description"><?php echo esc_html($checked_at); ?></span>
                        <?php endif; ?>
                        <?php if (!empty($preview['message'])) : ?>
                            <br><span class="description"><?php echo esc_html((string) $preview['message']); ?></span>
                        <?php endif; ?>
                    </td>
                    <td>
                        Mode: <code><?php echo esc_html((string) ($preview['mode_label'] ?? self::product_exposure_mode_label())); ?></code>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Catalog result</th>
                    <td>
                        Included: <strong><?php echo esc_html((string) intval($preview['included_count'] ?? 0)); ?></strong>
                        &middot; blocked: <strong><?php echo esc_html((string) intval($preview['blocked_count'] ?? 0)); ?></strong>
                        &middot; outside policy: <strong><?php echo esc_html((string) intval($preview['not_matching_count'] ?? 0)); ?></strong>
                    </td>
                    <td>
                        Published simple products scanned: <strong><?php echo esc_html((string) intval($preview['published_simple_count'] ?? 0)); ?></strong>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Saved catalog snapshot</th>
                    <td>
                        <?php self::render_admin_status_badge(!empty($snapshot), 'Baseline saved', 'No baseline'); ?>
                        <?php if (!empty($snapshot['saved_at'])) : ?>
                            <br><span class="description"><?php echo esc_html((string) $snapshot['saved_at']); ?></span>
                        <?php else : ?>
                            <br><span class="description">Save a snapshot after reviewing a good catalog. Future previews will show what changed.</span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <?php if (!empty($snapshot)) : ?>
                            Products: <strong><?php echo esc_html((string) intval($snapshot['included_count'] ?? 0)); ?></strong>
                            <br><span class="description">Hash: <code><?php echo esc_html((string) ($snapshot['catalog_hash'] ?? '')); ?></code></span>
                        <?php endif; ?>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Catalog diff</th>
                    <td>
                        <?php self::render_admin_status_badge(($diff['state'] ?? '') === 'unchanged', 'No changes', (($diff['state'] ?? '') === 'no_snapshot' ? 'No baseline' : 'Review changes')); ?>
                        <br>
                        Added: <strong><?php echo esc_html((string) intval($diff['added_count'] ?? 0)); ?></strong>
                        &middot; removed: <strong><?php echo esc_html((string) intval($diff['removed_count'] ?? 0)); ?></strong>
                        &middot; changed: <strong><?php echo esc_html((string) intval($diff['changed_count'] ?? 0)); ?></strong>
                    </td>
                    <td>
                        Unchanged: <strong><?php echo esc_html((string) intval($diff['unchanged_count'] ?? 0)); ?></strong>
                    </td>
                </tr>
            </tbody>
        </table>
        <?php if (!empty($visible_diff_rows)) : ?>
            <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
                <thead>
                    <tr>
                        <th scope="col">Catalog diff</th>
                        <th scope="col">Product</th>
                        <th scope="col">Changed fields</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($visible_diff_rows as $row): ?>
                        <tr>
                            <td><code><?php echo esc_html((string) ($row['change_type'] ?? 'changed')); ?></code></td>
                            <th scope="row">
                                <?php echo esc_html((string) ($row['title'] ?? $row['product_id'] ?? 'Product')); ?>
                                <br><code><?php echo esc_html((string) ($row['product_id'] ?? '')); ?></code>
                            </th>
                            <td><?php echo esc_html(implode(', ', is_array($row['changed_fields'] ?? null) ? $row['changed_fields'] : [])); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <?php if (count($diff_rows) > count($visible_diff_rows)) : ?>
                <p class="description" style="max-width: 760px;">
                    Showing the first <?php echo esc_html((string) count($visible_diff_rows)); ?> changed products from this preview.
                </p>
            <?php endif; ?>
        <?php endif; ?>
        <?php if (!empty($visible_included)) : ?>
            <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
                <thead>
                    <tr>
                        <th scope="col">Included products</th>
                        <th scope="col">Exposure source</th>
                        <th scope="col">Stock</th>
                        <th scope="col">Shipping</th>
                        <th scope="col">Max qty</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($visible_included as $product): ?>
                        <tr>
                            <th scope="row">
                                <?php if (!empty($product['edit_url'])) : ?>
                                    <a href="<?php echo esc_url((string) $product['edit_url']); ?>"><?php echo esc_html((string) ($product['title'] ?? $product['product_id'] ?? 'Product')); ?></a>
                                <?php else : ?>
                                    <?php echo esc_html((string) ($product['title'] ?? $product['product_id'] ?? 'Product')); ?>
                                <?php endif; ?>
                                <br><code><?php echo esc_html((string) ($product['product_id'] ?? '')); ?></code>
                            </th>
                            <td><?php echo esc_html((string) ($product['exposure_source'] ?? '')); ?></td>
                            <td>
                                <?php echo esc_html((string) ($product['stock_status'] ?? 'unknown')); ?>
                                <?php if (isset($product['stock_quantity'])) : ?>
                                    <br><span class="description"><?php echo esc_html((string) intval($product['stock_quantity'])); ?> available</span>
                                <?php endif; ?>
                            </td>
                            <td><?php echo esc_html(implode(', ', is_array($product['shipping_countries'] ?? null) ? $product['shipping_countries'] : [])); ?></td>
                            <td><?php echo esc_html((string) intval($product['max_quantity'] ?? 1)); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <?php if (intval($preview['included_count'] ?? 0) > count($visible_included)) : ?>
                <p class="description" style="max-width: 760px;">
                    Showing the first <?php echo esc_html((string) count($visible_included)); ?> included products. The full catalog endpoint still returns every included product.
                </p>
            <?php endif; ?>
        <?php endif; ?>
        <?php if (!empty($visible_blocked)) : ?>
            <table class="widefat striped" style="max-width: 980px; margin-bottom: 12px;">
                <thead>
                    <tr>
                        <th scope="col">Blocked matching products</th>
                        <th scope="col">Why blocked</th>
                        <th scope="col">Exposure source</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($visible_blocked as $product): ?>
                        <tr>
                            <th scope="row"><?php echo esc_html((string) ($product['title'] ?? $product['product_id'] ?? 'Product')); ?></th>
                            <td><code><?php echo esc_html(implode(', ', is_array($product['blocked_reasons'] ?? null) ? $product['blocked_reasons'] : [])); ?></code></td>
                            <td><?php echo esc_html((string) ($product['exposure_source'] ?? '')); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
        <?php
    }

    private static function render_stock_hold_setting_rows($mode, $minutes) {
        $mode_constant_defined = defined('AGENTCART_STOCK_HOLD_MODE');
        $minutes_constant_defined = defined('AGENTCART_STOCK_HOLD_MINUTES');
        $modes = [
            'soft' => 'Soft quote holds',
            'hard' => 'Hard reservation adapter',
            'none' => 'No quote holds',
        ];
        ?>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::STOCK_HOLD_MODE_OPTION); ?>">Stock hold mode</label></th>
            <td>
                <select
                    id="<?php echo esc_attr(self::STOCK_HOLD_MODE_OPTION); ?>"
                    name="<?php echo esc_attr(self::STOCK_HOLD_MODE_OPTION); ?>"
                    <?php disabled($mode_constant_defined); ?>
                >
                    <?php foreach ($modes as $value => $label): ?>
                        <option value="<?php echo esc_attr($value); ?>" <?php selected($mode, $value); ?>><?php echo esc_html($label); ?></option>
                    <?php endforeach; ?>
                </select>
                <p class="description">
                    Soft holds do not reduce WooCommerce stock. Hard mode requires an inventory adapter for <code>agentcart_shopbridge_reserve_stock</code>, <code>agentcart_shopbridge_confirm_stock_reservation</code>, and <code>agentcart_shopbridge_release_stock_reservation</code>; quotes fail closed if the adapter is missing.
                    <?php if ($mode_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_STOCK_HOLD_MODE</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <tr>
            <th scope="row"><label for="<?php echo esc_attr(self::STOCK_HOLD_MINUTES_OPTION); ?>">Stock hold minutes</label></th>
            <td>
                <input
                    id="<?php echo esc_attr(self::STOCK_HOLD_MINUTES_OPTION); ?>"
                    name="<?php echo esc_attr(self::STOCK_HOLD_MINUTES_OPTION); ?>"
                    type="number"
                    min="1"
                    max="60"
                    step="1"
                    value="<?php echo esc_attr((string) $minutes); ?>"
                    <?php disabled($minutes_constant_defined); ?>
                >
                <p class="description">
                    AgentCart quote holds expire after this many minutes. The quote expiry uses the same value.
                    <?php if ($minutes_constant_defined): ?>
                        <br><strong>Configured in wp-config.php via <code>AGENTCART_STOCK_HOLD_MINUTES</code>.</strong>
                    <?php endif; ?>
                </p>
            </td>
        </tr>
        <?php
    }

    public static function capability($request = null) {
        unset($request);
        return self::capability_document();
    }

    public static function support_diagnostics($request = null) {
        unset($request);
        return self::support_diagnostics_bundle();
    }

    private static function capability_document() {
        return [
            'name' => 'AgentCart ShopBridge for WooCommerce',
            'version' => '0.1.0',
            'merchant' => self::merchant(),
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'readiness' => self::readiness(),
            'setup_guide' => self::setup_guide(),
            'protocols' => self::legacy_protocols(),
            'protocol_profiles' => self::protocol_profiles(),
            'protocol_profile_ids' => self::protocol_profile_ids(),
            'capabilities' => [
                'catalog' => true,
                'quote' => true,
                'server_side_quote_binding' => true,
                'paid_order_creation' => true,
                'idempotent_order_creation' => true,
                'checkout_replay_conflict_detection' => true,
                'external_verifier_only_checkout_mode' => self::external_verifier_required_for_checkout(),
                'merchant_of_record' => true,
                'guest_checkout' => true,
                'shipping_address_on_order' => true,
                'per_product_agentcart_opt_in' => true,
                'tag_based_product_exposure' => true,
                'category_based_product_exposure' => true,
                'all_published_simple_product_exposure' => true,
                'blocked_category_product_exclusion' => true,
                'catalog_diff_preview' => true,
                'catalog_snapshot_baseline' => true,
                'per_product_agentcart_max_quantity' => true,
                'per_product_agentcart_block_override' => true,
                'per_product_shipping_country_overrides' => true,
                'per_product_aftercare_policy_overrides' => true,
                'soft_quote_stock_holds' => self::soft_stock_hold_enabled(),
                'hard_quote_stock_reservation_adapter' => self::hard_stock_reservation_enabled(),
                'structured_restricted_goods_metadata' => true,
                'restricted_goods_blocked_by_default' => true,
                'structured_commerce_policy_metadata' => true,
                'merchant_aftercare_policy_defaults' => true,
                'merchant_substitution_policy' => true,
                'merchant_cancellation_policy' => true,
                'x402_exact_payment_required' => self::x402_profile_configured(),
                'signed_http_requests' => self::signed_request_profile_configured(),
                'signed_request_required_for_checkout' => self::signed_request_required_for_bucket('checkout'),
                'signed_request_nonce_replay_protection' => self::signed_request_profile_configured(),
                'signed_request_key_rotation' => self::signed_request_profile_configured(),
                'signed_request_audit_trail' => true,
                'support_diagnostics_bundle' => true,
                'order_status_token' => true,
                'tracking_metadata_read' => true,
                'carrier_tracking_adapter_contract' => true,
                'aftercare_state_contract' => true,
                'agentcart_order_ip_minimized' => true,
                'endpoint_rate_limits' => true,
                'refund_endpoint' => true,
                'refunds_remain_in_woocommerce_with_external_rail_verification' => true,
                'cancellation_endpoint' => true,
                'cancellations_do_not_execute_refunds' => true,
            ],
            'support' => [
                'diagnostics_endpoint' => rest_url(self::API_NAMESPACE . '/support-diagnostics'),
                'diagnostics_requires_manage_woocommerce' => true,
                'diagnostics_redacted' => true,
            ],
            'rate_limits' => self::public_rate_limits_document(),
            'product_exposure' => [
                'mode' => self::product_exposure_mode(),
                'tag' => self::product_exposure_mode() === 'tag' ? self::product_exposure_tag() : null,
                'categories' => self::product_exposure_mode() === 'category' ? self::product_exposure_categories() : [],
                'blocked_categories' => self::product_blocked_categories(),
                'published_simple_products_exposed' => self::agentcart_enabled_product_count(),
                'manual_meta_key' => self::PRODUCT_ENABLED_META,
                'snapshot' => self::product_exposure_snapshot_summary(),
            ],
            'product_policy' => [
                'max_quantity_default' => 20,
                'max_quantity_meta_key' => self::PRODUCT_MAX_QUANTITY_META,
                'block_override_meta_key' => self::PRODUCT_BLOCKED_META,
                'over_limit_quote_rejected' => true,
                'blocked_products_absent_from_catalog' => true,
                'blocked_categories_absent_from_catalog' => true,
                'restricted_goods_metadata' => true,
                'restricted_goods_require_human_review' => true,
                'restricted_goods_blocked_by_default' => true,
                'restricted_goods_allow_override_meta_key' => self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META,
                'commerce_policy_metadata' => true,
                'aftercare_override_meta_keys' => [
                    'perishable' => self::PRODUCT_PERISHABLE_META,
                    'deposit' => self::PRODUCT_DEPOSIT_META,
                    'final_sale' => self::PRODUCT_FINAL_SALE_META,
                    'substitution_sensitive' => self::PRODUCT_SUBSTITUTION_SENSITIVE_META,
                ],
                'perishable_deposit_final_sale_detection' => true,
                'explicit_perishable_deposit_final_sale_overrides' => true,
                'explicit_substitution_sensitive_override' => true,
                'item_policy_preserved_on_order' => true,
                'product_shipping_country_meta_key' => self::PRODUCT_SHIPPING_COUNTRIES_META,
                'shipping_country_overrides_rechecked_on_order' => true,
                'stock_hold_mode' => self::stock_hold_mode(),
                'stock_hold_minutes' => self::stock_hold_minutes(),
                'soft_stock_holds_accounted_in_quotes' => self::soft_stock_hold_enabled(),
                'soft_stock_holds_accounted_in_checkout' => self::soft_stock_hold_enabled(),
                'hard_stock_reservation_adapter_required' => self::hard_stock_reservation_enabled(),
                'hard_stock_reservation_adapter_available' => self::hard_stock_reservation_adapter_available(),
            ],
            'merchant_policy' => self::merchant_policy(),
            'delivery' => [
                'ship_to_countries' => self::shipping_countries(),
                'shipping_country_names' => self::shipping_country_names(),
                'quote_requires_supported_country' => true,
                'tracking_adapter_contract' => [
                    'sources' => [
                        'woocommerce_shipment_tracking',
                        'aftership_tracking',
                        'parcelpanel_tracking',
                        'generic_order_meta',
                    ],
                    'fields' => [
                        'carrier',
                        'tracking_number',
                        'tracking_url',
                        'tracking_status',
                        'shipped_at',
                        'delivered_at',
                        'last_event_at',
                        'source',
                        'confidence',
                    ],
                    'estimated_delivery_is_not_carrier_tracking' => true,
                ],
            ],
            'endpoints' => [
                'manifest' => home_url('/.well-known/agentcart.json'),
                'registry_proof' => self::registry_proof_url(),
                'registry_revocations' => self::registry_revocation_url(),
                'registry_bundle' => self::registry_bundle_url(),
                'capability' => rest_url(self::API_NAMESPACE . '/capability'),
                'catalog' => rest_url(self::API_NAMESPACE . '/catalog'),
                'product' => rest_url(self::API_NAMESPACE . '/products/{id}'),
                'quote' => rest_url(self::API_NAMESPACE . '/quote'),
                'orders' => rest_url(self::API_NAMESPACE . '/orders'),
                'order_status' => rest_url(self::API_NAMESPACE . '/orders/{id}/status'),
                'refunds' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
                'cancellations' => rest_url(self::API_NAMESPACE . '/orders/{id}/cancellations'),
            ],
            'discovery' => [
                'well_known' => '/.well-known/agentcart.json',
                'registry_proof' => [
                    'signature_alg' => 'https-domain-proof',
                    'url' => self::registry_proof_url(),
                ],
                'revocation_url' => self::registry_revocation_url(),
                'registry_bundle_url' => self::registry_bundle_url(),
                'registry_claim_hash_alg' => 'sha-256',
                'registry_claim_hash' => self::registry_claim_hash(),
                'registry_claim' => self::registry_claim(),
                'registry_record_hash' => self::registry_record_hash_value(),
                'registry_updated_at' => self::registry_updated_at(),
                'registry_ready' => true,
                'registry_public_check' => self::registry_public_check_result(),
                'suggested_registry_record' => self::suggested_registry_record(),
                'registry_onboarding_bundle' => self::registry_onboarding_bundle(),
            ],
            'payment_verification' => [
                'mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'external_verifier_configured' => self::payment_verifier_url() !== '',
                'checkout_mode' => self::checkout_mode(),
                'external_verifier_required_for_checkout' => self::external_verifier_required_for_checkout(),
                'trusted_token_checkout_enabled' => !self::external_verifier_required_for_checkout(),
                'tempo_recipient_configured' => self::tempo_recipient() !== '',
                'tempo_network' => self::tempo_network(),
                'stripe_profile_configured' => self::stripe_profile_id() !== '',
                'x402_configured' => self::x402_profile_configured(),
                'x402_network' => self::x402_network(),
                'x402_asset' => self::x402_asset(),
                'x402_pay_to_configured' => self::x402_pay_to() !== '',
                'signed_request_mode' => self::signed_request_mode(),
                'signed_request_configured' => self::signed_request_profile_configured(),
                'signed_request_required_for' => self::signed_request_required_buckets(),
                'signed_request_active_signer' => self::signed_request_active_key_id(),
                'refunds_use_same_verifier' => true,
            ],
            'refund_policy' => [
                'endpoint' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
                'requires_merchant_token' => true,
                'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
                'production_requires_rail_refund_verification' => true,
                'item_commerce_policy_metadata' => true,
            ],
            'cancellation_policy' => [
                'endpoint' => rest_url(self::API_NAMESPACE . '/orders/{id}/cancellations'),
                'requires_merchant_token' => true,
                'idempotency_required' => true,
                'does_not_execute_refund' => true,
                'rejects_after_fulfillment_tracking' => true,
            ],
        ];
    }

    public static function catalog(WP_REST_Request $request) {
        $search = sanitize_text_field((string) $request->get_param('search'));
        $limit = min(24, max(1, intval($request->get_param('limit') ?: 12)));
        $query = array_merge(self::agentcart_product_query_args(), [
            'limit' => $limit,
            'return' => 'objects',
        ]);
        if ($search !== '') {
            $query['s'] = $search;
        }
        $products = array_values(array_filter(wc_get_products($query), function ($product) {
            return $product instanceof WC_Product && self::is_product_agentcart_enabled($product);
        }));
        return [
            'merchant' => self::merchant(),
            'products' => array_values(array_map([__CLASS__, 'serialize_product'], $products)),
        ];
    }

    public static function product(WP_REST_Request $request) {
        $product = wc_get_product(intval($request['id']));
        if (!$product || $product->get_status() !== 'publish') {
            return new WP_Error('agentcart_not_found', 'Product not found.', ['status' => 404]);
        }
        if (!self::is_product_agentcart_enabled($product)) {
            return new WP_Error('agentcart_product_not_enabled', 'Product is not enabled for AgentCart checkout.', ['status' => 404]);
        }
        return self::serialize_product($product);
    }

    public static function quote(WP_REST_Request $request) {
        $body = $request->get_json_params();
        $items = isset($body['items']) && is_array($body['items']) ? $body['items'] : [];
        if (!$items) {
            return new WP_Error('agentcart_bad_request', 'items are required.', ['status' => 400]);
        }
        $ship_to = self::normalize_address($body['ship_to'] ?? ['country' => WC()->countries->get_base_country() ?: 'DE']);
        $address_error = self::validate_quote_address($ship_to);
        if (is_wp_error($address_error)) {
            return $address_error;
        }
        $shipping_countries = self::shipping_countries();
        if ($shipping_countries && !in_array($ship_to['country'], $shipping_countries, true)) {
            return new WP_Error('agentcart_shipping_country_unsupported', 'Shop does not ship to country: ' . $ship_to['country'], ['status' => 400]);
        }
        $cart = self::prepare_quote_cart($ship_to);
        if (is_wp_error($cart)) {
            return $cart;
        }
        $quote_items = [];
        foreach ($items as $item) {
            $product_id = self::source_product_id($item);
            $quantity = intval($item['quantity'] ?? 1);
            if ($quantity < 1) {
                return new WP_Error('agentcart_quantity_invalid', 'Quantity must be at least 1 for product: ' . $product_id, ['status' => 400]);
            }
            $product = wc_get_product($product_id);
            if (!$product || $product->get_status() !== 'publish') {
                return new WP_Error('agentcart_product_missing', 'Product not found: ' . $product_id, ['status' => 404]);
            }
            if (!self::is_product_agentcart_enabled($product)) {
                return new WP_Error('agentcart_product_not_enabled', 'Product is not enabled for AgentCart checkout: ' . $product_id, ['status' => 403]);
            }
            if (!self::product_ships_to_country($product, $ship_to['country'])) {
                return new WP_Error(
                    'agentcart_product_shipping_country_unsupported',
                    'Product is not available for AgentCart shipping to country: ' . $ship_to['country'],
                    [
                        'status' => 400,
                        'product_id' => 'woo_' . $product_id,
                        'ship_to_country' => $ship_to['country'],
                        'supported_countries' => self::product_shipping_countries($product),
                    ]
                );
            }
            $max_quantity = self::product_max_quantity($product);
            if ($quantity > $max_quantity) {
                return new WP_Error(
                    'agentcart_quantity_limit_exceeded',
                    'Requested quantity exceeds AgentCart maximum for product: ' . $product_id,
                    [
                        'status' => 400,
                        'product_id' => 'woo_' . $product_id,
                        'max_quantity' => $max_quantity,
                    ]
                );
            }
            $stock_check = self::validate_product_stock_for_agentcart($product, $quantity);
            if (is_wp_error($stock_check)) {
                return $stock_check;
            }
            $quote_items[] = [
                'product_id' => $product_id,
                'quantity' => $quantity,
            ];
        }
        foreach ($quote_items as $item) {
            $cart_item_key = $cart->add_to_cart($item['product_id'], $item['quantity']);
            if (!$cart_item_key) {
                $cart->empty_cart();
                return new WP_Error('agentcart_cart_rejected_product', 'WooCommerce cart rejected product: ' . $item['product_id'], ['status' => 409]);
            }
        }
        $cart->calculate_shipping();
        $shipping_selection = self::select_shipping_rates_for_cart($cart);
        if (is_wp_error($shipping_selection)) {
            $cart->empty_cart();
            return $shipping_selection;
        }
        $cart->calculate_shipping();
        $cart->calculate_totals();
        $cart_quote = self::quote_from_cart($cart);
        if (is_wp_error($cart_quote)) {
            return $cart_quote;
        }
        $now = time();
        $quote_ttl_seconds = self::stock_hold_ttl_seconds();
        $quote_id = 'woo_quote_' . wp_generate_uuid4();
        $expires_at = gmdate('c', $now + $quote_ttl_seconds);
        $stock_reservation = self::reserve_stock_for_quote($quote_id, $quote_items, $expires_at);
        if (is_wp_error($stock_reservation)) {
            $cart->empty_cart();
            return $stock_reservation;
        }
        $quote = [
            'id' => $quote_id,
            'merchant' => self::merchant(),
            'merchant_of_record' => self::merchant()['merchant_of_record'],
            'items' => $cart_quote['items'],
            'ship_to' => $ship_to,
            'delivery_requirements' => [
                'ship_to_country' => $ship_to['country'],
                'supported_countries' => $shipping_countries,
            ],
            'subtotal_cents' => $cart_quote['subtotal_cents'],
            'shipping' => $cart_quote['shipping'],
            'vat_lines' => $cart_quote['vat_lines'],
            'total_cents' => $cart_quote['total_cents'],
            'currency' => get_woocommerce_currency(),
            'delivery_estimate' => [
                'min_days' => 2,
                'max_days' => 4,
                'label' => '2-4 business days',
            ],
            'delivery_window' => self::delivery_window(2, 4),
            'stock_reserved_until' => in_array(($stock_reservation['state'] ?? ''), ['soft_reserved', 'hard_reserved'], true) ? $expires_at : null,
            'stock_reservation' => $stock_reservation,
            'expires_at' => $expires_at,
            'terms_url' => self::terms_url(),
            'returns_url' => self::returns_url(),
            'merchant_policy' => self::merchant_policy(),
        ];
        $quote['quote_hash'] = self::quote_hash($quote);
        $quote['payment_requirements'] = self::payment_requirements($quote);
        $quote['refund_policy'] = self::quote_refund_policy();
        set_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id, $quote, $quote_ttl_seconds);
        $cart->empty_cart();
        return $quote;
    }

    public static function create_order(WP_REST_Request $request) {
        $body = $request->get_json_params();
        $body = is_array($body) ? $body : [];
        $receipt = isset($body['payment_receipt']) && is_array($body['payment_receipt']) ? $body['payment_receipt'] : [];
        $approval_metadata = self::checkout_approval_metadata($body);
        $agentcart_order_id = sanitize_text_field((string) ($body['agentcart_order_id'] ?? ''));
        $idempotency_key = self::checkout_idempotency_key($body, $request);
        if (is_wp_error($idempotency_key)) {
            return $idempotency_key;
        }
        if ($agentcart_order_id === '' && $idempotency_key !== '') {
            $agentcart_order_id = $idempotency_key;
        }
        if ($idempotency_key === '' && $agentcart_order_id !== '') {
            $idempotency_key = $agentcart_order_id;
        }
        if ($idempotency_key === '') {
            return new WP_Error('agentcart_idempotency_key_required', 'agentcart_order_id, idempotency_key, or Idempotency-Key header is required.', ['status' => 400]);
        }

        $existing_order = self::find_existing_checkout_order($agentcart_order_id, $idempotency_key);
        if ($existing_order) {
            $replay_error = self::validate_existing_order_replay($existing_order, $body, $receipt, $agentcart_order_id, $idempotency_key);
            if (is_wp_error($replay_error)) {
                return $replay_error;
            }
            return self::serialize_order_response($existing_order, 'idempotent_replay');
        }

        $lock = self::acquire_checkout_lock($idempotency_key);
        if (is_wp_error($lock)) {
            return $lock;
        }
        try {
            $existing_order = self::find_existing_checkout_order($agentcart_order_id, $idempotency_key);
            if ($existing_order) {
                $replay_error = self::validate_existing_order_replay($existing_order, $body, $receipt, $agentcart_order_id, $idempotency_key);
                if (is_wp_error($replay_error)) {
                    return $replay_error;
                }
                return self::serialize_order_response($existing_order, 'idempotent_replay');
            }

        $merchant_quote_id = self::merchant_quote_id_from_body($body);
        if ($merchant_quote_id === '') {
            return new WP_Error('agentcart_bad_request', 'merchant_quote_id is required.', ['status' => 400]);
        }
        $quote_lock = self::acquire_quote_lock($merchant_quote_id);
        if (is_wp_error($quote_lock)) {
            return $quote_lock;
        }
        try {
        $existing_quote_order = self::find_existing_quote_order($merchant_quote_id);
        if ($existing_quote_order) {
            return new WP_Error('agentcart_quote_already_consumed', 'Merchant quote has already been used for an AgentCart order.', ['status' => 409]);
        }
        $quote = get_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id);
        if (!is_array($quote)) {
            return self::quote_recovery_error('agentcart_quote_expired', 'Merchant quote is unknown or expired.', null, $merchant_quote_id, 'quote_unknown_or_expired');
        }
        $receipt = self::payment_receipt_from_checkout_request($body, $request, $quote);
        if (empty($receipt['id'])) {
            $x402_response = self::x402_payment_required_response($quote, 'payment_receipt.id or PAYMENT-SIGNATURE header is required.');
            if ($x402_response !== null) {
                return $x402_response;
            }
            return new WP_Error('agentcart_bad_request', 'payment_receipt.id is required.', ['status' => 400]);
        }
        if (strtotime((string) ($quote['expires_at'] ?? '')) < time()) {
            delete_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id);
            self::release_stock_hold($merchant_quote_id);
            return self::quote_recovery_error('agentcart_quote_expired', 'Merchant quote has expired.', $quote, $merchant_quote_id, 'quote_expired');
        }
        $expected_quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $supplied_quote_hash = sanitize_text_field((string) ($body['quote_hash'] ?? ($body['quote']['quote_hash'] ?? '')));
        if ($supplied_quote_hash !== '' && !hash_equals($expected_quote_hash, $supplied_quote_hash)) {
            return new WP_Error('agentcart_quote_mismatch', 'quote_hash does not match the stored merchant quote.', ['status' => 409]);
        }
        if ($supplied_quote_hash === '' && !self::has_valid_merchant_token($request)) {
            return new WP_Error('agentcart_quote_hash_required', 'quote_hash is required for public checkout.', ['status' => 400]);
        }

        $validated_items = [];
        $quote_ship_to = self::normalize_address($quote['ship_to'] ?? ['country' => '']);
        foreach ($quote['items'] as $item) {
            $product_id = self::source_product_id($item);
            $quantity = intval($item['quantity'] ?? 1);
            if ($quantity < 1) {
                return new WP_Error('agentcart_quantity_invalid', 'Quote quantity is invalid for product: ' . $product_id, ['status' => 409]);
            }
            $product = wc_get_product($product_id);
            if (!$product || $product->get_status() !== 'publish') {
                return new WP_Error('agentcart_product_missing', 'Product not found: ' . $product_id, ['status' => 404]);
            }
            if (!self::is_product_agentcart_enabled($product)) {
                return new WP_Error('agentcart_product_not_enabled', 'Product is no longer enabled for AgentCart checkout: ' . $product_id, ['status' => 403]);
            }
            if (!self::product_ships_to_country($product, $quote_ship_to['country'] ?? '')) {
                return new WP_Error(
                    'agentcart_product_shipping_country_unsupported',
                    'Product is no longer available for AgentCart shipping to country: ' . ($quote_ship_to['country'] ?? ''),
                    [
                        'status' => 409,
                        'product_id' => 'woo_' . $product_id,
                        'ship_to_country' => $quote_ship_to['country'] ?? '',
                        'supported_countries' => self::product_shipping_countries($product),
                    ]
                );
            }
            $max_quantity = self::product_max_quantity($product);
            if ($quantity > $max_quantity) {
                return new WP_Error(
                    'agentcart_quantity_limit_exceeded',
                    'Quote quantity now exceeds AgentCart maximum for product: ' . $product_id,
                    [
                        'status' => 409,
                        'product_id' => 'woo_' . $product_id,
                        'max_quantity' => $max_quantity,
                    ]
                );
            }
            $stock_check = self::validate_product_stock_for_agentcart($product, $quantity, $merchant_quote_id);
            if (is_wp_error($stock_check)) {
                return $stock_check;
            }
            $validated_items[] = [$product, $item, $quantity];
        }

        $quote_drift = self::validate_live_quote_totals_for_checkout($quote, $merchant_quote_id, $validated_items);
        if (is_wp_error($quote_drift)) {
            return $quote_drift;
        }

        $payment_verification = self::verify_payment_receipt($quote, $receipt, $body, $request);
        if (is_wp_error($payment_verification)) {
            return $payment_verification;
        }

        $stock_reservation_confirmation = self::confirm_stock_reservation_for_order($merchant_quote_id, $quote, $receipt, $body);
        if (is_wp_error($stock_reservation_confirmation)) {
            return $stock_reservation_confirmation;
        }

        $order = wc_create_order([
            'created_via' => 'agentcart-shopbridge',
            'status' => 'processing',
        ]);
        if (is_wp_error($order)) {
            self::release_stock_hold($merchant_quote_id, 'order_creation_failed');
            return $order;
        }
        foreach ($validated_items as $validated_item) {
            [$product, $quote_item, $quantity] = $validated_item;
            $item_id = $order->add_product($product, $quantity);
            $order_item = $order->get_item($item_id);
            if ($order_item) {
                $line_total = intval($quote_item['line_total_cents'] ?? 0) / 100;
                $order_item->set_subtotal($line_total);
                $order_item->set_total($line_total);
                $order_item->save();
            }
        }
        $shipping = isset($quote['shipping']) && is_array($quote['shipping']) ? $quote['shipping'] : [];
        $shipping_cents = intval($shipping['amount_cents'] ?? 0);
        if ($shipping_cents > 0) {
            $shipping_item = new WC_Order_Item_Shipping();
            $shipping_item->set_method_title(sanitize_text_field((string) ($shipping['method'] ?? 'AgentCart standard shipping')));
            $shipping_item->set_method_id('agentcart_standard');
            $shipping_item->set_total($shipping_cents / 100);
            $order->add_item($shipping_item);
        }
        $ship_to = self::normalize_address($quote['ship_to'] ?? $body['ship_to'] ?? ['country' => 'DE']);
        $bill_to = self::normalize_address($body['bill_to'] ?? $ship_to);
        $status_token = wp_generate_password(40, false, false);
        $order->set_address($ship_to, 'shipping');
        $order->set_address($bill_to, 'billing');
        self::minimize_order_network_metadata($order);
        $payment_rail = self::payment_rail_from_receipt($receipt, $body);
        if (is_array($payment_verification) && !empty($payment_verification['rail'])) {
            $payment_rail = self::normalize_payment_rail((string) $payment_verification['rail']);
        }
        $order->set_payment_method(self::woo_payment_method_for_rail($payment_rail));
        $order->set_payment_method_title(self::payment_method_title_for_rail($payment_rail));
        $order->set_transaction_id(sanitize_text_field((string) $receipt['id']));
        $order->update_meta_data('_agentcart_order_id', $agentcart_order_id);
        $order->update_meta_data(self::IDEMPOTENCY_KEY_META, $idempotency_key);
        $order->update_meta_data('_agentcart_quote_id', sanitize_text_field((string) ($body['agentcart_quote_id'] ?? '')));
        $order->update_meta_data('_agentcart_merchant_quote_id', $merchant_quote_id);
        $order->update_meta_data('_agentcart_payment_receipt_id', sanitize_text_field((string) $receipt['id']));
        $order->update_meta_data('_agentcart_payment_rail', $payment_rail);
        $order->update_meta_data('_agentcart_reason', sanitize_text_field((string) ($body['reason'] ?? '')));
        $order->update_meta_data('_agentcart_quote_hash', $expected_quote_hash);
        if ($approval_metadata['approval_id'] !== '') {
            $order->update_meta_data('_agentcart_approval_id', $approval_metadata['approval_id']);
        }
        if ($approval_metadata['approval_hash'] !== '') {
            $order->update_meta_data('_agentcart_approval_hash', $approval_metadata['approval_hash']);
        }
        if ($approval_metadata['approval_record_hash'] !== '') {
            $order->update_meta_data('_agentcart_approval_record_hash', $approval_metadata['approval_record_hash']);
        }
        if ($approval_metadata['approval_decision_hash'] !== '') {
            $order->update_meta_data('_agentcart_approval_decision_hash', $approval_metadata['approval_decision_hash']);
        }
        $order->update_meta_data(self::ORDER_ITEMS_META, wp_json_encode($quote['items'] ?? []));
        $order->update_meta_data(self::ORDER_MERCHANT_POLICY_META, wp_json_encode($quote['merchant_policy'] ?? self::merchant_policy()));
        $order->update_meta_data('_agentcart_payment_verification', wp_json_encode($payment_verification));
        $order->update_meta_data('_agentcart_stock_reservation', wp_json_encode($quote['stock_reservation'] ?? null));
        $order->update_meta_data('_agentcart_stock_reservation_confirmation', wp_json_encode($stock_reservation_confirmation));
        if (!empty($payment_verification['transaction_reference'])) {
            $order->update_meta_data('_agentcart_payment_transaction_reference', sanitize_text_field((string) $payment_verification['transaction_reference']));
        }
        $order->update_meta_data('_agentcart_delivery_window', wp_json_encode($quote['delivery_window'] ?? null));
        $order->update_meta_data(self::STATUS_TOKEN_META, $status_token);
        $order->calculate_totals();
        $order->payment_complete(sanitize_text_field((string) $receipt['id']));
        $order->set_date_paid(time());
        $order->add_order_note('AgentCart created this order after quote-bound payment verification: ' . sanitize_text_field((string) ($payment_verification['mode'] ?? 'unknown')) . '.');
        $order->save();
        delete_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id);
        self::release_stock_hold($merchant_quote_id, 'confirmed');
        return self::serialize_order_response($order, 'created', $payment_verification);
        } finally {
            self::release_quote_lock($merchant_quote_id);
        }
        } finally {
            self::release_checkout_lock($idempotency_key);
        }
    }

    public static function order_status(WP_REST_Request $request) {
        $order = wc_get_order(intval($request['id']));
        if (!$order) {
            return new WP_Error('agentcart_not_found', 'Order not found.', ['status' => 404]);
        }
        return self::serialize_order_status($order);
    }

    public static function create_refund(WP_REST_Request $request) {
        $order = wc_get_order(intval($request['id']));
        if (!$order) {
            return new WP_Error('agentcart_not_found', 'Order not found.', ['status' => 404]);
        }
        if ((string) $order->get_meta('_agentcart_order_id', true) === '') {
            return new WP_Error('agentcart_not_agentcart_order', 'Only AgentCart-created orders can use the AgentCart refund endpoint.', ['status' => 409]);
        }

        $body = $request->get_json_params();
        $body = is_array($body) ? $body : [];
        $refund_idempotency_key = self::refund_idempotency_key($body, $request);
        if (is_wp_error($refund_idempotency_key)) {
            return $refund_idempotency_key;
        }
        if ($refund_idempotency_key === '') {
            return new WP_Error('agentcart_refund_idempotency_key_required', 'refund_idempotency_key, idempotency_key, requested_reference, or Idempotency-Key header is required for refunds.', ['status' => 400]);
        }
        $amount_cents = isset($body['amount_cents']) ? intval($body['amount_cents']) : 0;
        $reason = sanitize_text_field((string) ($body['reason'] ?? 'AgentCart merchant-approved refund'));
        $rail = sanitize_key((string) ($body['rail'] ?? self::payment_rail_from_order($order)));
        $requested_reference = sanitize_text_field((string) ($body['requested_reference'] ?? ''));

        $existing_refund = self::find_existing_refund($order, $refund_idempotency_key);
        if ($existing_refund) {
            $replay_error = self::validate_existing_refund_replay($order, $existing_refund, $amount_cents, $rail, $refund_idempotency_key, $requested_reference);
            if (is_wp_error($replay_error)) {
                return $replay_error;
            }
            return self::serialize_refund_response($order, $existing_refund, 'refund_idempotent_replay');
        }

        $lock = self::acquire_refund_lock($refund_idempotency_key);
        if (is_wp_error($lock)) {
            return $lock;
        }
        try {
            $existing_refund = self::find_existing_refund($order, $refund_idempotency_key);
            if ($existing_refund) {
                $replay_error = self::validate_existing_refund_replay($order, $existing_refund, $amount_cents, $rail, $refund_idempotency_key, $requested_reference);
                if (is_wp_error($replay_error)) {
                    return $replay_error;
                }
                return self::serialize_refund_response($order, $existing_refund, 'refund_idempotent_replay');
            }

            $remaining_cents = self::cents((float) $order->get_remaining_refund_amount());
            if ($remaining_cents <= 0) {
                return new WP_Error('agentcart_refund_unavailable', 'This order has no refundable amount remaining.', ['status' => 409]);
            }
            if (!isset($body['amount_cents'])) {
                $amount_cents = $remaining_cents;
            }
            if ($amount_cents <= 0) {
                return new WP_Error('agentcart_refund_amount_invalid', 'Refund amount must be greater than zero.', ['status' => 400]);
            }
            if ($amount_cents > $remaining_cents) {
                return new WP_Error('agentcart_refund_amount_exceeds_remaining', 'Refund amount exceeds the remaining refundable amount.', ['status' => 409]);
            }

            $refund_verification = self::verify_refund_request($order, $amount_cents, $reason, $rail, $body);
            if (is_wp_error($refund_verification)) {
                return $refund_verification;
            }
            $refund_reference = sanitize_text_field((string) ($refund_verification['refund_reference'] ?? ''));
            if ($refund_reference !== '' && self::refund_reference_used($order, $refund_reference)) {
                return new WP_Error('agentcart_refund_replay', 'Refund reference has already been used for this order.', ['status' => 409]);
            }

            $refund = wc_create_refund([
                'amount' => $amount_cents / 100,
                'reason' => $reason,
                'order_id' => $order->get_id(),
                'refund_payment' => false,
                'restock_items' => false,
            ]);
            if (is_wp_error($refund)) {
                return $refund;
            }

            $refund->update_meta_data('_agentcart_refund_verification', wp_json_encode($refund_verification));
            $refund->update_meta_data('_agentcart_refund_rail', $rail);
            $refund->update_meta_data(self::REFUND_IDEMPOTENCY_KEY_META, $refund_idempotency_key);
            if ($refund_reference !== '') {
                $refund->update_meta_data(self::REFUND_REFERENCE_META, $refund_reference);
            }
            if ($requested_reference !== '') {
                $refund->update_meta_data(self::REFUND_REQUESTED_REFERENCE_META, $requested_reference);
            }
            $refund->save();

            $refunds = self::stored_refund_events($order);
            $refunds[] = [
                'refund_id' => (string) $refund->get_id(),
                'amount_cents' => $amount_cents,
                'currency' => $order->get_currency(),
                'rail' => $rail,
                'reason' => $reason,
                'idempotency_key' => $refund_idempotency_key,
                'requested_reference' => $requested_reference,
                'refund_reference' => $refund_reference,
                'verification' => $refund_verification,
                'created_at' => gmdate('c'),
            ];
            $order->update_meta_data('_agentcart_refunds', wp_json_encode($refunds));
            $order->add_order_note(
                'AgentCart refund recorded: '
                . wc_price($amount_cents / 100, ['currency' => $order->get_currency()])
                . ' via ' . $rail . '. Rail verification state: '
                . sanitize_text_field((string) ($refund_verification['state'] ?? 'unknown')) . '.'
            );
            $order->save();

            return self::serialize_refund_response($order, $refund, 'refund_recorded');
        } finally {
            self::release_refund_lock($refund_idempotency_key);
        }
    }

    public static function create_cancellation(WP_REST_Request $request) {
        $order = wc_get_order(intval($request['id']));
        if (!$order) {
            return new WP_Error('agentcart_not_found', 'Order not found.', ['status' => 404]);
        }
        if ((string) $order->get_meta('_agentcart_order_id', true) === '') {
            return new WP_Error('agentcart_not_agentcart_order', 'Only AgentCart-created orders can use the AgentCart cancellation endpoint.', ['status' => 409]);
        }

        $body = $request->get_json_params();
        $body = is_array($body) ? $body : [];
        $cancellation_idempotency_key = self::cancellation_idempotency_key($body, $request);
        if (is_wp_error($cancellation_idempotency_key)) {
            return $cancellation_idempotency_key;
        }
        if ($cancellation_idempotency_key === '') {
            return new WP_Error('agentcart_cancellation_idempotency_key_required', 'cancellation_idempotency_key, idempotency_key, requested_reference, or Idempotency-Key header is required for cancellations.', ['status' => 400]);
        }

        $reason = sanitize_text_field((string) ($body['reason'] ?? 'AgentCart merchant-approved cancellation'));
        $requested_reference = sanitize_text_field((string) ($body['requested_reference'] ?? ''));

        $existing_event = self::find_existing_cancellation_event($order, $cancellation_idempotency_key);
        if ($existing_event) {
            $replay_error = self::validate_existing_cancellation_replay($existing_event, $reason, $requested_reference);
            if (is_wp_error($replay_error)) {
                return $replay_error;
            }
            return self::serialize_cancellation_response($order, $existing_event, 'cancellation_idempotent_replay');
        }

        $lock = self::acquire_cancellation_lock($cancellation_idempotency_key);
        if (is_wp_error($lock)) {
            return $lock;
        }
        try {
            $existing_event = self::find_existing_cancellation_event($order, $cancellation_idempotency_key);
            if ($existing_event) {
                $replay_error = self::validate_existing_cancellation_replay($existing_event, $reason, $requested_reference);
                if (is_wp_error($replay_error)) {
                    return $replay_error;
                }
                return self::serialize_cancellation_response($order, $existing_event, 'cancellation_idempotent_replay');
            }

            $eligibility = self::cancellation_eligibility($order);
            if (empty($eligibility['eligible'])) {
                return new WP_Error(
                    'agentcart_cancellation_unavailable',
                    'This order is not eligible for AgentCart cancellation.',
                    ['status' => 409, 'eligibility' => $eligibility]
                );
            }

            $previous_status = $order->get_status();
            $refund_required = $order->is_paid() && self::cents((float) $order->get_remaining_refund_amount()) > 0;
            $event = [
                'id' => 'cancel_' . wp_generate_uuid4(),
                'state' => $refund_required ? 'order_cancelled_refund_required' : 'order_cancelled',
                'order_id' => (string) $order->get_id(),
                'previous_status' => $previous_status,
                'new_status' => 'cancelled',
                'reason' => $reason,
                'idempotency_key' => $cancellation_idempotency_key,
                'requested_reference' => $requested_reference,
                'refund_required' => $refund_required,
                'real_refund_verified' => false,
                'refund_endpoint' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/refunds'),
                'note' => $refund_required
                    ? 'WooCommerce order was cancelled. A separate rail-verified refund is still required before claiming money moved back.'
                    : 'WooCommerce order was cancelled. No refundable paid amount remains.',
                'created_at' => gmdate('c'),
            ];

            $events = self::stored_cancellation_events($order);
            $events[] = $event;
            $order->update_meta_data(self::CANCELLATION_EVENTS_META, wp_json_encode($events));
            $order->add_order_note(
                'AgentCart cancellation approved: ' . $reason
                . '. Refund required: ' . ($refund_required ? 'yes' : 'no')
                . '. No payment refund was executed by this cancellation endpoint.'
            );
            try {
                $order->update_status('cancelled', 'AgentCart changed order status to cancelled after merchant-approved cancellation.', true);
            } catch (Exception $exception) {
                return new WP_Error('agentcart_cancellation_failed', $exception->getMessage(), ['status' => 500]);
            }
            $order->save();

            return self::serialize_cancellation_response($order, $event, 'cancellation_recorded');
        } finally {
            self::release_cancellation_lock($cancellation_idempotency_key);
        }
    }

    private static function serialize_order_response(WC_Order $order, $state = 'created', $payment_verification = null) {
        $status_token = (string) $order->get_meta(self::STATUS_TOKEN_META, true);
        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'state' => $state,
            'id' => (string) $order->get_id(),
            'number' => $order->get_order_number(),
            'status' => $order->get_status(),
            'payment_method' => $order->get_payment_method(),
            'url' => admin_url('post.php?post=' . $order->get_id() . '&action=edit'),
            'status_url' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/status'),
            'status_token' => $status_token,
            'fulfillment' => self::serialize_fulfillment($order),
            'approval_id' => (string) $order->get_meta('_agentcart_approval_id', true),
            'approval_hash' => (string) $order->get_meta('_agentcart_approval_hash', true),
            'approval_record_hash' => (string) $order->get_meta('_agentcart_approval_record_hash', true),
            'approval_decision_hash' => (string) $order->get_meta('_agentcart_approval_decision_hash', true),
            'aftercare_state' => self::aftercare_state($order),
            'payment_verification' => is_array($payment_verification) ? $payment_verification : self::stored_payment_verification($order),
            'items' => self::serialize_order_items($order),
            'merchant_policy' => self::stored_merchant_policy($order),
            'cancellation_policy' => self::cancellation_policy($order),
            'refund_policy' => self::refund_policy($order),
            'cancellations' => self::serialize_cancellations($order),
            'refunds' => self::serialize_refunds($order),
        ];
    }

    private static function serialize_refund_response(WC_Order $order, $refund, $state = 'refund_recorded') {
        $verification = self::stored_refund_verification($refund);
        $response_state = $state;
        if ($state === 'refund_recorded' && is_array($verification) && !empty($verification['real_refund_verified'])) {
            $response_state = 'rail_refund_verified';
        }
        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'state' => $response_state,
            'order_id' => (string) $order->get_id(),
            'refund_id' => (string) $refund->get_id(),
            'amount_cents' => self::cents((float) $refund->get_amount()),
            'currency' => $order->get_currency(),
            'rail' => (string) $refund->get_meta('_agentcart_refund_rail', true),
            'idempotency_key' => (string) $refund->get_meta(self::REFUND_IDEMPOTENCY_KEY_META, true),
            'requested_reference' => (string) $refund->get_meta(self::REFUND_REQUESTED_REFERENCE_META, true),
            'refund_reference' => (string) $refund->get_meta(self::REFUND_REFERENCE_META, true),
            'real_refund_verified' => is_array($verification) && !empty($verification['real_refund_verified']),
            'provider' => is_array($verification) ? (string) ($verification['provider'] ?? '') : '',
            'verification_state' => is_array($verification) ? (string) ($verification['state'] ?? '') : '',
            'verification_mode' => is_array($verification) ? (string) ($verification['mode'] ?? '') : '',
            'replay_reference' => is_array($verification) ? (string) ($verification['replay_reference'] ?? '') : '',
            'replay_request_hash' => is_array($verification) ? (string) ($verification['replay_request_hash'] ?? '') : '',
            'refund_status' => is_array($verification) ? (string) ($verification['refund_status'] ?? '') : '',
            'verification' => $verification,
            'aftercare_state' => self::aftercare_state($order),
            'refunds' => self::serialize_refunds($order),
        ];
    }

    private static function serialize_cancellation_response(WC_Order $order, $event, $state = 'cancellation_recorded') {
        $event = is_array($event) ? $event : [];
        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'state' => $state,
            'order_id' => (string) $order->get_id(),
            'order_status' => $order->get_status(),
            'cancellation' => $event,
            'refund_required' => !empty($event['refund_required']),
            'real_refund_verified' => false,
            'aftercare_state' => self::aftercare_state($order),
            'refund_policy' => self::refund_policy($order),
            'cancellation_policy' => self::cancellation_policy($order),
            'cancellations' => self::serialize_cancellations($order),
        ];
    }

    private static function serialize_order_status(WC_Order $order) {
        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'id' => (string) $order->get_id(),
            'number' => $order->get_order_number(),
            'status' => $order->get_status(),
            'created_at' => $order->get_date_created() ? $order->get_date_created()->date('c') : null,
            'payment_status' => $order->is_paid() ? 'paid' : 'unpaid',
            'payment_method' => $order->get_payment_method(),
            'fulfillment' => self::serialize_fulfillment($order),
            'aftercare_state' => self::aftercare_state($order),
            'items' => self::serialize_order_items($order),
            'merchant_policy' => self::stored_merchant_policy($order),
            'cancellation_policy' => self::cancellation_policy($order),
            'refund_policy' => self::refund_policy($order),
            'cancellations' => self::serialize_cancellations($order),
            'refunds' => self::serialize_refunds($order),
            'updated_at' => $order->get_date_modified() ? $order->get_date_modified()->date('c') : null,
        ];
    }

    private static function stored_merchant_policy(WC_Order $order) {
        $raw = $order->get_meta(self::ORDER_MERCHANT_POLICY_META, true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? $decoded : self::merchant_policy();
    }

    private static function serialize_order_items(WC_Order $order) {
        $raw = $order->get_meta(self::ORDER_ITEMS_META, true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        if (is_array($decoded)) {
            return array_values(array_filter($decoded, 'is_array'));
        }
        $items = [];
        foreach ($order->get_items() as $item) {
            $product = method_exists($item, 'get_product') ? $item->get_product() : null;
            $serialized = $product instanceof WC_Product ? self::serialize_product($product) : [];
            $items[] = [
                'product_id' => $serialized['product_id'] ?? '',
                'source_product_id' => $product instanceof WC_Product ? $product->get_id() : 0,
                'sku' => $serialized['sku'] ?? '',
                'title' => method_exists($item, 'get_name') ? wp_strip_all_tags($item->get_name()) : '',
                'quantity' => method_exists($item, 'get_quantity') ? intval($item->get_quantity()) : 1,
                'line_total_cents' => method_exists($item, 'get_total') ? self::cents((float) $item->get_total()) : 0,
                'currency' => $order->get_currency(),
                'category' => $serialized['category'] ?? '',
                'category_slugs' => $serialized['category_slugs'] ?? [],
                'restricted_goods' => $serialized['restricted_goods'] ?? [],
                'commerce_policy' => $serialized['commerce_policy'] ?? null,
                'agentcart_policy' => $serialized['agentcart_policy'] ?? null,
            ];
        }
        return $items;
    }

    private static function minimize_order_network_metadata(WC_Order $order) {
        if (method_exists($order, 'set_customer_ip_address')) {
            $order->set_customer_ip_address('');
        }
        if (method_exists($order, 'set_customer_user_agent')) {
            $order->set_customer_user_agent('');
        }
        $order->update_meta_data('_agentcart_privacy_note', 'AgentCart order creation clears WooCommerce customer IP and user-agent fields.');
    }

    private static function checkout_approval_metadata($body) {
        $body = is_array($body) ? $body : [];
        $approval = isset($body['approval']) && is_array($body['approval']) ? $body['approval'] : [];
        $approval_record = isset($body['approval_record']) && is_array($body['approval_record']) ? $body['approval_record'] : [];
        $approval_decision_record = isset($body['approval_decision_record']) && is_array($body['approval_decision_record']) ? $body['approval_decision_record'] : [];
        return [
            'approval_id' => sanitize_text_field((string) ($body['approval_id'] ?? $approval['approval_id'] ?? $approval['id'] ?? $approval_record['approval_id'] ?? '')),
            'approval_hash' => sanitize_text_field((string) ($body['approval_hash'] ?? $approval['approval_hash'] ?? $approval_record['approval_hash'] ?? '')),
            'approval_record_hash' => sanitize_text_field((string) ($body['approval_record_hash'] ?? $approval['approval_record_hash'] ?? $approval_record['approval_record_hash'] ?? '')),
            'approval_decision_hash' => sanitize_text_field((string) ($body['approval_decision_hash'] ?? $approval['approval_decision_hash'] ?? $approval_decision_record['decision_record_hash'] ?? $approval_decision_record['approval_decision_hash'] ?? '')),
        ];
    }

    private static function merchant_quote_id_from_body($body) {
        $quote = isset($body['quote']) && is_array($body['quote']) ? $body['quote'] : [];
        return sanitize_text_field((string) (
            $body['merchant_quote_id']
            ?? $quote['merchant_quote_id']
            ?? $quote['id']
            ?? ''
        ));
    }

    private static function checkout_idempotency_key($body, WP_REST_Request $request) {
        $body_key = sanitize_text_field((string) ($body['idempotency_key'] ?? ''));
        $header_key = sanitize_text_field((string) $request->get_header('idempotency-key'));
        if ($body_key !== '' && $header_key !== '' && !hash_equals($body_key, $header_key)) {
            return new WP_Error('agentcart_idempotency_key_mismatch', 'idempotency_key does not match the Idempotency-Key header.', ['status' => 409]);
        }
        if ($body_key !== '') {
            return $body_key;
        }
        if ($header_key !== '') {
            return $header_key;
        }
        return sanitize_text_field((string) ($body['agentcart_order_id'] ?? ''));
    }

    private static function find_existing_checkout_order($agentcart_order_id, $idempotency_key) {
        $lookups = [
            ['_agentcart_order_id', sanitize_text_field((string) $agentcart_order_id)],
            [self::IDEMPOTENCY_KEY_META, sanitize_text_field((string) $idempotency_key)],
        ];
        foreach ($lookups as $lookup) {
            [$meta_key, $meta_value] = $lookup;
            if ($meta_value === '') {
                continue;
            }
            $existing_orders = wc_get_orders([
                'limit' => 1,
                'return' => 'objects',
                'meta_key' => $meta_key, // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_key -- Idempotency lookup must query Woo order meta by exact AgentCart key.
                'meta_value' => $meta_value, // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_value -- Idempotency lookup must query Woo order meta by exact AgentCart value.
            ]);
            if (!empty($existing_orders)) {
                return $existing_orders[0];
            }
        }
        return null;
    }

    private static function find_existing_quote_order($merchant_quote_id) {
        $merchant_quote_id = sanitize_text_field((string) $merchant_quote_id);
        if ($merchant_quote_id === '') {
            return null;
        }
        $existing_orders = wc_get_orders([
            'limit' => 1,
            'return' => 'objects',
            'meta_key' => '_agentcart_merchant_quote_id', // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_key -- Quote replay lookup must query Woo order meta by merchant quote id.
            'meta_value' => $merchant_quote_id, // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_value -- Quote replay lookup must query Woo order meta by merchant quote id.
        ]);
        return !empty($existing_orders) ? $existing_orders[0] : null;
    }

    private static function validate_existing_order_replay(WC_Order $order, $body, $receipt, $agentcart_order_id, $idempotency_key) {
        $stored_agentcart_order_id = (string) $order->get_meta('_agentcart_order_id', true);
        if ($agentcart_order_id !== '' && $stored_agentcart_order_id !== '' && !hash_equals($stored_agentcart_order_id, $agentcart_order_id)) {
            return new WP_Error('agentcart_idempotency_conflict', 'agentcart_order_id is already bound to a different order.', ['status' => 409]);
        }

        $stored_idempotency_key = (string) $order->get_meta(self::IDEMPOTENCY_KEY_META, true);
        if ($idempotency_key !== '' && $stored_idempotency_key !== '' && !hash_equals($stored_idempotency_key, $idempotency_key)) {
            return new WP_Error('agentcart_idempotency_conflict', 'Idempotency key is already bound to a different order.', ['status' => 409]);
        }

        $stored_quote_hash = (string) $order->get_meta('_agentcart_quote_hash', true);
        $supplied_quote_hash = sanitize_text_field((string) ($body['quote_hash'] ?? ($body['quote']['quote_hash'] ?? '')));
        if ($supplied_quote_hash !== '' && $stored_quote_hash !== '' && !hash_equals($stored_quote_hash, $supplied_quote_hash)) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay quote_hash does not match the existing order.', ['status' => 409]);
        }

        $stored_merchant_quote_id = (string) $order->get_meta('_agentcart_merchant_quote_id', true);
        $supplied_merchant_quote_id = self::merchant_quote_id_from_body($body);
        if ($supplied_merchant_quote_id !== '' && $stored_merchant_quote_id !== '' && !hash_equals($stored_merchant_quote_id, $supplied_merchant_quote_id)) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay merchant_quote_id does not match the existing order.', ['status' => 409]);
        }

        $stored_receipt_id = (string) $order->get_meta('_agentcart_payment_receipt_id', true);
        $supplied_receipt_id = sanitize_text_field((string) ($receipt['id'] ?? ''));
        if ($supplied_receipt_id !== '' && $stored_receipt_id !== '' && !hash_equals($stored_receipt_id, $supplied_receipt_id)) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay payment_receipt.id does not match the existing order.', ['status' => 409]);
        }

        $receipt_amount = isset($receipt['amount_cents']) ? intval($receipt['amount_cents']) : null;
        if ($receipt_amount !== null && $receipt_amount !== self::cents((float) $order->get_total())) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay payment amount does not match the existing order.', ['status' => 409]);
        }

        $receipt_currency = strtoupper((string) ($receipt['currency'] ?? ''));
        if ($receipt_currency !== '' && $receipt_currency !== strtoupper($order->get_currency())) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay payment currency does not match the existing order.', ['status' => 409]);
        }

        $stored_rail = (string) $order->get_meta('_agentcart_payment_rail', true);
        $supplied_rail = self::payment_rail_from_receipt($receipt, $body);
        if ($supplied_rail !== '' && $stored_rail !== '' && $supplied_rail !== $stored_rail) {
            return new WP_Error('agentcart_idempotency_conflict', 'Replay payment rail does not match the existing order.', ['status' => 409]);
        }

        return true;
    }

    private static function refund_idempotency_key($body, WP_REST_Request $request) {
        $body_key = sanitize_text_field((string) ($body['refund_idempotency_key'] ?? $body['idempotency_key'] ?? $body['requested_reference'] ?? ''));
        $header_key = sanitize_text_field((string) $request->get_header('idempotency-key'));
        if ($body_key !== '' && $header_key !== '' && !hash_equals($body_key, $header_key)) {
            return new WP_Error('agentcart_refund_idempotency_key_mismatch', 'Refund idempotency key does not match the Idempotency-Key header.', ['status' => 409]);
        }
        return $body_key !== '' ? $body_key : $header_key;
    }

    private static function find_existing_refund(WC_Order $order, $refund_idempotency_key) {
        if ($refund_idempotency_key === '') {
            return null;
        }
        foreach ($order->get_refunds() as $refund) {
            $stored_key = (string) $refund->get_meta(self::REFUND_IDEMPOTENCY_KEY_META, true);
            if ($stored_key !== '' && hash_equals($stored_key, $refund_idempotency_key)) {
                return $refund;
            }
        }
        return null;
    }

    private static function refund_reference_used(WC_Order $order, $refund_reference) {
        if ($refund_reference === '') {
            return false;
        }
        foreach ($order->get_refunds() as $refund) {
            $stored_reference = (string) $refund->get_meta(self::REFUND_REFERENCE_META, true);
            if ($stored_reference !== '' && hash_equals($stored_reference, $refund_reference)) {
                return true;
            }
            $verification = self::stored_refund_verification($refund);
            $verified_reference = is_array($verification) ? (string) ($verification['refund_reference'] ?? '') : '';
            if ($verified_reference !== '' && hash_equals($verified_reference, $refund_reference)) {
                return true;
            }
        }
        return false;
    }

    private static function validate_existing_refund_replay(WC_Order $order, $refund, $amount_cents, $rail, $refund_idempotency_key, $requested_reference = '') {
        $stored_key = (string) $refund->get_meta(self::REFUND_IDEMPOTENCY_KEY_META, true);
        if ($refund_idempotency_key !== '' && $stored_key !== '' && !hash_equals($stored_key, $refund_idempotency_key)) {
            return new WP_Error('agentcart_refund_idempotency_conflict', 'Refund idempotency key is already bound to a different refund.', ['status' => 409]);
        }

        if ($amount_cents > 0 && $amount_cents !== self::cents((float) $refund->get_amount())) {
            return new WP_Error('agentcart_refund_idempotency_conflict', 'Replay refund amount does not match the existing refund.', ['status' => 409]);
        }

        $stored_rail = (string) $refund->get_meta('_agentcart_refund_rail', true);
        if ($rail !== '' && $stored_rail !== '' && $rail !== $stored_rail) {
            return new WP_Error('agentcart_refund_idempotency_conflict', 'Replay refund rail does not match the existing refund.', ['status' => 409]);
        }

        $stored_requested_reference = (string) $refund->get_meta(self::REFUND_REQUESTED_REFERENCE_META, true);
        if ($requested_reference !== '' && $stored_requested_reference !== '' && !hash_equals($stored_requested_reference, $requested_reference)) {
            return new WP_Error('agentcart_refund_idempotency_conflict', 'Replay refund requested_reference does not match the existing refund.', ['status' => 409]);
        }

        return true;
    }

    private static function cancellation_idempotency_key($body, WP_REST_Request $request) {
        $body_key = sanitize_text_field((string) ($body['cancellation_idempotency_key'] ?? $body['idempotency_key'] ?? $body['requested_reference'] ?? ''));
        $header_key = sanitize_text_field((string) $request->get_header('idempotency-key'));
        if ($body_key !== '' && $header_key !== '' && !hash_equals($body_key, $header_key)) {
            return new WP_Error('agentcart_cancellation_idempotency_key_mismatch', 'Cancellation idempotency key does not match the Idempotency-Key header.', ['status' => 409]);
        }
        return $body_key !== '' ? $body_key : $header_key;
    }

    private static function find_existing_cancellation_event(WC_Order $order, $cancellation_idempotency_key) {
        if ($cancellation_idempotency_key === '') {
            return null;
        }
        foreach (self::stored_cancellation_events($order) as $event) {
            if (!is_array($event)) {
                continue;
            }
            $stored_key = (string) ($event['idempotency_key'] ?? '');
            if ($stored_key !== '' && hash_equals($stored_key, $cancellation_idempotency_key)) {
                return $event;
            }
        }
        return null;
    }

    private static function validate_existing_cancellation_replay($event, $reason, $requested_reference = '') {
        $event = is_array($event) ? $event : [];
        $stored_reason = (string) ($event['reason'] ?? '');
        if ($reason !== '' && $stored_reason !== '' && !hash_equals($stored_reason, $reason)) {
            return new WP_Error('agentcart_cancellation_idempotency_conflict', 'Replay cancellation reason does not match the existing cancellation.', ['status' => 409]);
        }
        $stored_requested_reference = (string) ($event['requested_reference'] ?? '');
        if ($requested_reference !== '' && $stored_requested_reference !== '' && !hash_equals($stored_requested_reference, $requested_reference)) {
            return new WP_Error('agentcart_cancellation_idempotency_conflict', 'Replay cancellation requested_reference does not match the existing cancellation.', ['status' => 409]);
        }
        return true;
    }

    private static function acquire_checkout_lock($idempotency_key) {
        $option_name = self::checkout_lock_option_name($idempotency_key);
        $now = time();
        if (add_option($option_name, (string) $now, '', 'no')) {
            return true;
        }
        $existing = intval(get_option($option_name, 0));
        if ($existing > 0 && $existing < ($now - self::CHECKOUT_LOCK_TTL_SECONDS)) {
            update_option($option_name, (string) $now, false);
            return true;
        }
        return new WP_Error('agentcart_checkout_in_progress', 'A checkout with this idempotency key is already in progress.', ['status' => 409]);
    }

    private static function release_checkout_lock($idempotency_key) {
        delete_option(self::checkout_lock_option_name($idempotency_key));
    }

    private static function checkout_lock_option_name($idempotency_key) {
        return self::CHECKOUT_LOCK_PREFIX . hash('sha256', (string) $idempotency_key);
    }

    private static function acquire_quote_lock($merchant_quote_id) {
        $option_name = self::quote_lock_option_name($merchant_quote_id);
        $now = time();
        if (add_option($option_name, (string) $now, '', 'no')) {
            return true;
        }
        $existing = intval(get_option($option_name, 0));
        if ($existing > 0 && $existing < ($now - self::CHECKOUT_LOCK_TTL_SECONDS)) {
            update_option($option_name, (string) $now, false);
            return true;
        }
        return new WP_Error('agentcart_quote_checkout_in_progress', 'A checkout for this merchant quote is already in progress.', ['status' => 409]);
    }

    private static function release_quote_lock($merchant_quote_id) {
        delete_option(self::quote_lock_option_name($merchant_quote_id));
    }

    private static function quote_lock_option_name($merchant_quote_id) {
        return self::QUOTE_LOCK_PREFIX . hash('sha256', (string) $merchant_quote_id);
    }

    private static function acquire_refund_lock($refund_idempotency_key) {
        $option_name = self::refund_lock_option_name($refund_idempotency_key);
        $now = time();
        if (add_option($option_name, (string) $now, '', 'no')) {
            return true;
        }
        $existing = intval(get_option($option_name, 0));
        if ($existing > 0 && $existing < ($now - self::CHECKOUT_LOCK_TTL_SECONDS)) {
            update_option($option_name, (string) $now, false);
            return true;
        }
        return new WP_Error('agentcart_refund_in_progress', 'A refund with this idempotency key is already in progress.', ['status' => 409]);
    }

    private static function release_refund_lock($refund_idempotency_key) {
        delete_option(self::refund_lock_option_name($refund_idempotency_key));
    }

    private static function refund_lock_option_name($refund_idempotency_key) {
        return self::REFUND_LOCK_PREFIX . hash('sha256', (string) $refund_idempotency_key);
    }

    private static function acquire_cancellation_lock($cancellation_idempotency_key) {
        $option_name = self::cancellation_lock_option_name($cancellation_idempotency_key);
        $now = time();
        if (add_option($option_name, (string) $now, '', 'no')) {
            return true;
        }
        $existing = intval(get_option($option_name, 0));
        if ($existing > 0 && $existing < ($now - self::CHECKOUT_LOCK_TTL_SECONDS)) {
            update_option($option_name, (string) $now, false);
            return true;
        }
        return new WP_Error('agentcart_cancellation_in_progress', 'A cancellation with this idempotency key is already in progress.', ['status' => 409]);
    }

    private static function release_cancellation_lock($cancellation_idempotency_key) {
        delete_option(self::cancellation_lock_option_name($cancellation_idempotency_key));
    }

    private static function cancellation_lock_option_name($cancellation_idempotency_key) {
        return self::CANCELLATION_LOCK_PREFIX . hash('sha256', (string) $cancellation_idempotency_key);
    }

    private static function payment_receipt_from_checkout_request($body, WP_REST_Request $request, $quote) {
        $receipt = isset($body['payment_receipt']) && is_array($body['payment_receipt']) ? $body['payment_receipt'] : [];
        if (!empty($receipt['id'])) {
            return $receipt;
        }
        $signature = self::x402_payment_signature_header($request);
        if ($signature === '' || self::x402_payment_required_document($quote) === null) {
            return $receipt;
        }
        $requirement = self::x402_payment_required_document($quote);
        $accept = is_array($requirement['accepts'][0] ?? null) ? $requirement['accepts'][0] : [];
        return [
            'id' => 'x402_' . substr(hash('sha256', $signature), 0, 24),
            'method' => 'x402-compatible',
            'rail' => 'x402-compatible',
            'provider' => 'x402',
            'status' => 'submitted',
            'amount_cents' => intval($quote['total_cents'] ?? 0),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'payment_contract_hash' => self::payment_contract_hash(self::payment_verification_contract($quote, 'x402-compatible')),
            'network' => (string) ($accept['network'] ?? ''),
            'asset' => (string) ($accept['asset'] ?? ''),
            'pay_to' => (string) ($accept['payTo'] ?? ''),
            'recipient' => (string) ($accept['payTo'] ?? ''),
            'max_amount_required' => (string) ($accept['maxAmountRequired'] ?? ''),
            'x402_version' => intval($requirement['x402Version'] ?? 2),
            'x402_payment_signature' => $signature,
            'payment_signature_header' => 'PAYMENT-SIGNATURE',
            'payment_required' => $requirement,
        ];
    }

    private static function x402_payment_signature_header(WP_REST_Request $request) {
        $signature = trim((string) $request->get_header('PAYMENT-SIGNATURE'));
        if ($signature === '') {
            $signature = trim((string) $request->get_header('X-PAYMENT'));
        }
        return sanitize_text_field($signature);
    }

    private static function x402_payment_required_response($quote, $message) {
        $document = self::x402_payment_required_document($quote);
        if ($document === null) {
            return null;
        }
        $document['error'] = $message;
        $response = new WP_REST_Response($document, 402);
        $response->header('PAYMENT-REQUIRED', self::x402_header_value($document));
        $response->header('Cache-Control', 'no-store');
        return $response;
    }

    private static function verify_payment_receipt($quote, $receipt, $body, WP_REST_Request $request) {
        $expected_amount = intval($quote['total_cents'] ?? 0);
        $expected_currency = (string) ($quote['currency'] ?? get_woocommerce_currency());
        $receipt_amount = intval($receipt['amount_cents'] ?? 0);
        $receipt_currency = (string) ($receipt['currency'] ?? '');
        $expected_quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $receipt_quote_hash = sanitize_text_field((string) ($receipt['quote_hash'] ?? ''));
        $rail = self::payment_rail_from_receipt($receipt, $body);
        $payment_contract = self::payment_verification_contract($quote, $rail);
        $payment_contract_hash = self::payment_contract_hash($payment_contract);
        $receipt_contract_hash = sanitize_text_field((string) ($receipt['payment_contract_hash'] ?? $receipt['contract_hash'] ?? ''));
        if ($receipt_amount !== $expected_amount || strtoupper($receipt_currency) !== strtoupper($expected_currency)) {
            return new WP_Error(
                'agentcart_payment_amount_mismatch',
                'Payment receipt amount or currency does not match the stored quote.',
                ['status' => 402]
            );
        }
        if ($receipt_quote_hash !== '' && !hash_equals($expected_quote_hash, $receipt_quote_hash)) {
            return new WP_Error('agentcart_payment_quote_hash_mismatch', 'Payment receipt quote_hash does not match the stored quote.', ['status' => 402]);
        }
        if ($receipt_contract_hash !== '' && !hash_equals($payment_contract_hash, $receipt_contract_hash)) {
            return new WP_Error('agentcart_payment_contract_mismatch', 'Payment receipt contract hash does not match the stored quote.', ['status' => 402]);
        }

        $verifier_url = self::payment_verifier_url();
        if ($verifier_url !== '') {
            $verification = self::call_payment_verifier($verifier_url, $quote, $receipt, $body);
            if (is_wp_error($verification)) {
                return $verification;
            }
            return $verification;
        }

        if (self::external_verifier_required_for_checkout()) {
            return new WP_Error(
                'agentcart_payment_verifier_required',
                'External-verifier-only checkout requires an external payment verifier.',
                ['status' => 401]
            );
        }

        if (!self::has_valid_merchant_token($request)) {
            return new WP_Error(
                'agentcart_payment_verifier_required',
                'Public checkout requires an external payment verifier.',
                ['status' => 401]
            );
        }

        return [
            'state' => 'verified',
            'mode' => 'trusted_agentcart_token',
            'real_settlement_verified' => false,
            'amount_cents' => $expected_amount,
            'currency' => $expected_currency,
            'rail' => $rail,
            'quote_hash' => $expected_quote_hash,
            'payment_contract_hash' => $payment_contract_hash,
            'note' => 'Merchant token authenticated AgentCart. Configure a payment verifier before production use.',
        ];
    }

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
        $response = wp_remote_post($verifier_url, [
            'headers' => $headers,
            'body' => wp_json_encode($payload),
            'timeout' => 15,
        ]);
        if (is_wp_error($response)) {
            return new WP_Error('agentcart_payment_verifier_failed', $response->get_error_message(), ['status' => 502]);
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded) || empty($decoded['ok'])) {
            return new WP_Error('agentcart_payment_not_verified', 'External payment verifier rejected the receipt.', ['status' => 402, 'detail' => $decoded ?: $raw_body]);
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
        if ($verified_contract_hash !== '' && !hash_equals($payment_contract_hash, $verified_contract_hash)) {
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
            'stripe_profile_id' => $verified_stripe_profile_id ?: $expected_stripe_profile_id,
            'transaction_reference' => $transaction_reference,
            'quote_hash' => $expected_quote_hash,
            'payment_contract_hash' => $payment_contract_hash,
        ];
    }

    private static function verify_refund_request(WC_Order $order, $amount_cents, $reason, $rail, $body) {
        $currency = $order->get_currency();
        $quote_hash = (string) $order->get_meta('_agentcart_quote_hash', true);
        $payment_verification = self::stored_payment_verification($order);
        $transaction_reference = '';
        if (is_array($payment_verification)) {
            $transaction_reference = sanitize_text_field((string) ($payment_verification['transaction_reference'] ?? ''));
        }
        if ($transaction_reference === '') {
            $transaction_reference = sanitize_text_field((string) $order->get_meta('_agentcart_payment_transaction_reference', true));
        }

        $verifier_url = self::payment_verifier_url();
        if ($verifier_url !== '') {
            $verification = self::call_refund_verifier(
                $verifier_url,
                $order,
                $amount_cents,
                $currency,
                $reason,
                $rail,
                $quote_hash,
                $transaction_reference,
                $payment_verification,
                $body
            );
            if (is_wp_error($verification)) {
                return $verification;
            }
            return $verification;
        }

        return [
            'state' => 'demo_refund_recorded',
            'mode' => 'trusted_agentcart_token',
            'rail' => $rail,
            'real_refund_verified' => false,
            'amount_cents' => intval($amount_cents),
            'currency' => $currency,
            'quote_hash' => $quote_hash,
            'original_transaction_reference' => $transaction_reference,
            'note' => 'WooCommerce refund record only. No Stripe, card, Tempo, stablecoin, or EUR rail refund was executed.',
        ];
    }

    private static function call_refund_verifier($verifier_url, WC_Order $order, $amount_cents, $currency, $reason, $rail, $quote_hash, $transaction_reference, $payment_verification, $body) {
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
            ],
            'expected' => [
                'amount_cents' => intval($amount_cents),
                'currency' => $currency,
                'quote_hash' => $quote_hash,
                'original_transaction_reference' => $transaction_reference,
                'tempo_network' => self::tempo_network(),
                'tempo_recipient' => self::tempo_recipient(),
                'stripe_profile_id' => self::stripe_profile_id(),
            ],
        ];
        $headers = ['Content-Type' => 'application/json'];
        $token = self::payment_verifier_token();
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer ' . $token;
        }
        $response = wp_remote_post($verifier_url, [
            'headers' => $headers,
            'body' => wp_json_encode($payload),
            'timeout' => 20,
        ]);
        if (is_wp_error($response)) {
            return new WP_Error('agentcart_refund_verifier_failed', $response->get_error_message(), ['status' => 502]);
        }
        $status = intval(wp_remote_retrieve_response_code($response));
        $raw_body = wp_remote_retrieve_body($response);
        $decoded = json_decode($raw_body, true);
        if ($status < 200 || $status >= 300 || !is_array($decoded) || empty($decoded['ok'])) {
            return new WP_Error('agentcart_refund_not_verified', 'External payment verifier rejected the refund.', ['status' => 402, 'detail' => $decoded ?: $raw_body]);
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

    private static function stored_payment_verification(WC_Order $order) {
        $raw = $order->get_meta('_agentcart_payment_verification', true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? $decoded : null;
    }

    private static function stored_refund_events(WC_Order $order) {
        $raw = $order->get_meta('_agentcart_refunds', true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? $decoded : [];
    }

    private static function stored_cancellation_events(WC_Order $order) {
        $raw = $order->get_meta(self::CANCELLATION_EVENTS_META, true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? array_values(array_filter($decoded, 'is_array')) : [];
    }

    private static function stored_refund_verification($refund) {
        $raw = $refund->get_meta('_agentcart_refund_verification', true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? $decoded : null;
    }

    private static function serialize_refunds(WC_Order $order) {
        $result = [];
        foreach ($order->get_refunds() as $refund) {
            $verification = self::stored_refund_verification($refund);
            $result[] = [
                'id' => (string) $refund->get_id(),
                'amount_cents' => self::cents((float) $refund->get_amount()),
                'currency' => $order->get_currency(),
                'reason' => $refund->get_reason(),
                'rail' => (string) $refund->get_meta('_agentcart_refund_rail', true),
                'idempotency_key' => (string) $refund->get_meta(self::REFUND_IDEMPOTENCY_KEY_META, true),
                'requested_reference' => (string) $refund->get_meta(self::REFUND_REQUESTED_REFERENCE_META, true),
                'refund_reference' => (string) $refund->get_meta(self::REFUND_REFERENCE_META, true),
                'verification' => $verification,
                'real_refund_verified' => is_array($verification) && !empty($verification['real_refund_verified']),
                'created_at' => $refund->get_date_created() ? $refund->get_date_created()->date('c') : null,
            ];
        }
        return $result;
    }

    private static function serialize_cancellations(WC_Order $order) {
        return self::stored_cancellation_events($order);
    }

    private static function cancellation_policy(WC_Order $order) {
        $eligibility = self::cancellation_eligibility($order);
        $merchant_policy = self::stored_merchant_policy($order);
        $aftercare_state = self::aftercare_state($order, $eligibility);
        return [
            'endpoint' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/cancellations'),
            'requires_merchant_token' => true,
            'idempotency_required' => true,
            'eligible' => !empty($eligibility['eligible']),
            'state' => $aftercare_state['cancellation_state'],
            'eligibility' => $eligibility,
            'merchant_policy' => $merchant_policy,
            'does_not_execute_refund' => true,
            'paid_order_requires_separate_refund' => $order->is_paid() && self::cents((float) $order->get_remaining_refund_amount()) > 0,
            'refund_endpoint' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/refunds'),
        ];
    }

    private static function aftercare_state(WC_Order $order, $eligibility = null) {
        $fulfillment = self::serialize_fulfillment($order);
        $delivery_exception = isset($fulfillment['delivery_exception']) && is_array($fulfillment['delivery_exception'])
            ? $fulfillment['delivery_exception']
            : null;
        $eligibility = is_array($eligibility) ? $eligibility : self::cancellation_eligibility($order);
        $blocking_reasons = isset($eligibility['blocking_reasons']) && is_array($eligibility['blocking_reasons'])
            ? $eligibility['blocking_reasons']
            : [];
        $remaining_refundable_cents = self::cents((float) $order->get_remaining_refund_amount());
        $refunded_cents = self::cents((float) $order->get_total_refunded());
        $total_order_cents = self::cents((float) $order->get_total());
        $paid = $order->is_paid();
        $is_cancelled = $order->has_status('cancelled');
        $fully_refunded = ($order->has_status('refunded') || $refunded_cents > 0) && $remaining_refundable_cents <= 0;
        $partially_refunded = $refunded_cents > 0 && $remaining_refundable_cents > 0;
        $refund_required_after_cancellation = $paid && $is_cancelled && $remaining_refundable_cents > 0;
        $cancellation_state = 'not_available';
        if (!empty($eligibility['eligible'])) {
            $cancellation_state = 'cancellable_before_fulfillment';
        } elseif ($is_cancelled && $refund_required_after_cancellation) {
            $cancellation_state = 'cancelled_refund_required';
        } elseif ($is_cancelled && $fully_refunded) {
            $cancellation_state = 'cancelled_refunded';
        } elseif ($is_cancelled) {
            $cancellation_state = 'cancelled_no_refund_due';
        } elseif (in_array('already_cancelled', $blocking_reasons, true)) {
            $cancellation_state = 'already_cancelled';
        } elseif (in_array('fulfillment_tracking_attached', $blocking_reasons, true)) {
            $cancellation_state = 'fulfillment_locked';
        } elseif (in_array('terminal_order_status', $blocking_reasons, true)) {
            $cancellation_state = 'terminal';
        }

        if ($fully_refunded) {
            $refund_state = 'refunded';
        } elseif ($refund_required_after_cancellation) {
            $refund_state = 'refund_required_after_cancellation';
        } elseif ($partially_refunded) {
            $refund_state = 'partially_refunded';
        } elseif (!$paid) {
            $refund_state = 'unpaid_no_refund_due';
        } elseif ($remaining_refundable_cents > 0) {
            $refund_state = 'refund_available';
        } else {
            $refund_state = 'no_refund_remaining';
        }

        if ($is_cancelled) {
            $order_lifecycle_state = $refund_required_after_cancellation
                ? 'cancelled_refund_required'
                : ($fully_refunded ? 'cancelled_refunded' : 'cancelled_no_refund_due');
        } elseif ($fully_refunded) {
            $order_lifecycle_state = 'refunded';
        } elseif ($partially_refunded) {
            $order_lifecycle_state = 'partially_refunded';
        } elseif ($cancellation_state === 'cancellable_before_fulfillment') {
            $order_lifecycle_state = 'cancellable';
        } elseif ($cancellation_state === 'fulfillment_locked') {
            $order_lifecycle_state = 'fulfillment_locked';
        } else {
            $order_lifecycle_state = 'active';
        }

        $next_actions = [];
        if (!empty($fulfillment['tracking_url'])) {
            $next_actions[] = 'open_tracking';
        } elseif (!empty($fulfillment['tracking_number'])) {
            $next_actions[] = 'track_with_carrier';
        } else {
            $next_actions[] = 'check_status_later';
        }
        if ($delivery_exception && !empty($delivery_exception['requires_attention'])) {
            $next_actions[] = 'review_delivery_exception';
            $next_actions[] = 'contact_merchant';
        }
        if ($cancellation_state === 'cancellable_before_fulfillment') {
            $next_actions[] = 'request_cancellation';
        }
        if (in_array($refund_state, ['refund_available', 'partially_refunded', 'refund_required_after_cancellation'], true)) {
            $next_actions[] = 'request_refund';
        }
        if ($refund_required_after_cancellation) {
            $next_actions[] = 'complete_verified_refund';
        }

        $state = [
            'order_status' => $order->get_status(),
            'order_lifecycle_state' => $order_lifecycle_state,
            'fulfillment_phase' => self::fulfillment_phase($order, $fulfillment),
            'cancellation_state' => $cancellation_state,
            'refund_state' => $refund_state,
            'remaining_refundable_cents' => $remaining_refundable_cents,
            'currency' => $order->get_currency(),
            'refund_progress' => [
                'total_order_cents' => $total_order_cents,
                'refunded_cents' => $refunded_cents,
                'remaining_refundable_cents' => $remaining_refundable_cents,
                'partially_refunded' => $partially_refunded,
                'fully_refunded' => $fully_refunded,
                'refund_required_after_cancellation' => $refund_required_after_cancellation,
            ],
            'blocking_reasons' => $blocking_reasons,
            'fulfillment_locked' => !empty($eligibility['fulfillment_locked']),
            'refund_required_if_cancelled' => !empty($eligibility['refund_required_if_cancelled']),
            'refund_required_after_cancellation' => $refund_required_after_cancellation,
            'cancellation_does_not_execute_refund' => true,
            'rail_refund_requires_verifier' => true,
            'delivery_exception_state' => $delivery_exception ? (string) ($delivery_exception['state'] ?? 'exception') : 'none',
            'delivery_exception_requires_attention' => $delivery_exception ? !empty($delivery_exception['requires_attention']) : false,
            'delivery_exception' => $delivery_exception,
            'next_actions' => array_values(array_unique($next_actions)),
        ];
        $state['buyer_aftercare_messages'] = self::buyer_aftercare_messages($order, $state);
        return $state;
    }

    private static function buyer_aftercare_messages(WC_Order $order, $aftercare) {
        $aftercare = is_array($aftercare) ? $aftercare : [];
        $refund_progress = isset($aftercare['refund_progress']) && is_array($aftercare['refund_progress']) ? $aftercare['refund_progress'] : [];
        $refunded_cents = max(0, intval($refund_progress['refunded_cents'] ?? 0));
        $remaining_cents = max(0, intval($aftercare['remaining_refundable_cents'] ?? 0));
        $currency = (string) ($aftercare['currency'] ?? $order->get_currency());
        $refunds = self::serialize_refunds($order);
        $latest_refund = !empty($refunds) ? $refunds[count($refunds) - 1] : [];
        $latest_refund = is_array($latest_refund) ? $latest_refund : [];
        $latest_verification = isset($latest_refund['verification']) && is_array($latest_refund['verification'])
            ? $latest_refund['verification']
            : [];
        $latest_refund_verified = !empty($latest_refund['real_refund_verified']);
        $any_real_refund_verified = false;
        foreach ($refunds as $refund) {
            if (is_array($refund) && !empty($refund['real_refund_verified'])) {
                $any_real_refund_verified = true;
                break;
            }
        }
        $refund_reference = sanitize_text_field((string) ($latest_refund['refund_reference'] ?? $latest_refund['id'] ?? ''));
        $provider = sanitize_text_field((string) ($latest_verification['provider'] ?? $latest_refund['rail'] ?? ''));
        $refund_state = (string) ($aftercare['refund_state'] ?? '');
        $cancellation_state = (string) ($aftercare['cancellation_state'] ?? '');
        $lifecycle_state = (string) ($aftercare['order_lifecycle_state'] ?? '');
        $delivery_exception = isset($aftercare['delivery_exception']) && is_array($aftercare['delivery_exception'])
            ? $aftercare['delivery_exception']
            : [];
        $messages = [
            'summary' => 'Order aftercare is active.',
            'refund' => 'No refund has been recorded.',
            'cancellation' => 'Order cancellation is not currently available.',
            'delivery' => 'Check merchant status for delivery updates.',
            'allowed_claims' => [
                'order_cancelled' => strpos($lifecycle_state, 'cancelled') === 0,
                'refund_recorded' => $refunded_cents > 0,
                'refund_executed' => $any_real_refund_verified,
                'money_returned' => $any_real_refund_verified,
                'refund_still_required' => !empty($aftercare['refund_required_after_cancellation']),
                'carrier_exception' => !empty($aftercare['delivery_exception_requires_attention']),
            ],
        ];

        if ($lifecycle_state === 'cancelled_refund_required') {
            $messages['summary'] = 'Order is cancelled, but a verified refund is still required.';
            $messages['cancellation'] = 'Order is cancelled. Cancellation does not prove money was returned.';
        } elseif ($lifecycle_state === 'cancelled_refunded') {
            $messages['summary'] = 'Order is cancelled and the refundable amount is closed.';
            $messages['cancellation'] = 'Order is cancelled and no refundable amount remains.';
        } elseif ($lifecycle_state === 'cancelled_no_refund_due') {
            $messages['summary'] = 'Order is cancelled and no refund is due.';
            $messages['cancellation'] = 'Order is cancelled. No paid refundable amount remains.';
        } elseif ($cancellation_state === 'cancellable_before_fulfillment') {
            $messages['summary'] = 'Order can still be sent for merchant cancellation review.';
            $messages['cancellation'] = 'A trusted gateway or merchant can review cancellation before fulfillment locks.';
        } elseif ($cancellation_state === 'fulfillment_locked') {
            $messages['cancellation'] = 'Cancellation is locked because fulfillment or tracking has started.';
        }

        if ($refund_state === 'refund_required_after_cancellation') {
            $messages['refund'] = 'A verified refund is still required for ' . self::aftercare_money($remaining_cents, $currency) . '.';
        } elseif ($refund_state === 'partially_refunded') {
            $messages['refund'] = 'A partial refund of ' . self::aftercare_money($refunded_cents, $currency)
                . ' is recorded; ' . self::aftercare_money($remaining_cents, $currency) . ' remains refundable.';
        } elseif ($refund_state === 'refunded') {
            if ($any_real_refund_verified) {
                $via = $provider !== '' ? ' via ' . $provider : '';
                $reference = $refund_reference !== '' ? ' Reference: ' . $refund_reference . '.' : '';
                $messages['refund'] = 'Refund executed and verified' . $via . '.' . $reference;
            } else {
                $messages['refund'] = 'Refund recorded by the merchant system. No real rail refund verification is attached.';
            }
        } elseif ($refund_state === 'refund_available') {
            $messages['refund'] = self::aftercare_money($remaining_cents, $currency) . ' remains refundable pending merchant or verifier review.';
        } elseif ($refund_state === 'unpaid_no_refund_due') {
            $messages['refund'] = 'Order is unpaid, so no refund is due.';
        } elseif ($refund_state === 'no_refund_remaining') {
            $messages['refund'] = 'No refundable amount remains.';
        }

        if (!empty($aftercare['delivery_exception_requires_attention'])) {
            $summary = sanitize_text_field((string) ($delivery_exception['summary'] ?? $delivery_exception['state'] ?? 'Carrier reported a delivery exception.'));
            $messages['delivery'] = 'Carrier delivery exception requires attention: ' . $summary;
        }

        if (!empty($latest_refund) && $latest_refund_verified) {
            $messages['allowed_claims']['latest_refund_verified'] = true;
            $messages['allowed_claims']['latest_refund_reference'] = $refund_reference;
        }
        return $messages;
    }

    private static function aftercare_money($cents, $currency) {
        $currency = strtoupper(sanitize_text_field((string) $currency));
        if ($currency === '') {
            $currency = 'EUR';
        }
        return number_format(max(0, intval($cents)) / 100, 2, '.', '') . ' ' . $currency;
    }

    private static function fulfillment_phase(WC_Order $order, $fulfillment) {
        $tracking_status = is_array($fulfillment) ? (string) ($fulfillment['tracking_status'] ?? '') : '';
        if ($order->has_status('completed')) {
            return 'fulfilled';
        }
        if ($order->has_status(['cancelled', 'refunded', 'failed'])) {
            return 'closed';
        }
        if ($tracking_status === 'delivered') {
            return 'fulfilled';
        }
        if (!empty($fulfillment['tracking_number']) || !empty($fulfillment['tracking_url'])) {
            return 'shipped';
        }
        return 'pre_fulfillment';
    }

    private static function cancellation_eligibility(WC_Order $order) {
        $status = $order->get_status();
        $tracking = self::tracking_from_order_meta($order);
        $merchant_policy = self::stored_merchant_policy($order);
        $cancellations = isset($merchant_policy['cancellations']) && is_array($merchant_policy['cancellations']) ? $merchant_policy['cancellations'] : [];
        $window_minutes = intval($cancellations['request_window_minutes'] ?? 0);
        $created = $order->get_date_created();
        $within_window = $window_minutes > 0 && $created
            ? time() <= ($created->getTimestamp() + ($window_minutes * 60))
            : $window_minutes > 0;
        $reasons = [];
        if ($status === 'cancelled') {
            $reasons[] = 'already_cancelled';
        }
        if (in_array($status, ['completed', 'refunded', 'failed'], true)) {
            $reasons[] = 'terminal_order_status';
        }
        if (
            !empty($tracking['tracking_number'])
            || !empty($tracking['tracking_url'])
            || in_array((string) ($tracking['tracking_status'] ?? ''), ['shipped', 'in_transit', 'out_for_delivery', 'delivered', 'exception'], true)
        ) {
            $reasons[] = 'fulfillment_tracking_attached';
        }
        return [
            'eligible' => empty($reasons),
            'status' => $status,
            'blocking_reasons' => $reasons,
            'fulfillment_locked' => !empty($reasons),
            'within_advertised_buyer_request_window' => $within_window,
            'advertised_request_window_minutes' => $window_minutes,
            'refund_required_if_cancelled' => $order->is_paid() && self::cents((float) $order->get_remaining_refund_amount()) > 0,
        ];
    }

    private static function refund_policy(WC_Order $order) {
        $item_policy_summary = self::order_item_policy_summary($order);
        $merchant_policy = self::stored_merchant_policy($order);
        return [
            'endpoint' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/refunds'),
            'requires_merchant_token' => true,
            'remaining_refundable_cents' => self::cents((float) $order->get_remaining_refund_amount()),
            'currency' => $order->get_currency(),
            'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
            'production_requires_rail_refund_verification' => true,
            'rails' => self::payment_rails(),
            'merchant_policy' => $merchant_policy,
            'item_policy_summary' => $item_policy_summary,
            'merchant_review_required' => !empty($item_policy_summary['merchant_review_required']),
        ];
    }

    private static function order_item_policy_summary(WC_Order $order) {
        $codes = [];
        $restricted_codes = [];
        $non_returnable_count = 0;
        $deposit_count = 0;
        $perishable_count = 0;
        foreach (self::serialize_order_items($order) as $item) {
            $commerce_policy = isset($item['commerce_policy']) && is_array($item['commerce_policy']) ? $item['commerce_policy'] : [];
            $flags = isset($commerce_policy['flags']) && is_array($commerce_policy['flags']) ? $commerce_policy['flags'] : [];
            foreach ($flags as $flag) {
                if (!is_array($flag) || empty($flag['code'])) {
                    continue;
                }
                $code = (string) $flag['code'];
                if (!in_array($code, $codes, true)) {
                    $codes[] = $code;
                }
                if ($code === 'perishable') {
                    $perishable_count++;
                }
                if ($code === 'deposit') {
                    $deposit_count++;
                }
            }
            if (isset($commerce_policy['returnable_by_default']) && !$commerce_policy['returnable_by_default']) {
                $non_returnable_count++;
            }
            $restricted_goods = isset($item['restricted_goods']) && is_array($item['restricted_goods']) ? $item['restricted_goods'] : [];
            foreach ($restricted_goods as $flag) {
                if (is_array($flag) && !empty($flag['code']) && !in_array((string) $flag['code'], $restricted_codes, true)) {
                    $restricted_codes[] = (string) $flag['code'];
                }
            }
        }
        sort($codes);
        sort($restricted_codes);
        return [
            'commerce_policy_codes' => $codes,
            'restricted_goods_codes' => $restricted_codes,
            'perishable_item_count' => $perishable_count,
            'deposit_item_count' => $deposit_count,
            'non_returnable_item_count' => $non_returnable_count,
            'merchant_review_required' => !empty($codes) || !empty($restricted_codes),
            'buyer_agent_note' => (!empty($codes) || !empty($restricted_codes))
                ? 'Review item-level policy before refund, return, cancellation, or substitution.'
                : 'Standard merchant refund policy applies.',
        ];
    }

    private static function quote_refund_policy() {
        return [
            'returns_url' => self::returns_url(),
            'refund_endpoint_template' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
            'requires_merchant_token' => true,
            'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
            'production_requires_rail_refund_verification' => true,
            'merchant_policy' => self::merchant_policy(),
        ];
    }

    private static function payment_rail_from_order(WC_Order $order) {
        $stored = self::normalize_payment_rail((string) $order->get_meta('_agentcart_payment_rail', true));
        if ($stored !== '') {
            return $stored;
        }
        $method = $order->get_payment_method();
        if (strpos($method, 'stripe') !== false) {
            return 'stripe-card-mpp';
        }
        if (strpos($method, 'tempo') !== false) {
            return 'tempo-mpp';
        }
        if (strpos($method, 'x402') !== false) {
            return 'x402-compatible';
        }
        return $method ?: 'agentcart-demo';
    }

    private static function payment_rail_from_receipt($receipt, $body) {
        $rail = '';
        if (is_array($body)) {
            $rail = (string) ($body['rail'] ?? '');
        }
        if ($rail === '' && is_array($receipt)) {
            $proof = isset($receipt['external_value_proof']) && is_array($receipt['external_value_proof']) ? $receipt['external_value_proof'] : [];
            $proof_provider = (string) ($proof['provider'] ?? '');
            if ($proof_provider === 'tempo_mpp') {
                $rail = 'tempo-mpp';
            } else {
                $rail = (string) ($receipt['rail'] ?? $receipt['method'] ?? $receipt['provider'] ?? '');
            }
        }
        $normalized = self::normalize_payment_rail($rail);
        return $normalized !== '' ? $normalized : 'tempo-mpp';
    }

    private static function normalize_payment_rail($rail) {
        $rail = str_replace('_', '-', sanitize_key((string) $rail));
        if ($rail === 'tempo' || $rail === 'tempo-mpp' || $rail === 'mpp' || $rail === 'mpp-shaped-demo' || $rail === 'demo-payment-proof') {
            return 'tempo-mpp';
        }
        if ($rail === 'stripe' || $rail === 'stripe-card' || $rail === 'stripe-card-mpp') {
            return 'stripe-card-mpp';
        }
        if ($rail === 'x402' || $rail === 'x402-compatible' || $rail === 'x402-exact') {
            return 'x402-compatible';
        }
        return $rail;
    }

    private static function woo_payment_method_for_rail($rail) {
        if ($rail === 'stripe-card-mpp') {
            return 'stripe_card_mpp';
        }
        if ($rail === 'tempo-mpp') {
            return 'tempo_mpp';
        }
        if ($rail === 'x402-compatible') {
            return 'x402';
        }
        return 'agentcart_mpp';
    }

    private static function payment_method_title_for_rail($rail) {
        if ($rail === 'stripe-card-mpp') {
            return 'Stripe/Card MPP via AgentCart';
        }
        if ($rail === 'tempo-mpp') {
            return 'Tempo MPP via AgentCart';
        }
        if ($rail === 'x402-compatible') {
            return 'x402 via AgentCart';
        }
        return 'AgentCart MPP';
    }

    private static function serialize_fulfillment(WC_Order $order) {
        $tracking = self::tracking_from_order_meta($order);
        $delivery_window = self::stored_delivery_window($order);
        $state = self::fulfillment_state_from_tracking($order, $tracking);
        $delivery_exception = self::delivery_exception_from_tracking($tracking);
        return [
            'state' => $state,
            'order_status' => $order->get_status(),
            'carrier' => $tracking['carrier'],
            'tracking_number' => $tracking['tracking_number'],
            'tracking_url' => $tracking['tracking_url'],
            'tracking_status' => $tracking['tracking_status'],
            'tracking' => $tracking,
            'has_delivery_exception' => $delivery_exception !== null,
            'delivery_exception' => $delivery_exception,
            'estimated_delivery_window' => $delivery_window,
            'source' => $tracking['source'],
            'note' => $tracking['tracking_number'] || $tracking['tracking_url']
                ? 'Carrier tracking metadata was read from ' . $tracking['source'] . '.'
                : 'No carrier tracking metadata is attached yet.',
        ];
    }

    private static function tracking_from_order_meta(WC_Order $order) {
        $default = self::tracking_candidate('woocommerce_order_meta', 'none', '', '', '', '', null, null, null);
        $shipment_items = $order->get_meta('_wc_shipment_tracking_items', true);
        if (is_array($shipment_items) && !empty($shipment_items)) {
            foreach ($shipment_items as $item) {
                if (!is_array($item)) {
                    continue;
                }
                $tracking = self::tracking_candidate(
                    'woocommerce_shipment_tracking',
                    'woocommerce-shipment-tracking',
                    $item['tracking_provider'] ?? $item['custom_tracking_provider'] ?? '',
                    $item['tracking_number'] ?? '',
                    $item['custom_tracking_link'] ?? $item['tracking_link'] ?? '',
                    $item['tracking_status'] ?? $item['shipment_status'] ?? $item['status'] ?? '',
                    $item['date_shipped'] ?? null,
                    $item['date_delivered'] ?? null,
                    $item['last_event_at'] ?? $item['date_updated'] ?? null
                );
                if (self::tracking_has_carrier_data($tracking)) {
                    return $tracking;
                }
            }
        }

        $aftership = self::tracking_candidate(
            'aftership_tracking',
            'aftership',
            self::first_order_meta_value($order, ['_aftership_tracking_provider_name', 'aftership_tracking_provider_name', '_aftership_courier', 'aftership_courier']),
            self::first_order_meta_value($order, ['_aftership_tracking_number', 'aftership_tracking_number']),
            self::first_order_meta_value($order, ['_aftership_tracking_url', 'aftership_tracking_url']),
            self::first_order_meta_value($order, ['_aftership_tracking_status', 'aftership_tracking_status']),
            self::first_order_meta_value($order, ['_aftership_tracking_ship_date', 'aftership_tracking_ship_date']),
            self::first_order_meta_value($order, ['_aftership_tracking_delivery_date', 'aftership_tracking_delivery_date']),
            self::first_order_meta_value($order, ['_aftership_tracking_updated_at', 'aftership_tracking_updated_at'])
        );
        if (self::tracking_has_carrier_data($aftership)) {
            return $aftership;
        }

        $parcelpanel = self::tracking_candidate(
            'parcelpanel_tracking',
            'parcelpanel',
            self::first_order_meta_value($order, ['_parcelpanel_courier', 'parcelpanel_courier', '_parcelpanel_carrier', 'parcelpanel_carrier']),
            self::first_order_meta_value($order, ['_parcelpanel_tracking_number', 'parcelpanel_tracking_number']),
            self::first_order_meta_value($order, ['_parcelpanel_tracking_url', 'parcelpanel_tracking_url']),
            self::first_order_meta_value($order, ['_parcelpanel_status', 'parcelpanel_status']),
            self::first_order_meta_value($order, ['_parcelpanel_shipped_at', 'parcelpanel_shipped_at']),
            self::first_order_meta_value($order, ['_parcelpanel_delivered_at', 'parcelpanel_delivered_at']),
            self::first_order_meta_value($order, ['_parcelpanel_updated_at', 'parcelpanel_updated_at'])
        );
        if (self::tracking_has_carrier_data($parcelpanel)) {
            return $parcelpanel;
        }

        $generic = self::tracking_candidate(
            'generic_order_meta',
            'generic-order-meta',
            self::first_order_meta_value($order, ['_tracking_provider', 'tracking_provider', '_carrier', 'carrier']),
            self::first_order_meta_value($order, ['_tracking_number', 'tracking_number']),
            self::first_order_meta_value($order, ['_tracking_url', 'tracking_url']),
            self::first_order_meta_value($order, ['_tracking_status', 'tracking_status', '_shipment_status', 'shipment_status']),
            self::first_order_meta_value($order, ['_date_shipped', 'date_shipped', '_shipped_at', 'shipped_at']),
            self::first_order_meta_value($order, ['_date_delivered', 'date_delivered', '_delivered_at', 'delivered_at']),
            self::first_order_meta_value($order, ['_tracking_last_event_at', 'tracking_last_event_at'])
        );
        return self::tracking_has_carrier_data($generic) ? $generic : $default;
    }

    private static function tracking_candidate($source, $adapter, $carrier, $tracking_number, $tracking_url, $tracking_status = '', $shipped_at = null, $delivered_at = null, $last_event_at = null) {
        $carrier = sanitize_text_field((string) $carrier);
        $tracking_number = sanitize_text_field((string) $tracking_number);
        $tracking_url = esc_url_raw((string) $tracking_url);
        $status_label = sanitize_text_field((string) $tracking_status);
        $shipped_at = self::normalize_tracking_datetime($shipped_at);
        $delivered_at = self::normalize_tracking_datetime($delivered_at);
        $last_event_at = self::normalize_tracking_datetime($last_event_at);
        $has_tracking = $tracking_number !== '' || $tracking_url !== '';
        $normalized_status = self::normalize_tracking_status($status_label, $has_tracking, $delivered_at);
        return [
            'carrier' => $carrier,
            'tracking_number' => $tracking_number,
            'tracking_url' => $tracking_url,
            'tracking_status' => $normalized_status,
            'tracking_status_label' => $status_label,
            'shipped_at' => $shipped_at,
            'delivered_at' => $delivered_at,
            'last_event_at' => $last_event_at,
            'source' => sanitize_key((string) $source),
            'adapter' => sanitize_key((string) $adapter),
            'confidence' => $has_tracking ? 'carrier_reference' : ($normalized_status !== 'not_shipped' ? 'status_only' : 'none'),
            'is_real_carrier_tracking' => $has_tracking,
        ];
    }

    private static function tracking_has_carrier_data($tracking) {
        return is_array($tracking)
            && (
                !empty($tracking['tracking_number'])
                || !empty($tracking['tracking_url'])
                || !empty($tracking['carrier'])
                || (($tracking['tracking_status'] ?? 'not_shipped') !== 'not_shipped')
            );
    }

    private static function first_order_meta_value(WC_Order $order, $keys) {
        foreach ($keys as $key) {
            $value = $order->get_meta($key, true);
            if (is_array($value) || is_object($value)) {
                continue;
            }
            if (trim((string) $value) !== '') {
                return $value;
            }
        }
        return '';
    }

    private static function normalize_tracking_datetime($value) {
        if ($value instanceof DateTimeInterface) {
            return gmdate('c', $value->getTimestamp());
        }
        if (is_numeric($value)) {
            $timestamp = intval($value);
            return $timestamp > 0 ? gmdate('c', $timestamp) : null;
        }
        $value = trim((string) $value);
        if ($value === '') {
            return null;
        }
        $timestamp = strtotime($value);
        return $timestamp ? gmdate('c', $timestamp) : null;
    }

    private static function normalize_tracking_status($status_label, $has_tracking, $delivered_at = null) {
        $status = strtolower(trim((string) $status_label));
        if (strpos($status, 'partial') !== false && strpos($status, 'deliver') !== false) {
            return 'exception';
        }
        if (
            strpos($status, 'exception') !== false
            || strpos($status, 'failed') !== false
            || strpos($status, 'return') !== false
            || strpos($status, 'delayed') !== false
            || strpos($status, 'delay') !== false
            || strpos($status, 'attempt') !== false
            || strpos($status, 'refused') !== false
            || strpos($status, 'held') !== false
            || strpos($status, 'lost') !== false
            || strpos($status, 'damaged') !== false
        ) {
            return 'exception';
        }
        if ($delivered_at || strpos($status, 'delivered') !== false) {
            return 'delivered';
        }
        if (strpos($status, 'out_for_delivery') !== false || strpos($status, 'out for delivery') !== false) {
            return 'out_for_delivery';
        }
        if (strpos($status, 'transit') !== false || strpos($status, 'in_transit') !== false) {
            return 'in_transit';
        }
        if (strpos($status, 'shipped') !== false || strpos($status, 'fulfilled') !== false || strpos($status, 'dispatched') !== false) {
            return 'shipped';
        }
        return $has_tracking ? 'shipped' : 'not_shipped';
    }

    private static function delivery_exception_from_tracking($tracking) {
        if (!is_array($tracking)) {
            return null;
        }
        $status_label = strtolower(trim((string) ($tracking['tracking_status_label'] ?? '')));
        $normalized_status = strtolower(trim((string) ($tracking['tracking_status'] ?? '')));
        $search = trim($normalized_status . ' ' . $status_label);
        if ($search === '' || $normalized_status === 'not_shipped') {
            return null;
        }
        $state = '';
        $summary = '';
        if (strpos($search, 'partial') !== false && strpos($search, 'deliver') !== false) {
            $state = 'partial_delivery';
            $summary = 'Shipment was only partially delivered.';
        } elseif (strpos($search, 'return') !== false) {
            $state = 'returned';
            $summary = 'Shipment appears to be returning or returned.';
        } elseif (strpos($search, 'delay') !== false || strpos($search, 'delayed') !== false) {
            $state = 'delayed';
            $summary = 'Carrier reported a delivery delay.';
        } elseif (strpos($search, 'failed') !== false || strpos($search, 'attempt') !== false || strpos($search, 'refused') !== false) {
            $state = 'failed';
            $summary = 'Carrier reported a failed delivery attempt.';
        } elseif (strpos($search, 'lost') !== false || strpos($search, 'damaged') !== false) {
            $state = 'exception';
            $summary = 'Carrier reported a lost or damaged shipment.';
        } elseif (strpos($search, 'held') !== false || strpos($search, 'exception') !== false || $normalized_status === 'exception') {
            $state = 'exception';
            $summary = 'Carrier reported a delivery exception.';
        }
        if ($state === '') {
            return null;
        }
        $next_actions = [];
        if (!empty($tracking['tracking_url'])) {
            $next_actions[] = 'open_tracking';
        } elseif (!empty($tracking['tracking_number'])) {
            $next_actions[] = 'track_with_carrier';
        }
        $next_actions[] = 'review_delivery_exception';
        $next_actions[] = 'contact_merchant';
        return [
            'state' => $state,
            'summary' => $summary,
            'tracking_status' => $normalized_status ?: 'exception',
            'tracking_status_label' => (string) ($tracking['tracking_status_label'] ?? ''),
            'carrier' => (string) ($tracking['carrier'] ?? ''),
            'tracking_number' => (string) ($tracking['tracking_number'] ?? ''),
            'tracking_url' => (string) ($tracking['tracking_url'] ?? ''),
            'source' => (string) ($tracking['source'] ?? ''),
            'last_event_at' => $tracking['last_event_at'] ?? null,
            'requires_attention' => true,
            'next_actions' => array_values(array_unique($next_actions)),
        ];
    }

    private static function fulfillment_state_from_tracking(WC_Order $order, $tracking) {
        $tracking_status = is_array($tracking) ? (string) ($tracking['tracking_status'] ?? '') : '';
        if ($tracking_status === 'delivered' || $order->has_status('completed')) {
            return 'fulfilled';
        }
        if (in_array($tracking_status, ['shipped', 'in_transit', 'out_for_delivery', 'exception'], true)) {
            return 'shipped';
        }
        if ($order->has_status(['cancelled', 'refunded', 'failed'])) {
            return 'closed';
        }
        return 'preparing';
    }

    private static function stored_delivery_window(WC_Order $order) {
        $raw = $order->get_meta('_agentcart_delivery_window', true);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        return is_array($decoded) ? $decoded : null;
    }

    private static function quote_hash($quote) {
        return hash('sha256', wp_json_encode(self::quote_hash_payload($quote)));
    }

    private static function quote_hash_payload($quote) {
        return [
            'id' => (string) ($quote['id'] ?? ''),
            'merchant_id' => self::merchant()['id'],
            'items' => $quote['items'] ?? [],
            'ship_to' => $quote['ship_to'] ?? [],
            'subtotal_cents' => intval($quote['subtotal_cents'] ?? 0),
            'shipping' => $quote['shipping'] ?? [],
            'vat_lines' => $quote['vat_lines'] ?? [],
            'total_cents' => intval($quote['total_cents'] ?? 0),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'expires_at' => (string) ($quote['expires_at'] ?? ''),
            'stock_reserved_until' => (string) ($quote['stock_reserved_until'] ?? ''),
            'stock_reservation' => $quote['stock_reservation'] ?? null,
            'terms_url' => (string) ($quote['terms_url'] ?? self::terms_url()),
            'returns_url' => (string) ($quote['returns_url'] ?? self::returns_url()),
            'merchant_policy' => $quote['merchant_policy'] ?? self::merchant_policy(),
            'payment_profile' => [
                'verification_mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'checkout_mode' => self::checkout_mode(),
                'external_verifier_required_for_checkout' => self::external_verifier_required_for_checkout(),
                'signed_request_mode' => self::signed_request_mode(),
                'signed_request_required_for' => self::signed_request_required_buckets(),
                'signed_request_active_signer' => self::signed_request_active_key_id(),
                'signed_request_key_rotation_seconds' => self::SIGNED_REQUEST_KEY_RETIREMENT_SECONDS,
                'tempo_network' => self::tempo_network(),
                'tempo_recipient' => self::tempo_recipient(),
                'stripe_profile_id' => self::stripe_profile_id(),
            ],
        ];
    }

    private static function payment_requirements($quote) {
        $x402 = self::x402_payment_required_document($quote);
        $payment_contracts = self::payment_verification_contracts($quote);
        $preferred_payment_contract = $payment_contracts[0] ?? self::payment_verification_contract_with_hash($quote, 'tempo-mpp');
        return [
            'amount_cents' => intval($quote['total_cents'] ?? 0),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'quote_hash' => (string) ($quote['quote_hash'] ?? self::quote_hash($quote)),
            'quote_total' => [
                'amount_cents' => intval($quote['total_cents'] ?? 0),
                'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                'subtotal_cents' => intval($quote['subtotal_cents'] ?? 0),
                'shipping_cents' => intval($quote['shipping']['amount_cents'] ?? 0),
                'vat_lines' => $quote['vat_lines'] ?? [],
                'includes' => ['items', 'shipping', 'tax'],
            ],
            'checkout_endpoint' => rest_url(self::API_NAMESPACE . '/orders'),
            'payment_protocol_profile_ids' => self::payment_protocol_profile_ids(),
            'verification_contract' => $preferred_payment_contract,
            'verification_contracts' => $payment_contracts,
            'payment_contract_hash' => (string) ($preferred_payment_contract['payment_contract_hash'] ?? ''),
            'x402' => [
                'enabled' => $x402 !== null,
                'version' => 2,
                'payment_required_header' => 'PAYMENT-REQUIRED',
                'payment_signature_header' => 'PAYMENT-SIGNATURE',
                'payment_response_header' => 'PAYMENT-RESPONSE',
                'payment_required' => $x402,
                'payment_required_header_value' => $x402 !== null ? self::x402_header_value($x402) : null,
                'unavailable_reason' => $x402 === null ? self::x402_unavailable_reason($quote) : null,
            ],
            'idempotency' => [
                'required' => true,
                'accepted_fields' => ['agentcart_order_id', 'idempotency_key', 'Idempotency-Key'],
                'replay_state' => 'idempotent_replay',
            ],
            'verification' => [
                'mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'external_verifier_configured' => self::payment_verifier_url() !== '',
                'checkout_mode' => self::checkout_mode(),
                'external_verifier_required_for_checkout' => self::external_verifier_required_for_checkout(),
                'trusted_token_checkout_enabled' => !self::external_verifier_required_for_checkout(),
                'payment_contract_hash' => (string) ($preferred_payment_contract['payment_contract_hash'] ?? ''),
                'payment_contract_schema' => 'agentcart.payment_verification_contract.v1',
            ],
            'request_signature' => [
                'configured' => self::signed_request_profile_configured(),
                'mode' => self::signed_request_mode(),
                'required_for_checkout' => self::signed_request_required_for_bucket('checkout'),
                'required_for' => self::signed_request_required_buckets(),
                'profile_id' => self::signed_request_profile_configured() ? 'signed-http-ready' : null,
                'signature_scheme' => self::signed_request_preferred_signature_scheme(),
                'signature_schemes' => self::signed_request_supported_signature_schemes(),
                'headers' => self::signed_request_header_names(),
                'max_ttl_seconds' => self::SIGNED_REQUEST_MAX_TTL_SECONDS,
                'active_signer' => self::signed_request_active_key_id(),
                'accepted_signers' => self::signed_request_public_key_summaries(),
                'key_rotation' => [
                    'supported' => !defined('AGENTCART_SIGNED_REQUEST_SECRET'),
                    'retirement_seconds' => self::SIGNED_REQUEST_KEY_RETIREMENT_SECONDS,
                ],
            ],
            'protocols' => [
                [
                    'id' => 'tempo-mpp',
                    'profile_id' => self::tempo_payment_profile_configured() ? 'mpp-http-auth' : null,
                    'type' => 'stablecoin',
                    'available' => self::tempo_recipient() !== '' || self::payment_verifier_url() !== '',
                    'network' => self::tempo_network(),
                    'recipient' => self::tempo_recipient(),
                    'amount_cents' => intval($quote['total_cents'] ?? 0),
                    'quote_currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                    'settlement_asset' => self::tempo_settlement_asset(),
                    'settlement_note' => 'WooCommerce quotes in the store currency. If the Tempo asset differs, the external verifier/payment provider must bind the FX conversion and settlement terms to the quote before creating a paid order.',
                ],
                [
                    'id' => 'stripe-card-mpp',
                    'profile_id' => self::stripe_payment_profile_configured() ? 'stripe-card-mpp' : null,
                    'type' => 'card',
                    'available' => self::stripe_payment_profile_configured(),
                    'network_id' => self::stripe_profile_id(),
                    'amount_cents' => intval($quote['total_cents'] ?? 0),
                    'quote_currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                    'settlement_note' => 'Stripe/card MPP requires Stripe machine-payment access, a Stripe profile/network id, and an external verifier that validates Shared Payment Token credentials and refunds.',
                    'setup_required' => !self::stripe_payment_profile_configured(),
                ],
                [
                    'id' => 'http-402-compatible',
                    'scheme' => 'Payment',
                    'quote_hash_required' => true,
                ],
                [
                    'id' => 'x402-compatible',
                    'profile_id' => $x402 !== null ? 'x402-compatible' : null,
                    'type' => 'stablecoin',
                    'available' => $x402 !== null,
                    'x402_version' => 2,
                    'scheme' => 'exact',
                    'network' => self::x402_network(),
                    'asset' => self::x402_asset(),
                    'pay_to' => self::x402_pay_to(),
                    'amount_cents' => intval($quote['total_cents'] ?? 0),
                    'quote_currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                    'max_amount_required' => $x402 !== null ? (string) ($x402['accepts'][0]['maxAmountRequired'] ?? '') : '',
                    'payment_required_header' => 'PAYMENT-REQUIRED',
                    'payment_signature_header' => 'PAYMENT-SIGNATURE',
                    'payment_response_header' => 'PAYMENT-RESPONSE',
                    'setup_required' => $x402 === null,
                    'unavailable_reason' => $x402 === null ? self::x402_unavailable_reason($quote) : null,
                ],
            ],
        ];
    }

    private static function payment_verification_contracts($quote) {
        $contracts = [];
        foreach (self::available_payment_rails_for_quote($quote) as $rail) {
            $contracts[] = self::payment_verification_contract_with_hash($quote, $rail);
        }
        return $contracts ?: [self::payment_verification_contract_with_hash($quote, 'tempo-mpp')];
    }

    private static function available_payment_rails_for_quote($quote) {
        $rails = [];
        if (self::tempo_recipient() !== '' || self::payment_verifier_url() !== '' || !self::external_verifier_required_for_checkout()) {
            $rails[] = 'tempo-mpp';
        }
        if (self::stripe_payment_profile_configured()) {
            $rails[] = 'stripe-card-mpp';
        }
        if (self::x402_payment_required_document($quote) !== null) {
            $rails[] = 'x402-compatible';
        }
        return array_values(array_unique($rails));
    }

    private static function payment_verification_contract_with_hash($quote, $rail) {
        $contract = self::payment_verification_contract($quote, $rail);
        $contract['payment_contract_hash'] = self::payment_contract_hash($contract);
        return $contract;
    }

    private static function payment_verification_contract($quote, $rail = '') {
        $rail = self::normalize_payment_rail($rail ?: 'tempo-mpp');
        $shipping = isset($quote['shipping']) && is_array($quote['shipping']) ? $quote['shipping'] : [];
        $contract = [
            'schema' => 'agentcart.payment_verification_contract.v1',
            'merchant_id' => self::merchant()['id'],
            'merchant_quote_id' => (string) ($quote['id'] ?? ''),
            'quote_hash' => (string) ($quote['quote_hash'] ?? self::quote_hash($quote)),
            'rail' => $rail,
            'amount' => [
                'amount_cents' => intval($quote['total_cents'] ?? 0),
                'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                'subtotal_cents' => intval($quote['subtotal_cents'] ?? 0),
                'shipping_cents' => intval($shipping['amount_cents'] ?? 0),
                'vat_lines' => $quote['vat_lines'] ?? [],
                'includes' => ['items', 'shipping', 'tax'],
            ],
            'checkout_endpoint' => rest_url(self::API_NAMESPACE . '/orders'),
            'expires_at' => (string) ($quote['expires_at'] ?? ''),
            'stock_reserved_until' => (string) ($quote['stock_reserved_until'] ?? ''),
            'terms_url' => (string) ($quote['terms_url'] ?? self::terms_url()),
            'returns_url' => (string) ($quote['returns_url'] ?? self::returns_url()),
        ];
        if ($rail === 'tempo-mpp') {
            $contract['settlement'] = [
                'network' => self::tempo_network(),
                'recipient' => self::tempo_recipient(),
                'asset' => self::tempo_settlement_asset(),
                'fx_policy' => 'external_verifier_binds_quote_currency_to_settlement_asset',
            ];
        } elseif ($rail === 'stripe-card-mpp') {
            $contract['settlement'] = [
                'stripe_profile_id' => self::stripe_profile_id(),
                'network_id' => self::stripe_profile_id(),
                'asset' => ['denomination' => (string) ($quote['currency'] ?? get_woocommerce_currency())],
            ];
        } elseif ($rail === 'x402-compatible') {
            $contract['settlement'] = [
                'network' => self::x402_network(),
                'asset' => self::x402_asset(),
                'pay_to' => self::x402_pay_to(),
                'max_amount_required' => self::x402_atomic_amount(intval($quote['total_cents'] ?? 0)),
            ];
        }
        return $contract;
    }

    private static function payment_contract_hash($contract) {
        return hash('sha256', wp_json_encode($contract));
    }

    private static function x402_payment_required_document($quote) {
        $currency = strtoupper((string) ($quote['currency'] ?? get_woocommerce_currency()));
        if (!self::x402_quote_configured_for_currency($currency)) {
            return null;
        }
        $quote_id = (string) ($quote['id'] ?? '');
        $quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $checkout_endpoint = rest_url(self::API_NAMESPACE . '/orders');
        $amount_cents = intval($quote['total_cents'] ?? 0);
        return [
            'x402Version' => 2,
            'accepts' => [
                [
                    'scheme' => 'exact',
                    'network' => self::x402_network(),
                    'maxAmountRequired' => self::x402_atomic_amount($amount_cents),
                    'resource' => $checkout_endpoint,
                    'description' => 'AgentCart ShopBridge checkout for merchant quote ' . $quote_id,
                    'mimeType' => 'application/json',
                    'payTo' => self::x402_pay_to(),
                    'asset' => self::x402_asset(),
                    'maxTimeoutSeconds' => self::x402_max_timeout_seconds(),
                    'extra' => [
                        'name' => self::x402_asset_symbol(),
                        'version' => '2',
                        'decimals' => self::x402_asset_decimals(),
                        'assetCurrency' => $currency,
                        'merchantId' => self::merchant()['id'],
                        'merchantQuoteId' => $quote_id,
                        'quoteHash' => $quote_hash,
                        'checkoutEndpoint' => $checkout_endpoint,
                        'verifierRequired' => true,
                    ],
                ],
            ],
            'error' => 'PAYMENT-SIGNATURE header or quote-bound payment_receipt is required',
        ];
    }

    private static function x402_atomic_amount($amount_cents) {
        $amount_cents = max(0, intval($amount_cents));
        $zeros = str_repeat('0', max(0, self::x402_asset_decimals() - 2));
        $value = (string) $amount_cents . $zeros;
        $value = ltrim($value, '0');
        return $value === '' ? '0' : $value;
    }

    private static function x402_header_value($document) {
        return base64_encode(wp_json_encode($document, JSON_UNESCAPED_SLASHES)); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_encode -- x402 transports the payment document as a base64 HTTP header value, not obfuscated code.
    }

    private static function x402_unavailable_reason($quote = null) {
        $currency = strtoupper((string) (($quote['currency'] ?? null) ?: get_woocommerce_currency()));
        $missing = [];
        if (self::payment_verifier_url() === '') {
            $missing[] = 'payment_verifier';
        }
        if (self::x402_network() === '') {
            $missing[] = 'x402_network';
        }
        if (self::x402_asset() === '') {
            $missing[] = 'x402_asset';
        }
        if (self::x402_pay_to() === '') {
            $missing[] = 'x402_pay_to';
        }
        if ($currency !== strtoupper(self::x402_asset_currency())) {
            $missing[] = 'quote_currency_' . strtolower($currency) . '_does_not_match_x402_asset_currency_' . strtolower(self::x402_asset_currency());
        }
        return implode(',', $missing);
    }

    private static function delivery_window($min_days, $max_days) {
        $earliest = gmdate('Y-m-d', strtotime('+' . intval($min_days) . ' days'));
        $latest = gmdate('Y-m-d', strtotime('+' . intval($max_days) . ' days'));
        return [
            'earliest_date' => $earliest,
            'latest_date' => $latest,
            'label' => intval($min_days) . '-' . intval($max_days) . ' business days',
            'source' => 'merchant_estimate',
        ];
    }

    private static function payment_verifier_url() {
        if (defined('AGENTCART_PAYMENT_VERIFIER_URL')) {
            $value = trim((string) AGENTCART_PAYMENT_VERIFIER_URL);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::PAYMENT_VERIFIER_URL_OPTION, ''));
    }

    private static function payment_verifier_token() {
        if (defined('AGENTCART_PAYMENT_VERIFIER_TOKEN')) {
            $value = trim((string) AGENTCART_PAYMENT_VERIFIER_TOKEN);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::PAYMENT_VERIFIER_TOKEN_OPTION, ''));
    }

    private static function x402_network() {
        if (defined('AGENTCART_X402_NETWORK')) {
            $value = trim((string) AGENTCART_X402_NETWORK);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::X402_NETWORK_OPTION, ''));
    }

    private static function x402_asset() {
        if (defined('AGENTCART_X402_ASSET')) {
            $value = trim((string) AGENTCART_X402_ASSET);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::X402_ASSET_OPTION, ''));
    }

    private static function x402_asset_symbol() {
        if (defined('AGENTCART_X402_ASSET_SYMBOL')) {
            $value = trim((string) AGENTCART_X402_ASSET_SYMBOL);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::X402_ASSET_SYMBOL_OPTION, 'USDC')) ?: 'USDC';
    }

    private static function x402_asset_decimals() {
        if (defined('AGENTCART_X402_ASSET_DECIMALS')) {
            return self::sanitize_x402_asset_decimals_setting(AGENTCART_X402_ASSET_DECIMALS);
        }
        return self::sanitize_x402_asset_decimals_setting(get_option(self::X402_ASSET_DECIMALS_OPTION, 6));
    }

    private static function x402_asset_currency() {
        if (defined('AGENTCART_X402_ASSET_CURRENCY')) {
            $value = self::sanitize_currency_code_setting((string) AGENTCART_X402_ASSET_CURRENCY);
            if ($value !== '') {
                return $value;
            }
        }
        $stored = self::sanitize_currency_code_setting((string) get_option(self::X402_ASSET_CURRENCY_OPTION, ''));
        return $stored !== '' ? $stored : strtoupper((string) get_woocommerce_currency());
    }

    private static function x402_pay_to() {
        if (defined('AGENTCART_X402_PAY_TO')) {
            $value = trim((string) AGENTCART_X402_PAY_TO);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::X402_PAY_TO_OPTION, ''));
    }

    private static function x402_facilitator_url() {
        if (defined('AGENTCART_X402_FACILITATOR_URL')) {
            $value = trim((string) AGENTCART_X402_FACILITATOR_URL);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::X402_FACILITATOR_URL_OPTION, ''));
    }

    private static function x402_max_timeout_seconds() {
        if (defined('AGENTCART_X402_MAX_TIMEOUT_SECONDS')) {
            return self::sanitize_x402_timeout_setting(AGENTCART_X402_MAX_TIMEOUT_SECONDS);
        }
        return self::sanitize_x402_timeout_setting(get_option(self::X402_MAX_TIMEOUT_SECONDS_OPTION, 300));
    }

    private static function checkout_mode() {
        if (defined('AGENTCART_CHECKOUT_MODE')) {
            $value = self::sanitize_checkout_mode_setting((string) AGENTCART_CHECKOUT_MODE);
            if ($value !== '') {
                return $value;
            }
        }
        return self::sanitize_checkout_mode_setting((string) get_option(self::CHECKOUT_MODE_OPTION, 'trusted_token_or_verifier'));
    }

    private static function signed_request_mode() {
        if (defined('AGENTCART_SIGNED_REQUEST_MODE')) {
            $value = self::sanitize_signed_request_mode_setting((string) AGENTCART_SIGNED_REQUEST_MODE);
            if ($value !== '') {
                return $value;
            }
        }
        return self::sanitize_signed_request_mode_setting((string) get_option(self::SIGNED_REQUEST_MODE_OPTION, 'off'));
    }

    private static function signed_request_secret() {
        $active_key = self::signed_request_active_key();
        if ($active_key && self::signed_request_key_alg($active_key) === 'hmac-sha256') {
            return (string) ($active_key['secret'] ?? '');
        }
        $keys = self::signed_request_keys();
        foreach ($keys as $key) {
            if (self::signed_request_key_alg($key) === 'hmac-sha256') {
                return (string) ($key['secret'] ?? '');
            }
        }
        return trim((string) get_option(self::SIGNED_REQUEST_SECRET_OPTION, ''));
    }

    private static function signed_request_public_key() {
        if (defined('AGENTCART_SIGNED_REQUEST_PUBLIC_KEY')) {
            return self::normalize_signed_request_public_key((string) AGENTCART_SIGNED_REQUEST_PUBLIC_KEY);
        }
        return self::normalize_signed_request_public_key((string) get_option(self::SIGNED_REQUEST_PUBLIC_KEY_OPTION, ''));
    }

    private static function normalize_signed_request_public_key($value) {
        $value = trim(str_replace(["\r\n", "\r"], "\n", (string) $value));
        if ($value === '') {
            return '';
        }
        if (strpos($value, '-----BEGIN PUBLIC KEY-----') === false || strpos($value, '-----END PUBLIC KEY-----') === false) {
            return '';
        }
        return $value;
    }

    private static function signed_request_keys() {
        $keys = [];
        $public_key = self::signed_request_public_key();
        if ($public_key !== '') {
            $keys[] = self::signed_request_public_key_record($public_key);
        }

        if (defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
            $secret = trim((string) AGENTCART_SIGNED_REQUEST_SECRET);
            if ($secret === '') {
                return $keys;
            }
            $keys[] = [
                'id' => 'wp-config',
                'alg' => 'hmac-sha256',
                'secret' => $secret,
                'state' => 'active',
                'created_at' => '',
                'retire_after' => null,
                'source' => 'wp-config',
            ];
            return $keys;
        }

        $stored = get_option(self::SIGNED_REQUEST_KEYS_OPTION, []);
        $hmac_keys = self::sanitize_signed_request_keys($stored);
        $hmac_keys = self::prune_expired_signed_request_keys($hmac_keys);
        if ($hmac_keys) {
            $keys = array_merge($keys, $hmac_keys);
            return $keys;
        }

        $legacy_secret = trim((string) get_option(self::SIGNED_REQUEST_SECRET_OPTION, ''));
        if ($legacy_secret === '') {
            return $keys;
        }
        $legacy_key = self::signed_request_key_record($legacy_secret, 'active', null, 'legacy-option', 'legacy');
        update_option(self::SIGNED_REQUEST_KEYS_OPTION, [$legacy_key], false);
        $keys[] = $legacy_key;
        return $keys;
    }

    private static function sanitize_signed_request_keys($stored) {
        if (!is_array($stored)) {
            return [];
        }

        $keys = [];
        foreach ($stored as $record) {
            if (!is_array($record)) {
                continue;
            }
            $secret = trim(sanitize_text_field((string) ($record['secret'] ?? '')));
            if ($secret === '') {
                continue;
            }
            $state = sanitize_key((string) ($record['state'] ?? 'active'));
            if (!in_array($state, ['active', 'retiring'], true)) {
                $state = 'active';
            }
            $id = sanitize_key((string) ($record['id'] ?? ''));
            if ($id === '') {
                $id = 'sig_' . substr(hash('sha256', $secret), 0, 16);
            }
            $retire_after = $record['retire_after'] ?? null;
            $retire_after = $retire_after === null ? null : sanitize_text_field((string) $retire_after);
            $source = sanitize_key((string) ($record['source'] ?? 'admin'));

            $keys[] = [
                'id' => $id,
                'alg' => 'hmac-sha256',
                'secret' => $secret,
                'state' => $state,
                'created_at' => sanitize_text_field((string) ($record['created_at'] ?? '')),
                'retire_after' => $retire_after ?: null,
                'source' => $source ?: 'admin',
            ];
        }
        return $keys;
    }

    private static function prune_expired_signed_request_keys($keys) {
        $now = time();
        $changed = false;
        $kept = [];
        foreach ($keys as $key) {
            if (($key['state'] ?? '') === 'retiring' && !empty($key['retire_after'])) {
                $retire_after = strtotime((string) $key['retire_after']);
                if ($retire_after && $retire_after < $now) {
                    $changed = true;
                    continue;
                }
            }
            $kept[] = $key;
        }
        if ($changed && !defined('AGENTCART_SIGNED_REQUEST_SECRET')) {
            update_option(self::SIGNED_REQUEST_KEYS_OPTION, $kept, false);
        }
        return $kept;
    }

    private static function create_initial_signed_request_key() {
        return self::store_single_signed_request_key(self::generate_signed_request_secret(), 'admin');
    }

    private static function store_single_signed_request_key($secret, $source = 'admin') {
        $key = self::signed_request_key_record($secret, 'active', null, $source);
        update_option(self::SIGNED_REQUEST_KEYS_OPTION, [$key], false);
        return $key;
    }

    private static function rotate_signed_request_key() {
        $retire_after = gmdate('Y-m-d\TH:i:s\Z', time() + self::SIGNED_REQUEST_KEY_RETIREMENT_SECONDS);
        $keys = [];
        foreach (self::signed_request_keys() as $key) {
            $key['state'] = 'retiring';
            $key['retire_after'] = $retire_after;
            $keys[] = $key;
        }

        $new_key = self::signed_request_key_record(self::generate_signed_request_secret(), 'active', null, 'admin');
        array_unshift($keys, $new_key);
        update_option(self::SIGNED_REQUEST_KEYS_OPTION, $keys, false);
        update_option(self::SIGNED_REQUEST_SECRET_OPTION, (string) ($new_key['secret'] ?? ''), false);
        return $new_key;
    }

    private static function add_signed_request_key() {
        $keys = self::signed_request_keys();
        $new_key = self::signed_request_key_record(self::generate_signed_request_secret(), 'active', null, 'admin');
        array_unshift($keys, $new_key);
        update_option(self::SIGNED_REQUEST_KEYS_OPTION, $keys, false);
        update_option(self::SIGNED_REQUEST_SECRET_OPTION, (string) ($new_key['secret'] ?? ''), false);
        return $new_key;
    }

    private static function revoke_retiring_signed_request_keys() {
        $keys = self::signed_request_keys();
        $kept = [];
        $removed = 0;
        foreach ($keys as $key) {
            if (($key['state'] ?? '') === 'retiring') {
                $removed++;
                continue;
            }
            $kept[] = $key;
        }
        update_option(self::SIGNED_REQUEST_KEYS_OPTION, $kept, false);
        return $removed;
    }

    private static function signed_request_key_record($secret, $state = 'active', $retire_after = null, $source = 'admin', $id = '') {
        $secret = trim((string) $secret);
        return [
            'id' => $id !== '' ? sanitize_key($id) : 'sig_' . substr(hash('sha256', $secret . '|' . wp_generate_uuid4()), 0, 16),
            'alg' => 'hmac-sha256',
            'secret' => $secret,
            'state' => in_array($state, ['active', 'retiring'], true) ? $state : 'active',
            'created_at' => self::current_registry_timestamp(),
            'retire_after' => $retire_after,
            'source' => sanitize_key((string) $source) ?: 'admin',
        ];
    }

    private static function signed_request_public_key_record($public_key) {
        $public_key = self::normalize_signed_request_public_key($public_key);
        return [
            'id' => 'sig_rsa_' . substr(hash('sha256', $public_key), 0, 16),
            'alg' => 'rsa-sha256',
            'public_key' => $public_key,
            'state' => 'active',
            'created_at' => '',
            'retire_after' => null,
            'source' => defined('AGENTCART_SIGNED_REQUEST_PUBLIC_KEY') ? 'wp-config-public-key' : 'settings-public-key',
        ];
    }

    private static function generate_signed_request_secret() {
        return wp_generate_password(64, false, false);
    }

    private static function signed_request_active_key() {
        foreach (self::signed_request_keys() as $key) {
            if (($key['state'] ?? '') === 'active') {
                return $key;
            }
        }
        return null;
    }

    private static function signed_request_active_key_count() {
        $count = 0;
        foreach (self::signed_request_keys() as $key) {
            if (($key['state'] ?? '') === 'active') {
                $count++;
            }
        }
        return $count;
    }

    private static function signed_request_retiring_key_count() {
        $count = 0;
        foreach (self::signed_request_keys() as $key) {
            if (($key['state'] ?? '') === 'retiring') {
                $count++;
            }
        }
        return $count;
    }

    private static function signed_request_active_key_id() {
        $key = self::signed_request_active_key();
        return $key ? (string) ($key['id'] ?? '') : '';
    }

    private static function signed_request_public_key_summaries() {
        $summaries = [];
        foreach (self::signed_request_keys() as $key) {
            $summaries[] = [
                'id' => (string) ($key['id'] ?? ''),
                'alg' => self::signed_request_key_alg($key),
                'state' => (string) ($key['state'] ?? ''),
                'retire_after' => $key['retire_after'] ?? null,
                'source' => (string) ($key['source'] ?? 'admin'),
                'public_key_fingerprint' => !empty($key['public_key']) ? hash('sha256', (string) $key['public_key']) : '',
            ];
        }
        return $summaries;
    }

    private static function signed_request_key_status_summary() {
        $active = self::signed_request_active_key_count();
        $retiring = self::signed_request_retiring_key_count();
        $asymmetric = self::signed_request_asymmetric_key_count();
        $active_id = self::signed_request_active_key_id();
        $days = (int) ceil(self::SIGNED_REQUEST_KEY_RETIREMENT_SECONDS / 86400);
        $summary = sprintf('Active keys: %d. Asymmetric keys: %d. Retiring keys: %d. Retirement window: %d days.', $active, $asymmetric, $retiring, $days);
        if ($active_id !== '') {
            $summary .= ' Active signer: ' . $active_id . '.';
        }
        return $summary;
    }

    private static function signed_request_asymmetric_key_count() {
        $count = 0;
        foreach (self::signed_request_keys() as $key) {
            if (self::signed_request_key_alg($key) === 'rsa-sha256') {
                $count++;
            }
        }
        return $count;
    }

    private static function signed_request_supported_signature_schemes() {
        $schemes = [];
        foreach (self::signed_request_keys() as $key) {
            $scheme = self::signed_request_key_alg($key) === 'rsa-sha256'
                ? 'agentcart-rsa-sha256-v1'
                : 'agentcart-hmac-sha256-v1';
            if (!in_array($scheme, $schemes, true)) {
                $schemes[] = $scheme;
            }
        }
        return $schemes ?: ['agentcart-hmac-sha256-v1'];
    }

    private static function signed_request_preferred_signature_scheme() {
        $active = self::signed_request_active_key();
        if ($active && self::signed_request_key_alg($active) === 'rsa-sha256') {
            return 'agentcart-rsa-sha256-v1';
        }
        return 'agentcart-hmac-sha256-v1';
    }

    private static function signed_request_profile_configured() {
        return self::signed_request_mode() !== 'off' && !empty(self::signed_request_keys());
    }

    private static function signed_request_required_buckets() {
        $buckets = [];
        foreach (['quote', 'checkout', 'order_status', 'refund', 'cancellation'] as $bucket) {
            if (self::signed_request_required_for_bucket($bucket)) {
                $buckets[] = $bucket;
            }
        }
        return $buckets;
    }

    private static function signed_request_header_names() {
        return [
            'signed_method' => 'X-AgentCart-Signed-Method',
            'signed_path' => 'X-AgentCart-Signed-Path',
            'content_digest' => 'X-AgentCart-Content-Digest',
            'nonce' => 'X-AgentCart-Nonce',
            'expires_at' => 'X-AgentCart-Expires-At',
            'signer' => 'X-AgentCart-Signer',
            'signature_alg' => 'X-AgentCart-Signature-Alg',
            'signature' => 'X-AgentCart-Signature',
        ];
    }

    private static function external_verifier_required_for_checkout() {
        return self::checkout_mode() === 'external_verifier_only';
    }

    private static function checkout_mode_label($mode) {
        return $mode === 'external_verifier_only'
            ? 'External verifier only'
            : 'Trusted gateway token or external verifier';
    }

    private static function signed_request_mode_label($mode) {
        $labels = [
            'off' => 'Off',
            'allow' => 'Allow signed requests',
            'require_checkout' => 'Require for checkout',
            'require_mutations' => 'Require for checkout, refunds, and cancellations',
            'require_all_sensitive' => 'Require for quote, checkout, status, refunds, and cancellations',
        ];
        return $labels[$mode] ?? 'Off';
    }

    private static function tempo_recipient() {
        if (defined('AGENTCART_TEMPO_RECIPIENT_ADDRESS')) {
            $value = trim((string) AGENTCART_TEMPO_RECIPIENT_ADDRESS);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::TEMPO_RECIPIENT_OPTION, ''));
    }

    private static function tempo_network() {
        if (defined('AGENTCART_TEMPO_NETWORK')) {
            $value = trim((string) AGENTCART_TEMPO_NETWORK);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::TEMPO_NETWORK_OPTION, 'testnet')) ?: 'testnet';
    }

    private static function tempo_settlement_asset() {
        $network = self::tempo_network();
        if ($network === 'mainnet') {
            return [
                'asset' => 'USDC.e',
                'denomination' => 'USD stablecoin',
                'token_standard' => 'TIP-20',
                'network' => 'mainnet',
            ];
        }
        return [
            'asset' => 'pathUSD',
            'denomination' => 'USD stablecoin',
            'token_standard' => 'TIP-20',
            'network' => $network ?: 'testnet',
            'token_address' => '0x20c0000000000000000000000000000000000000', // phpcs:ignore PHPCompatibility.Miscellaneous.ValidIntegers.HexNumericStringFound -- Token address is an opaque chain address string and PHP 8.1+ is required.
        ];
    }

    private static function stripe_profile_id() {
        if (defined('AGENTCART_STRIPE_PROFILE_ID')) {
            $value = trim((string) AGENTCART_STRIPE_PROFILE_ID);
            if ($value !== '') {
                return $value;
            }
        }
        return trim((string) get_option(self::STRIPE_PROFILE_ID_OPTION, ''));
    }

    private static function payment_rails() {
        return [
            [
                'id' => 'tempo-mpp',
                'type' => 'stablecoin',
                'configured' => self::tempo_recipient() !== '' || self::payment_verifier_url() !== '',
                'network' => self::tempo_network(),
                'recipient_configured' => self::tempo_recipient() !== '',
                'settlement_asset' => self::tempo_settlement_asset(),
                'refunds_require_verifier_for_real_funds' => true,
            ],
            [
                'id' => 'stripe-card-mpp',
                'type' => 'card',
                'configured' => self::stripe_profile_id() !== '' && self::payment_verifier_url() !== '',
                'network_id' => self::stripe_profile_id(),
                'requires_stripe_machine_payments' => true,
                'refunds_use_stripe_or_verifier' => true,
            ],
        ];
    }

    private static function support_email() {
        if (defined('AGENTCART_SUPPORT_EMAIL')) {
            $value = sanitize_email((string) AGENTCART_SUPPORT_EMAIL);
            if ($value !== '') {
                return $value;
            }
        }
        return sanitize_email((string) get_option(self::SUPPORT_EMAIL_OPTION, ''));
    }

    private static function terms_url() {
        return wc_get_page_permalink('terms') ?: home_url('/terms');
    }

    private static function returns_url() {
        if (defined('AGENTCART_RETURNS_URL')) {
            $value = esc_url_raw((string) AGENTCART_RETURNS_URL);
            if ($value !== '') {
                return $value;
            }
        }
        $configured = esc_url_raw((string) get_option(self::RETURNS_URL_OPTION, ''));
        return $configured !== '' ? $configured : home_url('/returns');
    }

    private static function substitution_policy() {
        if (defined('AGENTCART_SUBSTITUTION_POLICY')) {
            return self::sanitize_substitution_policy_setting((string) AGENTCART_SUBSTITUTION_POLICY);
        }
        return self::sanitize_substitution_policy_setting((string) get_option(self::SUBSTITUTION_POLICY_OPTION, 'approval_required'));
    }

    private static function cancellation_window_minutes() {
        if (defined('AGENTCART_CANCELLATION_WINDOW_MINUTES')) {
            return self::sanitize_cancellation_window_minutes_setting(AGENTCART_CANCELLATION_WINDOW_MINUTES);
        }
        return self::sanitize_cancellation_window_minutes_setting(get_option(self::CANCELLATION_WINDOW_MINUTES_OPTION, 30));
    }

    private static function merchant_policy_summary() {
        $policy = self::merchant_policy();
        $substitutions = $policy['substitutions']['label'];
        $cancellation = intval($policy['cancellations']['request_window_minutes']);
        return $substitutions . '; cancellation requests advertised for ' . $cancellation . ' minutes after checkout.';
    }

    private static function merchant_policy() {
        $substitution_policy = self::substitution_policy();
        $substitution_labels = [
            'approval_required' => 'Substitutions require buyer approval.',
            'not_allowed' => 'Substitutions are not allowed by default.',
            'merchant_allowed' => 'Merchant may substitute comparable items.',
        ];
        $cancellation_minutes = self::cancellation_window_minutes();
        return [
            'source' => 'woocommerce_shopbridge_settings',
            'terms_url' => self::terms_url(),
            'returns_url' => self::returns_url(),
            'refunds' => [
                'requires_merchant_review' => true,
                'rail_refund_requires_verifier' => true,
                'policy_url' => self::returns_url(),
                'note' => 'Refund requests require merchant review and real-funds refunds require the configured payment verifier.',
            ],
            'cancellations' => [
                'buyer_request_allowed' => $cancellation_minutes > 0,
                'request_window_minutes' => $cancellation_minutes,
                'requires_merchant_review' => true,
                'policy_url' => self::returns_url(),
                'note' => $cancellation_minutes > 0
                    ? 'Buyer agents may surface a cancellation request during the advertised window; the merchant still decides before fulfillment.'
                    : 'No self-service cancellation window is advertised. Contact merchant support.',
            ],
            'substitutions' => [
                'policy' => $substitution_policy,
                'label' => $substitution_labels[$substitution_policy] ?? $substitution_labels['approval_required'],
                'requires_buyer_approval' => $substitution_policy === 'approval_required',
                'not_allowed' => $substitution_policy === 'not_allowed',
                'merchant_may_substitute' => $substitution_policy === 'merchant_allowed',
                'stricter_item_policy_wins' => true,
            ],
        ];
    }

    private static function shipping_countries() {
        if (!class_exists('WooCommerce') || !WC() || !WC()->countries) {
            return ['DE'];
        }
        $countries = [];
        if (method_exists(WC()->countries, 'get_shipping_countries')) {
            $countries = WC()->countries->get_shipping_countries();
        }
        if (!$countries && method_exists(WC()->countries, 'get_allowed_countries')) {
            $countries = WC()->countries->get_allowed_countries();
        }
        if (!$countries) {
            $base = WC()->countries->get_base_country();
            $countries = [$base ?: 'DE' => true];
        }
        return array_values(array_unique(array_map('strtoupper', array_keys($countries))));
    }

    private static function shipping_country_names() {
        if (!class_exists('WooCommerce') || !WC() || !WC()->countries) {
            return ['DE' => 'Germany'];
        }
        $countries = method_exists(WC()->countries, 'get_shipping_countries') ? WC()->countries->get_shipping_countries() : [];
        if (!$countries && method_exists(WC()->countries, 'get_allowed_countries')) {
            $countries = WC()->countries->get_allowed_countries();
        }
        if (!$countries) {
            return ['DE' => 'Germany'];
        }
        $result = [];
        foreach ($countries as $code => $name) {
            $result[strtoupper((string) $code)] = (string) $name;
        }
        return $result;
    }

    private static function merchant() {
        return [
            'id' => self::merchant_id(),
            'name' => get_bloginfo('name') ?: 'WooCommerce Demo Shop',
            'merchant_of_record' => [
                'name' => get_bloginfo('name') ?: 'WooCommerce Demo Shop',
                'country' => WC()->countries->get_base_country() ?: 'DE',
                'vat_id' => get_option('woocommerce_store_vat_number') ?: 'demo-vat',
                'support_email' => self::support_email(),
            ],
            'terms_url' => self::terms_url(),
            'returns_url' => self::returns_url(),
            'merchant_policy' => self::merchant_policy(),
        ];
    }

    private static function merchant_id() {
        if (defined('AGENTCART_MERCHANT_ID')) {
            $value = self::sanitize_merchant_id_setting((string) AGENTCART_MERCHANT_ID);
            if ($value !== '') {
                return $value;
            }
        }
        $value = self::sanitize_merchant_id_setting((string) get_option(self::MERCHANT_ID_OPTION, ''));
        return $value !== '' ? $value : 'woocommerce-demo-shop';
    }

    private static function agentcart_enabled_meta_query() {
        return [
            [
                'key' => self::PRODUCT_ENABLED_META,
                'value' => 'yes',
                'compare' => '=',
            ],
        ];
    }

    private static function product_exposure_mode() {
        if (defined('AGENTCART_PRODUCT_EXPOSURE_MODE')) {
            return self::sanitize_product_exposure_mode_setting((string) AGENTCART_PRODUCT_EXPOSURE_MODE);
        }
        return self::sanitize_product_exposure_mode_setting((string) get_option(self::PRODUCT_EXPOSURE_MODE_OPTION, 'manual'));
    }

    private static function product_exposure_tag() {
        if (defined('AGENTCART_PRODUCT_EXPOSURE_TAG')) {
            $tag = sanitize_title((string) AGENTCART_PRODUCT_EXPOSURE_TAG);
        } else {
            $tag = sanitize_title((string) get_option(self::PRODUCT_EXPOSURE_TAG_OPTION, 'agentcart-safe'));
        }
        return $tag !== '' ? $tag : 'agentcart-safe';
    }

    private static function product_exposure_categories() {
        return self::slug_list_from_setting(self::PRODUCT_EXPOSURE_CATEGORIES_OPTION, 'AGENTCART_PRODUCT_EXPOSURE_CATEGORIES');
    }

    private static function product_blocked_categories() {
        return self::slug_list_from_setting(self::PRODUCT_BLOCKED_CATEGORIES_OPTION, 'AGENTCART_PRODUCT_BLOCKED_CATEGORIES');
    }

    private static function slug_list_from_setting($option, $constant) {
        if (defined($constant)) {
            $raw = (string) constant($constant);
        } else {
            $raw = (string) get_option($option, '');
        }
        $value = self::sanitize_slug_list_setting($raw);
        return $value === '' ? [] : explode(',', $value);
    }

    private static function product_exposure_mode_label($mode = null) {
        $mode = $mode ?: self::product_exposure_mode();
        if ($mode === 'tag') {
            return 'WooCommerce tag';
        }
        if ($mode === 'category') {
            return 'WooCommerce categories';
        }
        if ($mode === 'all') {
            return 'all published simple products';
        }
        return 'manual product opt-in';
    }

    private static function agentcart_product_query_args() {
        $args = [
            'status' => 'publish',
            'type' => ['simple'],
        ];
        $mode = self::product_exposure_mode();
        if ($mode === 'manual') {
            $args['meta_query'] = self::agentcart_enabled_meta_query(); // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_query -- Manual product exposure intentionally filters by plugin product meta.
        } elseif ($mode === 'tag') {
            $args['tag'] = [self::product_exposure_tag()];
        } elseif ($mode === 'category') {
            $categories = self::product_exposure_categories();
            if (!$categories) {
                $args['include'] = [0];
            } else {
                $args['category'] = $categories;
            }
        }
        return $args;
    }

    private static function is_product_agentcart_enabled(WC_Product $product) {
        return self::product_matches_exposure_mode($product) && !self::is_product_agentcart_blocked($product);
    }

    private static function product_matches_exposure_mode(WC_Product $product) {
        if ($product->get_status() !== 'publish' || $product->get_type() !== 'simple') {
            return false;
        }
        $mode = self::product_exposure_mode();
        if ($mode === 'all') {
            return true;
        }
        if ($mode === 'tag') {
            return has_term(self::product_exposure_tag(), 'product_tag', $product->get_id());
        }
        if ($mode === 'category') {
            return self::product_has_category_slug($product, self::product_exposure_categories());
        }
        return $product->get_meta(self::PRODUCT_ENABLED_META, true) === 'yes';
    }

    private static function is_product_agentcart_blocked(WC_Product $product) {
        return !empty(self::product_agentcart_block_reasons($product));
    }

    private static function product_category_slugs(WC_Product $product) {
        $slugs = [];
        foreach ($product->get_category_ids() as $category_id) {
            $term = get_term($category_id, 'product_cat');
            if ($term && !is_wp_error($term)) {
                foreach ([$term->slug, $term->name] as $value) {
                    $slug = sanitize_title((string) $value);
                    if ($slug !== '' && !in_array($slug, $slugs, true)) {
                        $slugs[] = $slug;
                    }
                }
            }
        }
        return $slugs;
    }

    private static function product_has_category_slug(WC_Product $product, $category_slugs) {
        if (!$category_slugs) {
            return false;
        }
        return (bool) array_intersect(self::product_category_slugs($product), $category_slugs);
    }

    private static function product_blocked_category_matches(WC_Product $product) {
        return array_values(array_intersect(self::product_category_slugs($product), self::product_blocked_categories()));
    }

    private static function product_agentcart_block_reasons(WC_Product $product) {
        $reasons = [];
        if ($product->get_meta(self::PRODUCT_BLOCKED_META, true) === 'yes') {
            $reasons[] = 'product_checkout_blocked';
        }
        foreach (self::product_blocked_category_matches($product) as $slug) {
            $reasons[] = 'blocked_category:' . $slug;
        }
        foreach (self::product_restricted_goods_block_matches($product) as $code) {
            $reasons[] = 'restricted_goods:' . $code;
        }
        return array_values(array_unique($reasons));
    }

    private static function product_restricted_goods_block_matches(WC_Product $product) {
        if ($product->get_meta(self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META, true) === 'yes') {
            return [];
        }
        $matches = [];
        foreach (self::product_restricted_goods($product) as $flag) {
            if (is_array($flag) && !empty($flag['code'])) {
                $matches[] = sanitize_key((string) $flag['code']);
            }
        }
        return array_values(array_unique(array_filter($matches)));
    }

    private static function product_exposure_preview_result() {
        $stored = get_option(self::PRODUCT_EXPOSURE_PREVIEW_OPTION, []);
        return is_array($stored) ? $stored : [];
    }

    private static function product_exposure_snapshot_result() {
        $stored = get_option(self::PRODUCT_EXPOSURE_SNAPSHOT_OPTION, []);
        return is_array($stored) ? $stored : [];
    }

    private static function product_exposure_snapshot_summary($snapshot = null) {
        $snapshot = is_array($snapshot) ? $snapshot : self::product_exposure_snapshot_result();
        if (!$snapshot) {
            return [
                'configured' => false,
                'saved_at' => '',
                'catalog_hash' => '',
                'included_count' => 0,
            ];
        }
        return [
            'configured' => true,
            'saved_at' => (string) ($snapshot['saved_at'] ?? ''),
            'settings_fingerprint' => (string) ($snapshot['settings_fingerprint'] ?? ''),
            'catalog_hash' => (string) ($snapshot['catalog_hash'] ?? ''),
            'included_count' => intval($snapshot['included_count'] ?? 0),
        ];
    }

    private static function product_exposure_settings_fingerprint() {
        return self::canonical_json_hash([
            'mode' => self::product_exposure_mode(),
            'tag' => self::product_exposure_tag(),
            'categories' => self::product_exposure_categories(),
            'blocked_categories' => self::product_blocked_categories(),
        ]);
    }

    private static function build_product_exposure_preview() {
        $checked_at = self::current_registry_timestamp();
        if (!function_exists('wc_get_products')) {
            return [
                'schema' => 'agentcart.shopbridge.product_exposure_preview.v1',
                'state' => 'failed',
                'checked_at' => $checked_at,
                'message' => 'WooCommerce product APIs are not available.',
            ];
        }
        $products = wc_get_products([
            'status' => 'publish',
            'type' => ['simple'],
            'limit' => -1,
            'return' => 'objects',
            'orderby' => 'title',
            'order' => 'ASC',
        ]);
        $included_products = [];
        $blocked_products = [];
        $not_matching_count = 0;
        foreach ($products as $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $matches = self::product_matches_exposure_mode($product);
            if (!$matches) {
                $not_matching_count++;
                continue;
            }
            $blocked_reasons = self::product_agentcart_block_reasons($product);
            $row = self::product_exposure_preview_row($product, $blocked_reasons);
            if ($blocked_reasons) {
                $blocked_products[] = $row;
            } else {
                $included_products[] = $row;
            }
        }
        $preview = [
            'schema' => 'agentcart.shopbridge.product_exposure_preview.v1',
            'state' => 'passed',
            'checked_at' => $checked_at,
            'settings_fingerprint' => self::product_exposure_settings_fingerprint(),
            'mode' => self::product_exposure_mode(),
            'mode_label' => self::product_exposure_mode_label(),
            'tag' => self::product_exposure_tag(),
            'categories' => self::product_exposure_categories(),
            'blocked_categories' => self::product_blocked_categories(),
            'published_simple_count' => count($products),
            'included_count' => count($included_products),
            'blocked_count' => count($blocked_products),
            'not_matching_count' => $not_matching_count,
            'included_products' => $included_products,
            'blocked_products' => $blocked_products,
            'preview_limit' => self::PRODUCT_EXPOSURE_PREVIEW_LIMIT,
        ];
        $preview['catalog_snapshot'] = self::product_exposure_snapshot_summary();
        $preview['catalog_diff'] = self::catalog_snapshot_diff(
            self::product_exposure_snapshot_result(),
            self::product_exposure_snapshot_from_preview($preview)
        );
        return $preview;
    }

    private static function product_exposure_preview_row(WC_Product $product, $blocked_reasons) {
        $stock_quantity = $product->managing_stock() && $product->get_stock_quantity() !== null
            ? intval($product->get_stock_quantity())
            : null;
        return [
            'product_id' => 'woo_' . $product->get_id(),
            'source_product_id' => $product->get_id(),
            'title' => wp_strip_all_tags($product->get_name()),
            'sku' => $product->get_sku() ?: 'WOO-' . $product->get_id(),
            'edit_url' => admin_url('post.php?post=' . $product->get_id() . '&action=edit'),
            'exposure_source' => self::product_exposure_match_source($product),
            'category_slugs' => self::product_category_slugs($product),
            'shipping_countries' => self::product_shipping_countries($product),
            'stock_status' => $product->get_stock_status(),
            'stock_quantity' => $stock_quantity,
            'price_cents' => self::cents((float) wc_get_price_including_tax($product, ['qty' => 1])),
            'currency' => get_woocommerce_currency(),
            'max_quantity' => self::product_max_quantity($product),
            'blocked_reasons' => array_values(array_map('strval', $blocked_reasons)),
            'restricted_goods' => self::product_restricted_goods($product),
            'restricted_goods_override' => $product->get_meta(self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META, true) === 'yes',
        ];
    }

    private static function product_exposure_snapshot_from_preview($preview) {
        $preview = is_array($preview) ? $preview : [];
        $included_products = is_array($preview['included_products'] ?? null) ? $preview['included_products'] : [];
        $products = [];
        foreach ($included_products as $row) {
            if (!is_array($row)) {
                continue;
            }
            $product = self::catalog_snapshot_product_from_preview_row($row);
            if (empty($product['product_id'])) {
                continue;
            }
            $products[] = $product;
        }
        usort($products, static function ($left, $right) {
            return strcmp((string) ($left['product_id'] ?? ''), (string) ($right['product_id'] ?? ''));
        });
        return [
            'schema' => 'agentcart.shopbridge.catalog_snapshot.v1',
            'saved_at' => self::current_registry_timestamp(),
            'settings_fingerprint' => (string) ($preview['settings_fingerprint'] ?? self::product_exposure_settings_fingerprint()),
            'catalog_hash' => self::canonical_json_hash($products),
            'included_count' => count($products),
            'products' => $products,
        ];
    }

    private static function catalog_snapshot_product_from_preview_row($row) {
        $row = is_array($row) ? $row : [];
        $product = [
            'product_id' => sanitize_text_field((string) ($row['product_id'] ?? '')),
            'source_product_id' => intval($row['source_product_id'] ?? 0),
            'title' => sanitize_text_field((string) ($row['title'] ?? '')),
            'sku' => sanitize_text_field((string) ($row['sku'] ?? '')),
            'exposure_source' => sanitize_text_field((string) ($row['exposure_source'] ?? '')),
            'category_slugs' => is_array($row['category_slugs'] ?? null) ? array_values(array_map('sanitize_title', $row['category_slugs'])) : [],
            'shipping_countries' => is_array($row['shipping_countries'] ?? null) ? array_values(array_map('strtoupper', array_map('sanitize_text_field', $row['shipping_countries']))) : [],
            'stock_status' => sanitize_key((string) ($row['stock_status'] ?? '')),
            'stock_quantity' => isset($row['stock_quantity']) ? intval($row['stock_quantity']) : null,
            'price_cents' => intval($row['price_cents'] ?? 0),
            'currency' => strtoupper(sanitize_text_field((string) ($row['currency'] ?? ''))),
            'max_quantity' => intval($row['max_quantity'] ?? 0),
            'restricted_goods_count' => is_array($row['restricted_goods'] ?? null) ? count($row['restricted_goods']) : 0,
            'restricted_goods_override' => !empty($row['restricted_goods_override']),
        ];
        $product['product_hash'] = self::canonical_json_hash($product);
        return $product;
    }

    private static function catalog_snapshot_product_map($snapshot) {
        $snapshot = is_array($snapshot) ? $snapshot : [];
        $products = is_array($snapshot['products'] ?? null) ? $snapshot['products'] : [];
        $map = [];
        foreach ($products as $product) {
            if (!is_array($product) || empty($product['product_id'])) {
                continue;
            }
            $map[(string) $product['product_id']] = $product;
        }
        ksort($map, SORT_STRING);
        return $map;
    }

    private static function catalog_snapshot_diff($baseline, $current) {
        $baseline = is_array($baseline) ? $baseline : [];
        $current = is_array($current) ? $current : [];
        $baseline_map = self::catalog_snapshot_product_map($baseline);
        $current_map = self::catalog_snapshot_product_map($current);
        $added = [];
        $removed = [];
        $changed = [];
        $unchanged = [];

        foreach ($current_map as $product_id => $product) {
            if (!isset($baseline_map[$product_id])) {
                $added[] = self::catalog_snapshot_diff_row('added', $product, null);
                continue;
            }
            if ((string) ($product['product_hash'] ?? '') !== (string) ($baseline_map[$product_id]['product_hash'] ?? '')) {
                $changed[] = self::catalog_snapshot_diff_row('changed', $product, $baseline_map[$product_id]);
            } else {
                $unchanged[] = $product_id;
            }
        }
        foreach ($baseline_map as $product_id => $product) {
            if (!isset($current_map[$product_id])) {
                $removed[] = self::catalog_snapshot_diff_row('removed', $product, null);
            }
        }

        $has_baseline = !empty($baseline);
        $changed_count = count($added) + count($removed) + count($changed);
        return [
            'schema' => 'agentcart.shopbridge.catalog_diff.v1',
            'state' => !$has_baseline ? 'no_snapshot' : ($changed_count > 0 ? 'changed' : 'unchanged'),
            'baseline_saved_at' => (string) ($baseline['saved_at'] ?? ''),
            'baseline_catalog_hash' => (string) ($baseline['catalog_hash'] ?? ''),
            'current_catalog_hash' => (string) ($current['catalog_hash'] ?? ''),
            'added_count' => count($added),
            'removed_count' => count($removed),
            'changed_count' => count($changed),
            'unchanged_count' => count($unchanged),
            'added_products' => $added,
            'removed_products' => $removed,
            'changed_products' => $changed,
        ];
    }

    private static function catalog_snapshot_diff_row($change_type, $product, $baseline_product = null) {
        $product = is_array($product) ? $product : [];
        $baseline_product = is_array($baseline_product) ? $baseline_product : [];
        $changed_fields = [];
        if ($change_type === 'changed') {
            foreach (['title', 'sku', 'exposure_source', 'category_slugs', 'shipping_countries', 'stock_status', 'stock_quantity', 'price_cents', 'currency', 'max_quantity', 'restricted_goods_count', 'restricted_goods_override'] as $field) {
                if (($product[$field] ?? null) !== ($baseline_product[$field] ?? null)) {
                    $changed_fields[] = $field;
                }
            }
        }
        return [
            'change_type' => sanitize_key((string) $change_type),
            'product_id' => (string) ($product['product_id'] ?? ''),
            'title' => (string) ($product['title'] ?? ''),
            'sku' => (string) ($product['sku'] ?? ''),
            'changed_fields' => $changed_fields,
        ];
    }

    private static function catalog_snapshot_diff_rows($diff) {
        $diff = is_array($diff) ? $diff : [];
        $rows = [];
        foreach (['added_products', 'removed_products', 'changed_products'] as $key) {
            $items = is_array($diff[$key] ?? null) ? $diff[$key] : [];
            foreach ($items as $item) {
                if (is_array($item)) {
                    $rows[] = $item;
                }
            }
        }
        return $rows;
    }

    private static function product_exposure_match_source(WC_Product $product) {
        $mode = self::product_exposure_mode();
        if ($mode === 'tag') {
            return 'tag:' . self::product_exposure_tag();
        }
        if ($mode === 'category') {
            $matches = array_values(array_intersect(self::product_category_slugs($product), self::product_exposure_categories()));
            return 'category:' . implode(',', $matches);
        }
        if ($mode === 'all') {
            return 'all_published_simple_products';
        }
        return 'manual_checkbox:' . self::PRODUCT_ENABLED_META;
    }

    private static function product_shipping_countries(WC_Product $product) {
        $stored = self::sanitize_country_list_setting((string) $product->get_meta(self::PRODUCT_SHIPPING_COUNTRIES_META, true));
        return $stored === '' ? self::shipping_countries() : explode(',', $stored);
    }

    private static function product_ships_to_country(WC_Product $product, $country) {
        $country = strtoupper(sanitize_text_field((string) $country));
        $countries = self::product_shipping_countries($product);
        return $country === '' || !$countries || in_array($country, $countries, true);
    }

    private static function product_max_quantity(WC_Product $product) {
        if ($product->is_sold_individually()) {
            return 1;
        }
        $stored = absint($product->get_meta(self::PRODUCT_MAX_QUANTITY_META, true));
        return max(1, min(999, $stored ?: 20));
    }

    private static function quote_recovery_error($code, $message, $quote = null, $merchant_quote_id = '', $reason = 'quote_invalid') {
        return new WP_Error(
            $code,
            $message,
            [
                'status' => 409,
                'merchant_quote_id' => sanitize_text_field((string) $merchant_quote_id),
                'recovery' => self::quote_recovery($reason, $quote, $merchant_quote_id),
            ]
        );
    }

    private static function quote_recovery($reason, $quote = null, $merchant_quote_id = '') {
        $quote = is_array($quote) ? $quote : [];
        return [
            'reason' => sanitize_key((string) $reason),
            'recreate_quote_required' => true,
            'retry_quote_endpoint' => rest_url(self::API_NAMESPACE . '/quote'),
            'checkout_endpoint' => rest_url(self::API_NAMESPACE . '/orders'),
            'reuse_payment_receipt' => false,
            'merchant_quote_id' => sanitize_text_field((string) ($merchant_quote_id ?: ($quote['id'] ?? ''))),
            'quote_hash' => sanitize_text_field((string) ($quote['quote_hash'] ?? '')),
            'expires_at' => sanitize_text_field((string) ($quote['expires_at'] ?? '')),
            'items' => isset($quote['items']) && is_array($quote['items']) ? $quote['items'] : [],
            'ship_to' => isset($quote['ship_to']) && is_array($quote['ship_to']) ? $quote['ship_to'] : null,
            'note' => 'Create a fresh quote before asking for approval or retrying payment.',
        ];
    }

    private static function validate_live_quote_totals_for_checkout($quote, $merchant_quote_id, $validated_items) {
        $quote = is_array($quote) ? $quote : [];
        $cart = self::prepare_quote_cart(self::normalize_address($quote['ship_to'] ?? ['country' => '']));
        if (is_wp_error($cart)) {
            return $cart;
        }
        try {
            foreach ($validated_items as $validated_item) {
                $product = $validated_item[0] ?? null;
                $quantity = intval($validated_item[2] ?? 0);
                if (!($product instanceof WC_Product) || !$cart->add_to_cart($product->get_id(), $quantity)) {
                    return self::quote_recovery_error(
                        'agentcart_quote_product_changed',
                        'WooCommerce can no longer recreate the stored merchant quote.',
                        $quote,
                        $merchant_quote_id,
                        'product_changed'
                    );
                }
            }
            $cart->calculate_shipping();
            $shipping_selection = self::select_shipping_rates_for_cart($cart);
            if (is_wp_error($shipping_selection)) {
                return self::quote_recovery_error(
                    'agentcart_quote_shipping_changed',
                    'WooCommerce shipping can no longer recreate the stored merchant quote.',
                    $quote,
                    $merchant_quote_id,
                    'shipping_changed'
                );
            }
            $cart->calculate_shipping();
            $cart->calculate_totals();
            $current_quote = self::quote_from_cart($cart);
            if (is_wp_error($current_quote)) {
                return self::quote_recovery_error(
                    'agentcart_quote_price_changed',
                    'WooCommerce can no longer calculate the stored merchant quote.',
                    $quote,
                    $merchant_quote_id,
                    'price_changed'
                );
            }
            $current_quote['currency'] = get_woocommerce_currency();
            return self::quote_drift_error($quote, $current_quote, $merchant_quote_id);
        } finally {
            $cart->empty_cart();
        }
    }

    private static function quote_drift_error($quote, $current_quote, $merchant_quote_id) {
        $reason = self::quote_drift_reason($quote, $current_quote);
        if ($reason === '') {
            return true;
        }
        $codes = [
            'currency_changed' => 'agentcart_quote_currency_changed',
            'price_changed' => 'agentcart_quote_price_changed',
            'shipping_changed' => 'agentcart_quote_shipping_changed',
            'tax_changed' => 'agentcart_quote_tax_changed',
            'total_changed' => 'agentcart_quote_total_changed',
        ];
        $labels = [
            'currency_changed' => 'currency',
            'price_changed' => 'product pricing',
            'shipping_changed' => 'shipping',
            'tax_changed' => 'tax',
            'total_changed' => 'total',
        ];
        return new WP_Error(
            $codes[$reason] ?? 'agentcart_quote_total_changed',
            'Stored merchant quote no longer matches current WooCommerce ' . ($labels[$reason] ?? 'total') . '.',
            [
                'status' => 409,
                'merchant_quote_id' => sanitize_text_field((string) $merchant_quote_id),
                'quoted' => self::quote_money_snapshot($quote),
                'current' => self::quote_money_snapshot($current_quote),
                'recovery' => self::quote_recovery($reason, $quote, $merchant_quote_id),
            ]
        );
    }

    private static function quote_drift_reason($quote, $current_quote) {
        if ((string) ($quote['currency'] ?? '') !== (string) ($current_quote['currency'] ?? '')) {
            return 'currency_changed';
        }
        if (self::quote_item_totals_signature($quote['items'] ?? []) !== self::quote_item_totals_signature($current_quote['items'] ?? [])) {
            return 'price_changed';
        }
        if (intval($quote['subtotal_cents'] ?? 0) !== intval($current_quote['subtotal_cents'] ?? 0)) {
            return 'price_changed';
        }
        if (self::quote_shipping_signature($quote['shipping'] ?? []) !== self::quote_shipping_signature($current_quote['shipping'] ?? [])) {
            return 'shipping_changed';
        }
        if (self::quote_vat_signature($quote['vat_lines'] ?? []) !== self::quote_vat_signature($current_quote['vat_lines'] ?? [])) {
            return 'tax_changed';
        }
        if (intval($quote['total_cents'] ?? 0) !== intval($current_quote['total_cents'] ?? 0)) {
            return 'total_changed';
        }
        return '';
    }

    private static function quote_item_totals_signature($items) {
        $signature = [];
        foreach ((array) $items as $item) {
            if (!is_array($item)) {
                continue;
            }
            $signature[] = implode(':', [
                self::source_product_id($item),
                intval($item['quantity'] ?? 0),
                intval($item['unit_price_cents'] ?? 0),
                intval($item['line_total_cents'] ?? 0),
            ]);
        }
        sort($signature, SORT_STRING);
        return $signature;
    }

    private static function quote_shipping_signature($shipping) {
        $shipping = is_array($shipping) ? $shipping : [];
        return [
            'amount_cents' => intval($shipping['amount_cents'] ?? 0),
            'currency' => (string) ($shipping['currency'] ?? ''),
            'method' => (string) ($shipping['method'] ?? ''),
        ];
    }

    private static function quote_vat_signature($vat_lines) {
        $signature = [];
        foreach ((array) $vat_lines as $line) {
            if (!is_array($line)) {
                continue;
            }
            $signature[] = implode(':', [
                intval($line['rate_bps'] ?? 0),
                intval($line['taxable_gross_cents'] ?? 0),
                intval($line['vat_cents'] ?? 0),
                !empty($line['included_in_price']) ? '1' : '0',
            ]);
        }
        sort($signature, SORT_STRING);
        return $signature;
    }

    private static function quote_money_snapshot($quote) {
        $shipping = is_array($quote['shipping'] ?? null) ? $quote['shipping'] : [];
        return [
            'currency' => (string) ($quote['currency'] ?? ''),
            'subtotal_cents' => intval($quote['subtotal_cents'] ?? 0),
            'shipping' => self::quote_shipping_signature($shipping),
            'vat_lines' => self::quote_vat_signature($quote['vat_lines'] ?? []),
            'total_cents' => intval($quote['total_cents'] ?? 0),
            'items' => self::quote_item_totals_signature($quote['items'] ?? []),
        ];
    }

    private static function stock_hold_mode() {
        if (defined('AGENTCART_STOCK_HOLD_MODE')) {
            return self::sanitize_stock_hold_mode_setting((string) AGENTCART_STOCK_HOLD_MODE);
        }
        return self::sanitize_stock_hold_mode_setting((string) get_option(self::STOCK_HOLD_MODE_OPTION, 'soft'));
    }

    private static function stock_hold_enabled() {
        return in_array(self::stock_hold_mode(), ['soft', 'hard'], true);
    }

    private static function soft_stock_hold_enabled() {
        return self::stock_hold_mode() === 'soft';
    }

    private static function hard_stock_reservation_enabled() {
        return self::stock_hold_mode() === 'hard';
    }

    private static function hard_stock_reservation_adapter_available() {
        return has_filter('agentcart_shopbridge_reserve_stock')
            && has_filter('agentcart_shopbridge_confirm_stock_reservation')
            && has_filter('agentcart_shopbridge_release_stock_reservation');
    }

    private static function stock_hold_minutes() {
        if (defined('AGENTCART_STOCK_HOLD_MINUTES')) {
            return self::sanitize_stock_hold_minutes_setting(AGENTCART_STOCK_HOLD_MINUTES);
        }
        return self::sanitize_stock_hold_minutes_setting(get_option(self::STOCK_HOLD_MINUTES_OPTION, 15));
    }

    private static function stock_hold_ttl_seconds() {
        return self::stock_hold_minutes() * MINUTE_IN_SECONDS;
    }

    private static function stock_holds() {
        $raw = get_option(self::STOCK_HOLDS_OPTION, []);
        $holds = is_array($raw) ? $raw : [];
        $now = time();
        $changed = false;
        foreach ($holds as $quote_id => $hold) {
            $expires_at = strtotime((string) ($hold['expires_at'] ?? ''));
            if (!$expires_at || $expires_at <= $now) {
                if (is_array($hold) && ($hold['mode'] ?? '') === 'hard') {
                    self::release_hard_stock_reservation((string) $quote_id, $hold, 'expired');
                }
                unset($holds[$quote_id]);
                $changed = true;
            }
        }
        if ($changed) {
            update_option(self::STOCK_HOLDS_OPTION, $holds, false);
        }
        return $holds;
    }

    private static function held_stock_quantity($product_id, $exclude_quote_id = '') {
        $quantity = 0;
        foreach (self::stock_holds() as $quote_id => $hold) {
            if ($exclude_quote_id !== '' && (string) $quote_id === (string) $exclude_quote_id) {
                continue;
            }
            $items = isset($hold['items']) && is_array($hold['items']) ? $hold['items'] : [];
            foreach ($items as $item) {
                if (intval($item['product_id'] ?? 0) === intval($product_id)) {
                    $quantity += intval($item['quantity'] ?? 0);
                }
            }
        }
        return max(0, $quantity);
    }

    private static function validate_product_stock_for_agentcart(WC_Product $product, $quantity, $exclude_quote_id = '') {
        if (!$product->is_in_stock()) {
            return new WP_Error('agentcart_stock_conflict', 'Insufficient stock for product: ' . $product->get_id(), ['status' => 409]);
        }
        if (!$product->managing_stock() || $product->get_stock_quantity() === null) {
            return true;
        }
        $stock_quantity = intval($product->get_stock_quantity());
        $held_quantity = self::stock_hold_enabled() ? self::held_stock_quantity($product->get_id(), $exclude_quote_id) : 0;
        $available_quantity = max(0, $stock_quantity - $held_quantity);
        if ($available_quantity < intval($quantity)) {
            return new WP_Error(
                'agentcart_stock_conflict',
                'Insufficient stock for product: ' . $product->get_id(),
                [
                    'status' => 409,
                    'product_id' => 'woo_' . $product->get_id(),
                    'stock_quantity' => $stock_quantity,
                    'held_quantity' => $held_quantity,
                    'available_quantity' => $available_quantity,
                    'recovery' => self::quote_recovery('stock_changed', null, $exclude_quote_id),
                ]
            );
        }
        return true;
    }

    private static function reserve_stock_for_quote($quote_id, $quote_items, $expires_at) {
        $checked_at = gmdate('c');
        if (self::hard_stock_reservation_enabled()) {
            return self::reserve_hard_stock_for_quote($quote_id, $quote_items, $expires_at, $checked_at);
        }
        if (!self::stock_hold_enabled()) {
            return [
                'state' => 'not_reserved',
                'mode' => 'none',
                'checked_at' => $checked_at,
                'rechecked_before_order_creation' => true,
                'reason' => 'stock_holds_disabled',
            ];
        }
        $items = [];
        foreach ($quote_items as $item) {
            $product = wc_get_product(intval($item['product_id'] ?? 0));
            if (!$product instanceof WC_Product || !$product->managing_stock() || $product->get_stock_quantity() === null) {
                continue;
            }
            $quantity = max(1, intval($item['quantity'] ?? 1));
            $stock_check = self::validate_product_stock_for_agentcart($product, $quantity);
            if (is_wp_error($stock_check)) {
                return $stock_check;
            }
            $items[] = [
                'product_id' => intval($item['product_id']),
                'quantity' => $quantity,
            ];
        }
        if (!$items) {
            return [
                'state' => 'not_applicable',
                'mode' => 'soft',
                'checked_at' => $checked_at,
                'rechecked_before_order_creation' => true,
                'reason' => 'no_managed_stock_items',
            ];
        }
        $holds = self::stock_holds();
        $holds[$quote_id] = [
            'quote_id' => $quote_id,
            'mode' => 'soft',
            'created_at' => $checked_at,
            'expires_at' => $expires_at,
            'items' => $items,
        ];
        update_option(self::STOCK_HOLDS_OPTION, $holds, false);
        return [
            'state' => 'soft_reserved',
            'mode' => 'soft',
            'hold_id' => $quote_id,
            'expires_at' => $expires_at,
            'checked_at' => $checked_at,
            'rechecked_before_order_creation' => true,
            'items' => $items,
            'note' => 'Soft AgentCart hold only; WooCommerce stock is rechecked before paid order creation.',
        ];
    }

    private static function reserve_hard_stock_for_quote($quote_id, $quote_items, $expires_at, $checked_at) {
        if (!self::hard_stock_reservation_adapter_available()) {
            return new WP_Error(
                'agentcart_stock_reservation_adapter_missing',
                'Hard stock reservation mode requires a merchant inventory adapter.',
                [
                    'status' => 503,
                    'stock_hold_mode' => 'hard',
                    'required_hooks' => [
                        'agentcart_shopbridge_reserve_stock',
                        'agentcart_shopbridge_confirm_stock_reservation',
                        'agentcart_shopbridge_release_stock_reservation',
                    ],
                ]
            );
        }
        $items = [];
        foreach ($quote_items as $item) {
            $product = wc_get_product(intval($item['product_id'] ?? 0));
            if (!$product instanceof WC_Product) {
                continue;
            }
            $quantity = max(1, intval($item['quantity'] ?? 1));
            $stock_check = self::validate_product_stock_for_agentcart($product, $quantity);
            if (is_wp_error($stock_check)) {
                return $stock_check;
            }
            $items[] = [
                'product_id' => intval($item['product_id']),
                'sku' => $product->get_sku() ?: 'WOO-' . $product->get_id(),
                'quantity' => $quantity,
                'managing_stock' => $product->managing_stock(),
                'stock_quantity' => $product->managing_stock() && $product->get_stock_quantity() !== null
                    ? intval($product->get_stock_quantity())
                    : null,
            ];
        }
        if (!$items) {
            return [
                'state' => 'not_applicable',
                'mode' => 'hard',
                'checked_at' => $checked_at,
                'rechecked_before_order_creation' => true,
                'reason' => 'no_reservable_items',
            ];
        }

        $reservation = apply_filters(
            'agentcart_shopbridge_reserve_stock',
            null,
            [
                'quote_id' => $quote_id,
                'merchant_id' => self::merchant_id(),
                'expires_at' => $expires_at,
                'items' => $items,
                'currency' => get_woocommerce_currency(),
            ]
        );
        if (is_wp_error($reservation)) {
            return $reservation;
        }
        if (!is_array($reservation) || empty($reservation['hold_id'])) {
            return new WP_Error(
                'agentcart_stock_reservation_rejected',
                'Hard stock reservation adapter did not return a hold_id.',
                ['status' => 409]
            );
        }

        $hold = [
            'quote_id' => $quote_id,
            'mode' => 'hard',
            'hold_id' => sanitize_text_field((string) $reservation['hold_id']),
            'provider' => sanitize_text_field((string) ($reservation['provider'] ?? 'external')),
            'adapter_reference' => sanitize_text_field((string) ($reservation['reference'] ?? '')),
            'created_at' => $checked_at,
            'expires_at' => sanitize_text_field((string) ($reservation['expires_at'] ?? $expires_at)),
            'items' => $items,
        ];
        $holds = self::stock_holds();
        $holds[$quote_id] = $hold;
        update_option(self::STOCK_HOLDS_OPTION, $holds, false);

        return [
            'state' => 'hard_reserved',
            'mode' => 'hard',
            'hold_id' => $hold['hold_id'],
            'provider' => $hold['provider'],
            'adapter_reference' => $hold['adapter_reference'],
            'expires_at' => $hold['expires_at'],
            'checked_at' => $checked_at,
            'rechecked_before_order_creation' => true,
            'requires_confirmation_before_order' => true,
            'items' => $items,
            'note' => 'Hard reservation supplied by merchant inventory adapter.',
        ];
    }

    private static function confirm_stock_reservation_for_order($quote_id, $quote, $receipt, $body) {
        $reservation = isset($quote['stock_reservation']) && is_array($quote['stock_reservation'])
            ? $quote['stock_reservation']
            : [];
        if (($reservation['mode'] ?? '') !== 'hard' || ($reservation['state'] ?? '') !== 'hard_reserved') {
            return [
                'state' => 'not_required',
                'mode' => (string) ($reservation['mode'] ?? self::stock_hold_mode()),
                'checked_at' => gmdate('c'),
            ];
        }
        if (!has_filter('agentcart_shopbridge_confirm_stock_reservation')) {
            return new WP_Error(
                'agentcart_stock_reservation_confirm_adapter_missing',
                'Hard stock reservation confirmation adapter is not available.',
                ['status' => 503]
            );
        }
        $confirmation = apply_filters(
            'agentcart_shopbridge_confirm_stock_reservation',
            null,
            [
                'quote_id' => $quote_id,
                'hold_id' => sanitize_text_field((string) ($reservation['hold_id'] ?? '')),
                'reservation' => $reservation,
                'quote_hash' => sanitize_text_field((string) ($quote['quote_hash'] ?? '')),
                'payment_receipt_id' => sanitize_text_field((string) ($receipt['id'] ?? '')),
                'agentcart_order_id' => sanitize_text_field((string) ($body['agentcart_order_id'] ?? '')),
            ]
        );
        if (is_wp_error($confirmation)) {
            return $confirmation;
        }
        if (!is_array($confirmation)) {
            return new WP_Error(
                'agentcart_stock_reservation_confirm_failed',
                'Hard stock reservation confirmation adapter did not return a confirmation packet.',
                ['status' => 409]
            );
        }
        $state = sanitize_key((string) ($confirmation['state'] ?? 'confirmed'));
        if (!in_array($state, ['confirmed', 'already_confirmed'], true)) {
            return new WP_Error(
                'agentcart_stock_reservation_confirm_failed',
                'Hard stock reservation could not be confirmed.',
                [
                    'status' => 409,
                    'adapter_state' => $state,
                ]
            );
        }
        return [
            'state' => $state,
            'mode' => 'hard',
            'hold_id' => sanitize_text_field((string) ($confirmation['hold_id'] ?? ($reservation['hold_id'] ?? ''))),
            'provider' => sanitize_text_field((string) ($confirmation['provider'] ?? ($reservation['provider'] ?? 'external'))),
            'adapter_reference' => sanitize_text_field((string) ($confirmation['reference'] ?? ($reservation['adapter_reference'] ?? ''))),
            'checked_at' => gmdate('c'),
        ];
    }

    private static function release_stock_hold($quote_id, $reason = 'released') {
        if ($quote_id === '') {
            return;
        }
        $holds = self::stock_holds();
        if (isset($holds[$quote_id])) {
            $hold = is_array($holds[$quote_id]) ? $holds[$quote_id] : [];
            unset($holds[$quote_id]);
            update_option(self::STOCK_HOLDS_OPTION, $holds, false);
            if (($hold['mode'] ?? '') === 'hard' && $reason !== 'confirmed') {
                self::release_hard_stock_reservation((string) $quote_id, $hold, $reason);
            }
        }
    }

    private static function release_hard_stock_reservation($quote_id, $hold, $reason) {
        if (!has_filter('agentcart_shopbridge_release_stock_reservation')) {
            return;
        }
        apply_filters(
            'agentcart_shopbridge_release_stock_reservation',
            null,
            [
                'quote_id' => $quote_id,
                'hold_id' => sanitize_text_field((string) ($hold['hold_id'] ?? '')),
                'hold' => $hold,
                'reason' => sanitize_key((string) $reason),
            ]
        );
    }

    private static function agentcart_enabled_product_count() {
        if (!function_exists('wc_get_products')) {
            return 0;
        }
        $products = wc_get_products(array_merge(self::agentcart_product_query_args(), [
            'limit' => -1,
            'return' => 'objects',
        ]));
        $enabled = array_filter($products, function ($product) {
            return $product instanceof WC_Product && self::is_product_agentcart_enabled($product);
        });
        return count($enabled);
    }

    private static function set_agentcart_exposure_for_published_simple_products($enabled) {
        if (!function_exists('wc_get_products')) {
            return 0;
        }
        $products = wc_get_products([
            'status' => 'publish',
            'type' => ['simple'],
            'limit' => -1,
            'return' => 'objects',
        ]);
        foreach ($products as $product) {
            if ($product instanceof WC_Product) {
                $product->update_meta_data(self::PRODUCT_ENABLED_META, $enabled === 'yes' ? 'yes' : 'no');
                $product->save();
            }
        }
        return count($products);
    }

    private static function prepare_quote_cart($ship_to) {
        if (function_exists('wc_load_cart')) {
            wc_load_cart();
        }
        if (!WC() || !WC()->cart) {
            return new WP_Error('agentcart_cart_unavailable', 'WooCommerce cart is not available for quote calculation.', ['status' => 503]);
        }
        $cart = WC()->cart;
        $cart->empty_cart();
        if (WC()->customer) {
            WC()->customer->set_shipping_country((string) ($ship_to['country'] ?? ''));
            WC()->customer->set_shipping_state((string) ($ship_to['state'] ?? ''));
            WC()->customer->set_shipping_postcode((string) ($ship_to['postcode'] ?? ''));
            WC()->customer->set_shipping_city((string) ($ship_to['city'] ?? ''));
            WC()->customer->set_shipping_address((string) ($ship_to['address_1'] ?? ''));
            WC()->customer->set_shipping_address_2((string) ($ship_to['address_2'] ?? ''));
            WC()->customer->set_billing_country((string) ($ship_to['country'] ?? ''));
            WC()->customer->set_billing_state((string) ($ship_to['state'] ?? ''));
            WC()->customer->set_billing_postcode((string) ($ship_to['postcode'] ?? ''));
            WC()->customer->set_billing_city((string) ($ship_to['city'] ?? ''));
            WC()->customer->set_calculated_shipping(true);
        }
        if (WC()->session) {
            WC()->session->set('chosen_shipping_methods', []);
        }
        return $cart;
    }

    private static function select_shipping_rates_for_cart($cart) {
        if (!$cart || !$cart->needs_shipping()) {
            return true;
        }
        if (!WC()->shipping()) {
            return new WP_Error('agentcart_shipping_unavailable', 'WooCommerce shipping is not available.', ['status' => 503]);
        }
        $packages = WC()->shipping()->get_packages();
        if (!$packages) {
            return new WP_Error('agentcart_no_shipping_package', 'WooCommerce did not create a shipping package for this quote.', ['status' => 409]);
        }
        $chosen = [];
        foreach ($packages as $index => $package) {
            $rates = isset($package['rates']) && is_array($package['rates']) ? $package['rates'] : [];
            if (!$rates) {
                return new WP_Error('agentcart_no_shipping_rate', 'No WooCommerce shipping rate is available for this basket and address.', ['status' => 409]);
            }
            $rate_ids = array_keys($rates);
            $chosen[$index] = (string) reset($rate_ids);
        }
        if (WC()->session) {
            WC()->session->set('chosen_shipping_methods', $chosen);
        }
        return true;
    }

    private static function quote_from_cart($cart) {
        $selected_shipping = self::selected_shipping_summary();
        $items = [];
        $subtotal_cents = 0;
        foreach ($cart->get_cart() as $cart_item) {
            $product = isset($cart_item['data']) && $cart_item['data'] instanceof WC_Product ? $cart_item['data'] : null;
            if (!$product) {
                continue;
            }
            $quantity = max(1, intval($cart_item['quantity'] ?? 1));
            $line_gross_cents = self::cents(floatval($cart_item['line_total'] ?? 0) + floatval($cart_item['line_tax'] ?? 0));
            $unit_gross_cents = intval(round($line_gross_cents / $quantity));
            $subtotal_cents += $line_gross_cents;
            $serialized = self::serialize_product($product);
            $items[] = [
                'product_id' => $serialized['product_id'],
                'source_product_id' => $product->get_id(),
                'sku' => $serialized['sku'],
                'title' => $serialized['title'],
                'quantity' => $quantity,
                'unit_price_cents' => $unit_gross_cents,
                'line_total_cents' => $line_gross_cents,
                'currency' => get_woocommerce_currency(),
                'category' => $serialized['category'],
                'category_slugs' => $serialized['category_slugs'],
                'vat_rate_bps' => self::vat_rate_bps($product),
                'restricted_goods' => $serialized['restricted_goods'],
                'commerce_policy' => $serialized['commerce_policy'],
                'agentcart_policy' => $serialized['agentcart_policy'],
            ];
        }
        if (!$items) {
            return new WP_Error('agentcart_empty_cart_quote', 'WooCommerce cart did not contain quoteable items.', ['status' => 409]);
        }
        $shipping_cents = self::cents(floatval($cart->get_shipping_total()) + floatval($cart->get_shipping_tax()));
        $total_cents = self::cents(floatval($cart->get_total('edit')));
        if ($total_cents <= 0) {
            $totals = $cart->get_totals();
            $total_cents = self::cents(floatval($totals['total'] ?? 0));
        }
        return [
            'items' => $items,
            'subtotal_cents' => $subtotal_cents,
            'shipping' => [
                'amount_cents' => $shipping_cents,
                'currency' => get_woocommerce_currency(),
                'method' => $selected_shipping['method_id'],
                'label' => $selected_shipping['label'],
                'source' => 'woocommerce_cart',
            ],
            'vat_lines' => self::vat_lines_from_cart($cart),
            'total_cents' => $total_cents,
        ];
    }

    private static function selected_shipping_summary() {
        $labels = [];
        $method_ids = [];
        $chosen = WC()->session ? WC()->session->get('chosen_shipping_methods', []) : [];
        $packages = WC()->shipping() ? WC()->shipping()->get_packages() : [];
        foreach ($packages as $index => $package) {
            $rates = isset($package['rates']) && is_array($package['rates']) ? $package['rates'] : [];
            if (!$rates) {
                continue;
            }
            $rate_id = isset($chosen[$index]) && isset($rates[$chosen[$index]]) ? $chosen[$index] : array_key_first($rates);
            $rate = $rates[$rate_id] ?? null;
            if ($rate && method_exists($rate, 'get_label')) {
                $labels[] = $rate->get_label();
            }
            $method_ids[] = (string) $rate_id;
        }
        return [
            'method_id' => $method_ids ? implode('+', $method_ids) : 'woocommerce',
            'label' => $labels ? implode(' + ', $labels) : 'WooCommerce shipping',
        ];
    }

    private static function vat_lines_from_cart($cart) {
        $buckets = [];
        foreach ($cart->get_cart() as $cart_item) {
            $line_taxes = $cart_item['line_tax_data']['total'] ?? [];
            $line_net = floatval($cart_item['line_total'] ?? 0);
            foreach ((array) $line_taxes as $rate_id => $amount) {
                $tax_amount = floatval($amount);
                if ($tax_amount <= 0) {
                    continue;
                }
                if (!isset($buckets[$rate_id])) {
                    $buckets[$rate_id] = ['tax' => 0.0, 'gross' => 0.0];
                }
                $buckets[$rate_id]['tax'] += $tax_amount;
                $buckets[$rate_id]['gross'] += $line_net + $tax_amount;
            }
        }
        $shipping_net = floatval($cart->get_shipping_total());
        foreach ((array) $cart->get_shipping_taxes() as $rate_id => $amount) {
            $tax_amount = floatval($amount);
            if ($tax_amount <= 0) {
                continue;
            }
            if (!isset($buckets[$rate_id])) {
                $buckets[$rate_id] = ['tax' => 0.0, 'gross' => 0.0];
            }
            $buckets[$rate_id]['tax'] += $tax_amount;
            $buckets[$rate_id]['gross'] += $shipping_net + $tax_amount;
        }
        if (!$buckets) {
            foreach ((array) $cart->get_taxes() as $rate_id => $amount) {
                $tax_amount = floatval($amount);
                if ($tax_amount <= 0) {
                    continue;
                }
                $rate_bps = self::tax_rate_bps_from_rate_id($rate_id);
                $buckets[$rate_id] = [
                    'tax' => $tax_amount,
                    'gross' => $rate_bps > 0 ? $tax_amount * (10000 + $rate_bps) / $rate_bps : $tax_amount,
                ];
            }
        }
        $lines = [];
        ksort($buckets);
        foreach ($buckets as $rate_id => $bucket) {
            $tax_cents = self::cents(floatval($bucket['tax'] ?? 0));
            if ($tax_cents <= 0) {
                continue;
            }
            $rate_bps = self::tax_rate_bps_from_rate_id($rate_id);
            $lines[] = [
                'rate_bps' => $rate_bps,
                'taxable_gross_cents' => self::cents(floatval($bucket['gross'] ?? 0)),
                'vat_cents' => $tax_cents,
                'currency' => get_woocommerce_currency(),
                'included_in_price' => wc_prices_include_tax(),
                'source' => 'woocommerce_cart',
            ];
        }
        return $lines;
    }

    private static function tax_rate_bps_from_rate_id($rate_id) {
        if (class_exists('WC_Tax') && method_exists('WC_Tax', 'get_rate_percent_value')) {
            return intval(round(floatval(WC_Tax::get_rate_percent_value($rate_id)) * 100));
        }
        if (class_exists('WC_Tax') && method_exists('WC_Tax', 'get_rate_percent')) {
            return intval(round(floatval(str_replace('%', '', WC_Tax::get_rate_percent($rate_id))) * 100));
        }
        return 0;
    }

    private static function package_size_for_product(WC_Product $product) {
        $weight = trim((string) $product->get_weight());
        $weight_unit = strtolower((string) get_option('woocommerce_weight_unit', 'kg'));
        if ($weight !== '' && floatval($weight) > 0) {
            $quantity = floatval($weight);
            $normalized = self::normalize_package_quantity($quantity, $weight_unit);
            $label = self::format_quantity($quantity) . ' ' . $weight_unit;
            return [
                'label' => $label,
                'quantity' => $quantity,
                'unit' => $weight_unit,
                'normalized_quantity' => $normalized['quantity'],
                'normalized_unit' => $normalized['unit'],
                'source' => 'woocommerce_weight',
            ];
        }
        return [
            'label' => '1 unit',
            'quantity' => 1,
            'unit' => 'unit',
            'normalized_quantity' => 1,
            'normalized_unit' => 'unit',
            'source' => 'woocommerce_default_unit',
        ];
    }

    private static function normalize_package_quantity($quantity, $unit) {
        $unit = strtolower((string) $unit);
        $quantity = floatval($quantity);
        if (in_array($unit, ['kg', 'kilogram', 'kilograms'], true)) {
            return ['quantity' => $quantity * 1000, 'unit' => 'g'];
        }
        if (in_array($unit, ['g', 'gram', 'grams'], true)) {
            return ['quantity' => $quantity, 'unit' => 'g'];
        }
        if (in_array($unit, ['lbs', 'lb', 'pound', 'pounds'], true)) {
            return ['quantity' => $quantity * 453.59237, 'unit' => 'g'];
        }
        if (in_array($unit, ['oz', 'ounce', 'ounces'], true)) {
            return ['quantity' => $quantity * 28.349523125, 'unit' => 'g'];
        }
        if (in_array($unit, ['l', 'liter', 'litre', 'liters', 'litres'], true)) {
            return ['quantity' => $quantity * 1000, 'unit' => 'ml'];
        }
        if (in_array($unit, ['cl', 'centiliter', 'centilitre', 'centiliters', 'centilitres'], true)) {
            return ['quantity' => $quantity * 10, 'unit' => 'ml'];
        }
        if (in_array($unit, ['ml', 'milliliter', 'millilitre', 'milliliters', 'millilitres'], true)) {
            return ['quantity' => $quantity, 'unit' => 'ml'];
        }
        return ['quantity' => max(1, $quantity), 'unit' => 'unit'];
    }

    private static function format_quantity($quantity) {
        $formatted = rtrim(rtrim(number_format((float) $quantity, 3, '.', ''), '0'), '.');
        return $formatted === '' ? '0' : $formatted;
    }

    private static function normalized_label_values($values) {
        $normalized = [];
        foreach ($values as $value) {
            $text = strtolower(trim(wp_strip_all_tags((string) $value)));
            if ($text === '') {
                continue;
            }
            $slug = sanitize_title($text);
            foreach (array_filter([$text, $slug]) as $candidate) {
                if (!in_array($candidate, $normalized, true)) {
                    $normalized[] = $candidate;
                }
            }
        }
        return $normalized;
    }

    private static function product_tag_values(WC_Product $product) {
        $terms = wp_get_post_terms($product->get_id(), 'product_tag', ['fields' => 'all']);
        if (is_wp_error($terms) || !is_array($terms)) {
            return [];
        }
        $values = [];
        foreach ($terms as $term) {
            $values[] = $term->name;
            $values[] = $term->slug;
        }
        return self::normalized_label_values($values);
    }

    private static function product_attribute_values(WC_Product $product) {
        $values = [];
        foreach ($product->get_attributes() as $attribute) {
            if (!is_object($attribute) || !method_exists($attribute, 'get_options')) {
                continue;
            }
            if (method_exists($attribute, 'is_taxonomy') && $attribute->is_taxonomy() && function_exists('wc_get_product_terms')) {
                $term_values = wc_get_product_terms($product->get_id(), $attribute->get_name(), ['fields' => 'names']);
                if (!is_wp_error($term_values) && is_array($term_values)) {
                    $values = array_merge($values, $term_values);
                }
                continue;
            }
            foreach ($attribute->get_options() as $option) {
                $values[] = $option;
            }
        }
        return self::normalized_label_values($values);
    }

    private static function known_dietary_labels() {
        return [
            'vegan', 'vegetarian', 'organic', 'bio', 'gluten-free', 'glutenfree',
            'dairy-free', 'dairyfree', 'lactose-free', 'lactosefree', 'nut-free',
            'nutfree', 'peanut-free', 'peanutfree', 'halal', 'kosher',
        ];
    }

    private static function known_allergen_labels() {
        return [
            'peanut', 'peanuts', 'tree-nut', 'tree-nuts', 'nuts', 'milk', 'dairy',
            'egg', 'eggs', 'soy', 'soya', 'wheat', 'gluten', 'sesame', 'fish',
            'shellfish', 'crustaceans', 'molluscs', 'mustard', 'celery', 'lupin',
            'sulphites', 'sulfites',
        ];
    }

    private static function product_agent_labels(WC_Product $product) {
        $tags = self::product_tag_values($product);
        $attributes = self::product_attribute_values($product);
        $labels = array_values(array_unique(array_merge($tags, $attributes)));
        $dietary_tags = array_values(array_intersect($labels, self::known_dietary_labels()));
        $allergens = array_values(array_intersect($labels, self::known_allergen_labels()));
        return [
            'tags' => $tags,
            'labels' => $labels,
            'dietary_tags' => $dietary_tags,
            'allergens' => $allergens,
        ];
    }

    private static function restricted_goods_rules() {
        return [
            'age_restricted' => [
                'labels' => ['alcohol', 'beer', 'wine', 'spirits', 'liquor', 'tobacco', 'vape', 'vaping', 'cannabis', 'cbd', 'adult', 'lottery'],
                'summary' => 'Age-restricted or adult-regulated goods.',
            ],
            'medical' => [
                'labels' => ['medicine', 'medication', 'pharmacy', 'prescription', 'otc', 'drug', 'drugs'],
                'summary' => 'Medical or pharmacy goods that may need legal and health review.',
            ],
            'weapons' => [
                'labels' => ['weapon', 'weapons', 'knife', 'knives', 'blade', 'ammunition', 'fireworks'],
                'summary' => 'Weapons, blades, ammunition, or fireworks.',
            ],
            'stored_value' => [
                'labels' => ['gift-card', 'gift-cards', 'voucher', 'vouchers', 'prepaid-card', 'prepaid-cards'],
                'summary' => 'Stored-value goods with fraud or resale risk.',
            ],
        ];
    }

    private static function product_restricted_goods(WC_Product $product, $agent_labels = null) {
        $agent_labels = is_array($agent_labels) ? $agent_labels : self::product_agent_labels($product);
        $labels = array_values(array_unique(array_merge(
            $agent_labels['labels'] ?? [],
            self::product_category_slugs($product)
        )));
        $flags = [];
        foreach (self::restricted_goods_rules() as $code => $rule) {
            $matches = array_values(array_intersect($labels, $rule['labels']));
            if (!$matches) {
                continue;
            }
            $flags[] = [
                'code' => $code,
                'summary' => $rule['summary'],
                'matched_terms' => $matches,
                'requires_human_review' => true,
                'agent_should_not_autonomously_purchase' => true,
            ];
        }
        return $flags;
    }

    private static function commerce_policy_rules() {
        return [
            'perishable' => [
                'labels' => ['perishable', 'fresh', 'chilled', 'refrigerated', 'frozen', 'dairy', 'meat', 'seafood', 'fish', 'produce', 'fruit', 'vegetable', 'bakery'],
                'summary' => 'Perishable or temperature-sensitive goods may have shorter cancellation, return, or refund windows.',
                'returnable' => false,
            ],
            'deposit' => [
                'labels' => ['deposit', 'pfand', 'bottle-deposit', 'bottle-deposits', 'crate', 'returnable-bottle', 'returnable-bottles'],
                'summary' => 'Deposit-bearing goods may include a refundable container or packaging deposit.',
                'returnable' => true,
            ],
            'final_sale' => [
                'labels' => ['final-sale', 'non-returnable', 'nonreturnable', 'no-returns', 'custom', 'personalized', 'made-to-order'],
                'summary' => 'Merchant labels indicate final-sale or non-returnable handling.',
                'returnable' => false,
            ],
            'substitution_sensitive' => [
                'labels' => ['no-substitution', 'no-substitutions', 'substitution-sensitive', 'brand-specific'],
                'summary' => 'Substitutions should not be made without explicit buyer approval.',
                'returnable' => true,
            ],
        ];
    }

    private static function product_commerce_policy(WC_Product $product, $agent_labels = null) {
        $agent_labels = is_array($agent_labels) ? $agent_labels : self::product_agent_labels($product);
        $labels = array_values(array_unique(array_merge(
            $agent_labels['labels'] ?? [],
            self::product_category_slugs($product)
        )));
        $flags = [];
        $returnable = true;
        foreach (self::commerce_policy_rules() as $code => $rule) {
            $matches = array_values(array_intersect($labels, $rule['labels']));
            if (!$matches) {
                continue;
            }
            if (empty($rule['returnable'])) {
                $returnable = false;
            }
            $flags[] = self::commerce_policy_flag($code, $rule, $matches, 'woocommerce_terms');
        }
        foreach (self::product_aftercare_override_flags($product) as $flag) {
            if (empty($flag['returnable'])) {
                $returnable = false;
            }
            $flags = self::upsert_commerce_policy_flag($flags, $flag);
        }
        $refund_conditions = [
            'merchant_review_required' => !empty($flags),
            'rail_refund_requires_verifier' => true,
        ];
        if (!$returnable) {
            $refund_conditions['return_handling'] = 'merchant_review_or_exception_only';
        } elseif ($flags) {
            $refund_conditions['return_handling'] = 'review_policy_before_return';
        } else {
            $refund_conditions['return_handling'] = 'standard_merchant_policy';
        }
        return [
            'flags' => $flags,
            'returnable_by_default' => $returnable,
            'refund_conditions' => $refund_conditions,
            'substitution_requires_approval' => self::commerce_policy_has_flag($flags, 'substitution_sensitive'),
            'deposit_possible' => self::commerce_policy_has_flag($flags, 'deposit'),
            'perishable' => self::commerce_policy_has_flag($flags, 'perishable'),
            'buyer_agent_aftercare_note' => $flags
                ? 'Review item-level merchant policy before refund, return, cancellation, or substitution.'
                : 'Use standard merchant return and refund policy.',
        ];
    }

    private static function product_aftercare_override_flags(WC_Product $product) {
        $overrides = [
            'perishable' => self::PRODUCT_PERISHABLE_META,
            'deposit' => self::PRODUCT_DEPOSIT_META,
            'final_sale' => self::PRODUCT_FINAL_SALE_META,
            'substitution_sensitive' => self::PRODUCT_SUBSTITUTION_SENSITIVE_META,
        ];
        $rules = self::commerce_policy_rules();
        $flags = [];
        foreach ($overrides as $code => $meta_key) {
            if ($product->get_meta($meta_key, true) !== 'yes' || empty($rules[$code])) {
                continue;
            }
            $flags[] = self::commerce_policy_flag($code, $rules[$code], [$meta_key], 'woocommerce_product_meta');
        }
        return $flags;
    }

    private static function commerce_policy_flag($code, $rule, $matched_terms, $source) {
        return [
            'code' => $code,
            'summary' => (string) ($rule['summary'] ?? ''),
            'matched_terms' => array_values(array_unique(array_map('strval', $matched_terms))),
            'source' => $source,
            'requires_human_review' => true,
            'returnable' => !empty($rule['returnable']),
        ];
    }

    private static function upsert_commerce_policy_flag($flags, $new_flag) {
        $code = (string) ($new_flag['code'] ?? '');
        if ($code === '') {
            return $flags;
        }
        foreach ($flags as $index => $flag) {
            if (!is_array($flag) || (string) ($flag['code'] ?? '') !== $code) {
                continue;
            }
            $existing_terms = isset($flag['matched_terms']) && is_array($flag['matched_terms']) ? $flag['matched_terms'] : [];
            $new_terms = isset($new_flag['matched_terms']) && is_array($new_flag['matched_terms']) ? $new_flag['matched_terms'] : [];
            $sources = [];
            foreach ([$flag['source'] ?? '', $new_flag['source'] ?? ''] as $source) {
                if ($source !== '' && !in_array($source, $sources, true)) {
                    $sources[] = $source;
                }
            }
            $flag['matched_terms'] = array_values(array_unique(array_merge($existing_terms, $new_terms)));
            $flag['source'] = implode('+', $sources);
            $flag['returnable'] = !empty($flag['returnable']) && !empty($new_flag['returnable']);
            $flags[$index] = $flag;
            return $flags;
        }
        $flags[] = $new_flag;
        return $flags;
    }

    private static function commerce_policy_has_flag($flags, $code) {
        foreach ($flags as $flag) {
            if (is_array($flag) && ($flag['code'] ?? '') === $code) {
                return true;
            }
        }
        return false;
    }

    private static function serialize_product(WC_Product $product) {
        $category = 'household.supplies';
        $category_ids = $product->get_category_ids();
        if ($category_ids) {
            $term = get_term($category_ids[0], 'product_cat');
            if ($term && !is_wp_error($term)) {
                $category = 'woocommerce.' . $term->slug;
            }
        }
        $image_urls = [];
        $image_id = $product->get_image_id();
        if ($image_id) {
            $url = wp_get_attachment_image_url($image_id, 'full');
            if ($url) {
                $image_urls[] = $url;
            }
        }
        $package_size = self::package_size_for_product($product);
        $agent_labels = self::product_agent_labels($product);
        $category_slugs = self::product_category_slugs($product);
        $blocked_category_matches = self::product_blocked_category_matches($product);
        $restricted_goods = self::product_restricted_goods($product, $agent_labels);
        $blocked_reasons = self::product_agentcart_block_reasons($product);
        $restricted_goods_allowed = $product->get_meta(self::PRODUCT_RESTRICTED_GOODS_ALLOWED_META, true) === 'yes';
        $commerce_policy = self::product_commerce_policy($product, $agent_labels);
        return [
            'id' => 'woo_' . $product->get_id(),
            'product_id' => 'woo_' . $product->get_id(),
            'source_product_id' => $product->get_id(),
            'merchant_id' => self::merchant()['id'],
            'sku' => $product->get_sku() ?: 'WOO-' . $product->get_id(),
            'title' => wp_strip_all_tags($product->get_name()),
            'description' => wp_strip_all_tags($product->get_short_description() ?: $product->get_description()),
            'category' => $category,
            'category_slugs' => $category_slugs,
            'brand' => get_bloginfo('name') ?: 'WooCommerce',
            'unit_size' => $package_size['label'],
            'package_size' => $package_size,
            'tags' => $agent_labels['tags'],
            'labels' => $agent_labels['labels'],
            'dietary_tags' => $agent_labels['dietary_tags'],
            'allergens' => $agent_labels['allergens'],
            'restricted_goods' => $restricted_goods,
            'commerce_policy' => $commerce_policy,
            'image_urls' => $image_urls,
            'price_cents' => self::cents((float) wc_get_price_including_tax($product, ['qty' => 1])),
            'currency' => get_woocommerce_currency(),
            'vat_rate_bps' => self::vat_rate_bps($product),
            'stock' => $product->managing_stock() && $product->get_stock_quantity() !== null ? intval($product->get_stock_quantity()) : 999,
            'availability' => $product->is_in_stock() ? 'in_stock' : 'out_of_stock',
            'shipping_regions' => self::product_shipping_countries($product),
            'eligible_for_agent_checkout' => self::is_product_agentcart_enabled($product),
            'max_quantity' => self::product_max_quantity($product),
            'agentcart_policy' => [
                'max_quantity' => self::product_max_quantity($product),
                'blocked' => self::is_product_agentcart_blocked($product),
                'blocked_reasons' => $blocked_reasons,
                'blocked_category_slugs' => $blocked_category_matches,
                'exposure_mode' => self::product_exposure_mode(),
                'exposure_categories' => self::product_exposure_mode() === 'category' ? self::product_exposure_categories() : [],
                'restricted_goods' => $restricted_goods,
                'restricted_goods_blocked_by_default' => true,
                'restricted_goods_allowed_by_merchant' => $restricted_goods_allowed,
                'commerce_policy' => $commerce_policy,
                'requires_human_review' => !empty($restricted_goods) || !empty($commerce_policy['flags']),
            ],
        ];
    }

    private static function source_product_id($item) {
        if (isset($item['source_product_id'])) {
            return intval($item['source_product_id']);
        }
        $raw = (string) ($item['product_id'] ?? $item['id'] ?? '');
        return intval(str_replace('woo_', '', $raw));
    }

    private static function normalize_address($raw) {
        $raw = is_array($raw) ? $raw : [];
        $country = strtoupper(sanitize_text_field((string) ($raw['country'] ?? (WC()->countries->get_base_country() ?: 'DE'))));
        return [
            'first_name' => sanitize_text_field((string) ($raw['first_name'] ?? '')),
            'last_name' => sanitize_text_field((string) ($raw['last_name'] ?? '')),
            'company' => sanitize_text_field((string) ($raw['company'] ?? '')),
            'address_1' => sanitize_text_field((string) ($raw['address_1'] ?? '')),
            'address_2' => sanitize_text_field((string) ($raw['address_2'] ?? '')),
            'city' => sanitize_text_field((string) ($raw['city'] ?? '')),
            'state' => sanitize_text_field((string) ($raw['state'] ?? '')),
            'postcode' => sanitize_text_field((string) ($raw['postcode'] ?? $raw['postal_code'] ?? '')),
            'country' => $country ?: 'DE',
            'email' => sanitize_email((string) ($raw['email'] ?? '')),
            'phone' => sanitize_text_field((string) ($raw['phone'] ?? '')),
        ];
    }

    private static function validate_quote_address($ship_to) {
        if (empty($ship_to['country'])) {
            return new WP_Error('agentcart_ship_to_country_required', 'ship_to.country is required for a final quote.', ['status' => 400]);
        }
        if (empty($ship_to['postcode'])) {
            return new WP_Error('agentcart_ship_to_postcode_required', 'ship_to.postcode or ship_to.postal_code is required for a final quote.', ['status' => 400]);
        }
        return true;
    }

    private static function cents($amount) {
        return intval(round($amount * 100));
    }

    private static function vat_rate_bps(WC_Product $product) {
        $rates = WC_Tax::get_rates($product->get_tax_class());
        if (!$rates) {
            return 1900;
        }
        $rate = reset($rates);
        return intval(round(floatval($rate['rate'] ?? 19) * 100));
    }

    private static function vat_lines($buckets) {
        $lines = [];
        ksort($buckets);
        foreach ($buckets as $rate_bps => $gross) {
            if ($gross <= 0) {
                continue;
            }
            $lines[] = [
                'rate_bps' => intval($rate_bps),
                'taxable_gross_cents' => intval($gross),
                'vat_cents' => intval(round($gross * $rate_bps / (10000 + $rate_bps))),
                'currency' => get_woocommerce_currency(),
                'included_in_price' => true,
            ];
        }
        return $lines;
    }
}

AgentCart_ShopBridge::init();
