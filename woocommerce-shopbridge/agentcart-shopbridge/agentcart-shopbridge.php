<?php
/**
 * Plugin Name: AgentCart ShopBridge for WooCommerce
 * Description: Exposes opt-in WooCommerce catalog, quote, and paid-order endpoints for AgentCart household agents.
 * Version: 0.1.0
 * Author: AgentCart
 * Requires Plugins: woocommerce
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
    const CHECKOUT_LOCK_PREFIX = 'agentcart_shopbridge_checkout_lock_';
    const CHECKOUT_LOCK_TTL_SECONDS = 120;
    const PAYMENT_VERIFIER_URL_OPTION = 'agentcart_shopbridge_payment_verifier_url';
    const PAYMENT_VERIFIER_TOKEN_OPTION = 'agentcart_shopbridge_payment_verifier_token';
    const TEMPO_RECIPIENT_OPTION = 'agentcart_shopbridge_tempo_recipient';
    const TEMPO_NETWORK_OPTION = 'agentcart_shopbridge_tempo_network';
    const STRIPE_PROFILE_ID_OPTION = 'agentcart_shopbridge_stripe_profile_id';
    const SUPPORT_EMAIL_OPTION = 'agentcart_shopbridge_support_email';
    const PRODUCT_ENABLED_META = '_agentcart_enabled';

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
    }

    public static function render_settings_page() {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('You do not have permission to manage AgentCart ShopBridge.', 'agentcart-shopbridge'));
        }
        self::ensure_token();
        $product_action_notice = self::maybe_handle_product_exposure_action();
        $manifest_url = home_url('/.well-known/agentcart.json');
        $catalog_url = rest_url(self::API_NAMESPACE . '/catalog');
        $quote_url = rest_url(self::API_NAMESPACE . '/quote');
        $orders_url = rest_url(self::API_NAMESPACE . '/orders');
        $payment_verifier_url = self::payment_verifier_url();
        $tempo_recipient = self::tempo_recipient();
        $stripe_profile_id = self::stripe_profile_id();
        $support_email = self::support_email();
        $readiness = self::readiness();
        ?>
        <div class="wrap">
            <h1>AgentCart ShopBridge</h1>
            <?php if ($product_action_notice !== null) : ?>
                <div class="notice notice-success is-dismissible"><p><?php echo esc_html($product_action_notice); ?></p></div>
            <?php endif; ?>
            <p>
                Expose this WooCommerce store to household agents through machine-readable discovery,
                catalog, quote, paid-order, and order-status endpoints. WooCommerce stays the source of
                truth for products, stock, tax, shipping, fulfillment, refunds, and support.
            </p>

            <h2>Readiness</h2>
            <table class="widefat striped" style="max-width: 980px;">
                <tbody>
                    <tr>
                        <th scope="row">Discovery manifest</th>
                        <td><code><?php echo esc_html($manifest_url); ?></code></td>
                        <td><?php echo self::admin_status_badge(true, 'Published'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Merchant token</th>
                        <td>Used by a trusted AgentCart gateway for demo or private integrations.</td>
                        <td><?php echo self::admin_status_badge((bool) self::merchant_token_value(), 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Tempo recipient</th>
                        <td><code><?php echo esc_html($tempo_recipient ?: 'not configured'); ?></code></td>
                        <td><?php echo self::admin_status_badge($tempo_recipient !== '', 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Payment verifier</th>
                        <td><code><?php echo esc_html($payment_verifier_url ?: 'trusted gateway token mode'); ?></code></td>
                        <td><?php echo self::admin_status_badge($payment_verifier_url !== '', 'Production shape', 'Demo mode'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Stripe/card MPP</th>
                        <td><code><?php echo esc_html($stripe_profile_id ?: 'not configured'); ?></code></td>
                        <td><?php echo self::admin_status_badge($stripe_profile_id !== '' && $payment_verifier_url !== '', 'Configured', 'Needs Stripe profile + verifier'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Support email</th>
                        <td><code><?php echo esc_html($support_email ?: 'not published'); ?></code></td>
                        <td><?php echo self::admin_status_badge($support_email !== '', 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Public origin</th>
                        <td><code><?php echo esc_html(home_url('/')); ?></code></td>
                        <td><?php echo self::admin_status_badge(self::public_origin_is_https(), 'HTTPS', 'Needs HTTPS'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Legal pages</th>
                        <td><?php echo esc_html(self::legal_pages_configured() ? 'Terms and returns pages are configured.' : 'Terms and returns pages need review.'); ?></td>
                        <td><?php echo self::admin_status_badge(self::legal_pages_configured(), 'Configured', 'Missing'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Tax and shipping</th>
                        <td><?php echo esc_html(self::tax_and_shipping_configured() ? 'WooCommerce tax and shipping countries are configured.' : 'Review WooCommerce tax and shipping setup before production.'); ?></td>
                        <td><?php echo self::admin_status_badge(self::tax_and_shipping_configured(), 'Configured', 'Needs setup'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">AgentCart-enabled products</th>
                        <td><?php echo esc_html((string) $readiness['agentcart_enabled_product_count']); ?> published simple products are explicitly opted in.</td>
                        <td><?php echo self::admin_status_badge($readiness['agentcart_enabled_product_count'] > 0, 'Configured', 'None enabled'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Demo readiness</th>
                        <td><?php echo esc_html(empty($readiness['missing_for_demo']) ? 'Ready for agent catalog, quote, order, and refund demo.' : implode(', ', $readiness['missing_for_demo'])); ?></td>
                        <td><?php echo self::admin_status_badge($readiness['demo_ready'], 'Demo ready', 'Needs setup'); ?></td>
                    </tr>
                    <tr>
                        <th scope="row">Production readiness</th>
                        <td><?php echo esc_html(empty($readiness['missing_for_production']) ? 'External payment verifier and merchant rail settings are configured.' : implode(', ', $readiness['missing_for_production'])); ?></td>
                        <td><?php echo self::admin_status_badge($readiness['production_ready'], 'Production-shaped', 'Roadmap'); ?></td>
                    </tr>
                </tbody>
            </table>

            <h2>Endpoints</h2>
            <table class="widefat striped" style="max-width: 980px;">
                <tbody>
                    <tr><th scope="row">Manifest</th><td><code><?php echo esc_html($manifest_url); ?></code></td></tr>
                    <tr><th scope="row">Catalog</th><td><code><?php echo esc_html($catalog_url); ?></code></td></tr>
                    <tr><th scope="row">Quote</th><td><code><?php echo esc_html($quote_url); ?></code></td></tr>
                    <tr><th scope="row">Paid order</th><td><code><?php echo esc_html($orders_url); ?></code></td></tr>
                </tbody>
            </table>

            <h2>Settings</h2>
            <form method="post" action="options.php">
                <?php settings_fields('agentcart_shopbridge'); ?>
                <table class="form-table" role="presentation">
                    <?php self::render_text_setting_row('Merchant token', self::TOKEN_OPTION, self::merchant_token_value(), 'AGENTCART_SHOPBRIDGE_TOKEN', 'Shared secret for a trusted AgentCart gateway. Production public checkout should use a payment verifier.'); ?>
                    <?php self::render_text_setting_row('Support email', self::SUPPORT_EMAIL_OPTION, $support_email, 'AGENTCART_SUPPORT_EMAIL', 'Published in the merchant-of-record block for customer support.'); ?>
                    <?php self::render_text_setting_row('Tempo network', self::TEMPO_NETWORK_OPTION, self::tempo_network(), 'AGENTCART_TEMPO_NETWORK', 'For the hackathon this is usually testnet.'); ?>
                    <?php self::render_text_setting_row('Tempo recipient address', self::TEMPO_RECIPIENT_OPTION, $tempo_recipient, 'AGENTCART_TEMPO_RECIPIENT_ADDRESS', 'Merchant or payment-provider recipient used by the payment verifier.'); ?>
                    <?php self::render_text_setting_row('Stripe profile / network id', self::STRIPE_PROFILE_ID_OPTION, $stripe_profile_id, 'AGENTCART_STRIPE_PROFILE_ID', 'Optional Stripe Business Network/profile id for card/SPT MPP. Requires a verifier that can validate Stripe credentials and refunds.'); ?>
                    <?php self::render_text_setting_row('Payment verifier URL', self::PAYMENT_VERIFIER_URL_OPTION, $payment_verifier_url, 'AGENTCART_PAYMENT_VERIFIER_URL', 'Endpoint that verifies quote-bound Tempo or Stripe MPP receipts before WooCommerce creates a paid order, and rail-bound refunds before recording a production refund.'); ?>
                    <?php self::render_password_setting_row('Payment verifier token', self::PAYMENT_VERIFIER_TOKEN_OPTION, self::payment_verifier_token(), 'AGENTCART_PAYMENT_VERIFIER_TOKEN', 'Optional bearer token sent from this plugin to the verifier.'); ?>
                </table>
                <?php submit_button('Save AgentCart settings'); ?>
            </form>

            <h2>Product Exposure</h2>
            <p style="max-width: 760px;">
                Products are private by default until the merchant explicitly enables AgentCart exposure.
                Use the checkbox on individual products for fine-grained control, or bulk-enable the
                current published simple-product catalog during onboarding.
            </p>
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
                <li>Enable <strong>Expose through AgentCart</strong> on selected products, or bulk-enable the current published simple-product catalog above.</li>
                <li>Configure this page with support, Tempo recipient, and payment verification settings.</li>
                <li>Share the manifest URL or register its hash in an AgentCart discovery registry.</li>
                <li>Run a sandbox quote and order test before allowing public agent checkout.</li>
            </ol>
        </div>
        <?php
    }

    private static function maybe_handle_product_exposure_action() {
        if (strtoupper((string) ($_SERVER['REQUEST_METHOD'] ?? '')) !== 'POST') {
            return null;
        }
        if (empty($_POST['agentcart_product_action'])) {
            return null;
        }
        check_admin_referer('agentcart_shopbridge_product_action');
        $action = sanitize_key((string) $_POST['agentcart_product_action']);
        if ($action === 'enable_all_published_simple') {
            $count = self::set_agentcart_exposure_for_published_simple_products('yes');
            return sprintf('%d published simple products are now AgentCart-enabled.', $count);
        }
        if ($action === 'disable_all') {
            $count = self::set_agentcart_exposure_for_published_simple_products('no');
            return sprintf('%d published simple products are no longer exposed through AgentCart.', $count);
        }
        return null;
    }

    public static function render_product_agentcart_options() {
        if (!function_exists('woocommerce_wp_checkbox')) {
            return;
        }
        woocommerce_wp_checkbox([
            'id' => self::PRODUCT_ENABLED_META,
            'label' => __('Expose through AgentCart', 'agentcart-shopbridge'),
            'description' => __('Allow this product to appear in AgentCart catalog and quote endpoints for agent checkout.', 'agentcart-shopbridge'),
            'desc_tip' => true,
        ]);
    }

    public static function save_product_agentcart_options($product) {
        if (!$product instanceof WC_Product) {
            return;
        }
        $product->update_meta_data(self::PRODUCT_ENABLED_META, isset($_POST[self::PRODUCT_ENABLED_META]) ? 'yes' : 'no');
    }

    public static function maybe_serve_well_known_manifest() {
        $path = parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH);
        if ($path !== '/.well-known/agentcart.json') {
            return;
        }
        if (!class_exists('WooCommerce')) {
            wp_send_json(['error' => 'WooCommerce is required.'], 503);
        }
        wp_send_json(self::capability());
    }

    public static function authorize_public_read(WP_REST_Request $request) {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('agentcart_woocommerce_missing', 'WooCommerce is required.', ['status' => 503]);
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
        if (self::has_valid_merchant_token($request)) {
            return true;
        }
        return new WP_Error(
            'agentcart_unauthorized',
            'Refund creation requires the merchant token. Buyer-facing refund requests should be approved by the merchant or trusted gateway before this endpoint is called.',
            ['status' => 401]
        );
    }

    private static function has_valid_merchant_token(WP_REST_Request $request) {
        $configured = self::merchant_token_value();
        $supplied = $request->get_header('x-agentcart-merchant-token');
        return $configured && $supplied && hash_equals((string) $configured, (string) $supplied);
    }

    private static function merchant_token_value() {
        return defined('AGENTCART_SHOPBRIDGE_TOKEN') ? (string) AGENTCART_SHOPBRIDGE_TOKEN : (string) get_option(self::TOKEN_OPTION, '');
    }

    private static function admin_status_badge($ok, $ok_label, $missing_label = 'Missing') {
        $color = $ok ? '#008a20' : '#996800';
        $background = $ok ? '#edfaef' : '#fff8e5';
        $label = $ok ? $ok_label : $missing_label;
        return '<span style="display:inline-block;padding:3px 8px;border-radius:999px;background:' . esc_attr($background) . ';color:' . esc_attr($color) . ';font-weight:600;">' . esc_html($label) . '</span>';
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
            'agentcart_enabled_product_count' => $enabled_product_count,
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
        if (!defined('AGENTCART_MERCHANT_ID')) {
            return false;
        }
        $merchant_id = sanitize_key((string) AGENTCART_MERCHANT_ID);
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

    private static function render_text_setting_row($label, $option, $value, $constant, $description) {
        self::render_setting_row('text', $label, $option, $value, $constant, $description);
    }

    private static function render_password_setting_row($label, $option, $value, $constant, $description) {
        self::render_setting_row('password', $label, $option, $value, $constant, $description);
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

    public static function capability() {
        return [
            'name' => 'AgentCart ShopBridge for WooCommerce',
            'version' => '0.1.0',
            'merchant' => self::merchant(),
            'manifest_url' => home_url('/.well-known/agentcart.json'),
            'readiness' => self::readiness(),
            'protocols' => [
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
                    'configured' => self::stripe_profile_id() !== '' && self::payment_verifier_url() !== '',
                ],
            ],
            'capabilities' => [
                'catalog' => true,
                'quote' => true,
                'server_side_quote_binding' => true,
                'paid_order_creation' => true,
                'idempotent_order_creation' => true,
                'checkout_replay_conflict_detection' => true,
                'merchant_of_record' => true,
                'guest_checkout' => true,
                'shipping_address_on_order' => true,
                'per_product_agentcart_opt_in' => true,
                'order_status_token' => true,
                'tracking_metadata_read' => true,
                'agentcart_order_ip_minimized' => true,
                'refund_endpoint' => true,
                'refunds_remain_in_woocommerce_with_external_rail_verification' => true,
            ],
            'delivery' => [
                'ship_to_countries' => self::shipping_countries(),
                'shipping_country_names' => self::shipping_country_names(),
                'quote_requires_supported_country' => true,
            ],
            'endpoints' => [
                'manifest' => home_url('/.well-known/agentcart.json'),
                'capability' => rest_url(self::API_NAMESPACE . '/capability'),
                'catalog' => rest_url(self::API_NAMESPACE . '/catalog'),
                'product' => rest_url(self::API_NAMESPACE . '/products/{id}'),
                'quote' => rest_url(self::API_NAMESPACE . '/quote'),
                'orders' => rest_url(self::API_NAMESPACE . '/orders'),
                'order_status' => rest_url(self::API_NAMESPACE . '/orders/{id}/status'),
                'refunds' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
            ],
            'discovery' => [
                'well_known' => '/.well-known/agentcart.json',
                'registry_ready' => true,
                'suggested_registry_record' => [
                    'merchant_id' => self::merchant()['id'],
                    'manifest_url' => home_url('/.well-known/agentcart.json'),
                    'manifest_hash_alg' => 'sha-256',
                ],
            ],
            'payment_verification' => [
                'mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'external_verifier_configured' => self::payment_verifier_url() !== '',
                'tempo_recipient_configured' => self::tempo_recipient() !== '',
                'tempo_network' => self::tempo_network(),
                'stripe_profile_configured' => self::stripe_profile_id() !== '',
                'refunds_use_same_verifier' => true,
            ],
            'refund_policy' => [
                'endpoint' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
                'requires_merchant_token' => true,
                'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
                'production_requires_rail_refund_verification' => true,
            ],
        ];
    }

    public static function catalog(WP_REST_Request $request) {
        $search = sanitize_text_field((string) $request->get_param('search'));
        $limit = min(24, max(1, intval($request->get_param('limit') ?: 12)));
        $query = [
            'status' => 'publish',
            'type' => ['simple'],
            'limit' => $limit,
            'return' => 'objects',
            'meta_query' => self::agentcart_enabled_meta_query(),
        ];
        if ($search !== '') {
            $query['s'] = $search;
        }
        $products = wc_get_products($query);
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
        foreach ($items as $item) {
            $product_id = self::source_product_id($item);
            $quantity = max(1, min(20, intval($item['quantity'] ?? 1)));
            $product = wc_get_product($product_id);
            if (!$product || $product->get_status() !== 'publish') {
                return new WP_Error('agentcart_product_missing', 'Product not found: ' . $product_id, ['status' => 404]);
            }
            if (!self::is_product_agentcart_enabled($product)) {
                return new WP_Error('agentcart_product_not_enabled', 'Product is not enabled for AgentCart checkout: ' . $product_id, ['status' => 403]);
            }
            if (!$product->is_in_stock() || ($product->managing_stock() && $product->get_stock_quantity() !== null && $product->get_stock_quantity() < $quantity)) {
                return new WP_Error('agentcart_stock_conflict', 'Insufficient stock for product: ' . $product_id, ['status' => 409]);
            }
            $cart_item_key = $cart->add_to_cart($product_id, $quantity);
            if (!$cart_item_key) {
                return new WP_Error('agentcart_cart_rejected_product', 'WooCommerce cart rejected product: ' . $product_id, ['status' => 409]);
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
        $quote_id = 'woo_quote_' . wp_generate_uuid4();
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
            'stock_reserved_until' => null,
            'stock_reservation' => [
                'state' => 'not_reserved',
                'checked_at' => gmdate('c', $now),
                'rechecked_before_order_creation' => true,
            ],
            'expires_at' => gmdate('c', $now + 15 * 60),
            'terms_url' => wc_get_page_permalink('terms') ?: home_url('/terms'),
            'returns_url' => home_url('/returns'),
        ];
        $quote['quote_hash'] = self::quote_hash($quote);
        $quote['payment_requirements'] = self::payment_requirements($quote);
        $quote['refund_policy'] = self::quote_refund_policy();
        set_transient(self::QUOTE_TRANSIENT_PREFIX . $quote_id, $quote, 15 * MINUTE_IN_SECONDS);
        $cart->empty_cart();
        return $quote;
    }

    public static function create_order(WP_REST_Request $request) {
        $body = $request->get_json_params();
        $receipt = isset($body['payment_receipt']) && is_array($body['payment_receipt']) ? $body['payment_receipt'] : [];
        if (empty($receipt['id'])) {
            return new WP_Error('agentcart_bad_request', 'payment_receipt.id is required.', ['status' => 400]);
        }
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
        $quote = get_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id);
        if (!is_array($quote)) {
            return new WP_Error('agentcart_quote_expired', 'Merchant quote is unknown or expired.', ['status' => 409]);
        }
        if (strtotime((string) ($quote['expires_at'] ?? '')) < time()) {
            delete_transient(self::QUOTE_TRANSIENT_PREFIX . $merchant_quote_id);
            return new WP_Error('agentcart_quote_expired', 'Merchant quote has expired.', ['status' => 409]);
        }
        $expected_quote_hash = (string) ($quote['quote_hash'] ?? self::quote_hash($quote));
        $supplied_quote_hash = sanitize_text_field((string) ($body['quote_hash'] ?? ($body['quote']['quote_hash'] ?? '')));
        if ($supplied_quote_hash !== '' && !hash_equals($expected_quote_hash, $supplied_quote_hash)) {
            return new WP_Error('agentcart_quote_mismatch', 'quote_hash does not match the stored merchant quote.', ['status' => 409]);
        }
        if ($supplied_quote_hash === '' && !self::has_valid_merchant_token($request)) {
            return new WP_Error('agentcart_quote_hash_required', 'quote_hash is required for public checkout.', ['status' => 400]);
        }

        $payment_verification = self::verify_payment_receipt($quote, $receipt, $body, $request);
        if (is_wp_error($payment_verification)) {
            return $payment_verification;
        }

        $validated_items = [];
        foreach ($quote['items'] as $item) {
            $product_id = self::source_product_id($item);
            $quantity = max(1, min(20, intval($item['quantity'] ?? 1)));
            $product = wc_get_product($product_id);
            if (!$product || $product->get_status() !== 'publish') {
                return new WP_Error('agentcart_product_missing', 'Product not found: ' . $product_id, ['status' => 404]);
            }
            if (!self::is_product_agentcart_enabled($product)) {
                return new WP_Error('agentcart_product_not_enabled', 'Product is no longer enabled for AgentCart checkout: ' . $product_id, ['status' => 403]);
            }
            if (!$product->is_in_stock() || ($product->managing_stock() && $product->get_stock_quantity() !== null && $product->get_stock_quantity() < $quantity)) {
                return new WP_Error('agentcart_stock_conflict', 'Insufficient stock for product: ' . $product_id, ['status' => 409]);
            }
            $validated_items[] = [$product, $item, $quantity];
        }

        $order = wc_create_order([
            'created_via' => 'agentcart-shopbridge',
            'status' => 'processing',
        ]);
        if (is_wp_error($order)) {
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
        $order->update_meta_data('_agentcart_merchant_quote_id', sanitize_text_field((string) ($body['merchant_quote_id'] ?? '')));
        $order->update_meta_data('_agentcart_payment_receipt_id', sanitize_text_field((string) $receipt['id']));
        $order->update_meta_data('_agentcart_payment_rail', $payment_rail);
        $order->update_meta_data('_agentcart_reason', sanitize_text_field((string) ($body['reason'] ?? '')));
        $order->update_meta_data('_agentcart_quote_hash', $expected_quote_hash);
        $order->update_meta_data('_agentcart_payment_verification', wp_json_encode($payment_verification));
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
        return self::serialize_order_response($order, 'created', $payment_verification);
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
        $remaining_cents = self::cents((float) $order->get_remaining_refund_amount());
        if ($remaining_cents <= 0) {
            return new WP_Error('agentcart_refund_unavailable', 'This order has no refundable amount remaining.', ['status' => 409]);
        }
        $amount_cents = isset($body['amount_cents']) ? intval($body['amount_cents']) : $remaining_cents;
        $amount_cents = max(1, min($amount_cents, $remaining_cents));
        $reason = sanitize_text_field((string) ($body['reason'] ?? 'AgentCart merchant-approved refund'));
        $rail = sanitize_key((string) ($body['rail'] ?? self::payment_rail_from_order($order)));

        $refund_verification = self::verify_refund_request($order, $amount_cents, $reason, $rail, $body);
        if (is_wp_error($refund_verification)) {
            return $refund_verification;
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
        $refund->save();

        $refunds = self::stored_refund_events($order);
        $refunds[] = [
            'refund_id' => (string) $refund->get_id(),
            'amount_cents' => $amount_cents,
            'currency' => $order->get_currency(),
            'rail' => $rail,
            'reason' => $reason,
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

        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'state' => 'refund_recorded',
            'order_id' => (string) $order->get_id(),
            'refund_id' => (string) $refund->get_id(),
            'amount_cents' => $amount_cents,
            'currency' => $order->get_currency(),
            'rail' => $rail,
            'real_refund_verified' => !empty($refund_verification['real_refund_verified']),
            'verification' => $refund_verification,
            'refunds' => self::serialize_refunds($order),
        ];
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
            'payment_verification' => is_array($payment_verification) ? $payment_verification : self::stored_payment_verification($order),
            'refund_policy' => self::refund_policy($order),
            'refunds' => self::serialize_refunds($order),
        ];
    }

    private static function serialize_order_status(WC_Order $order) {
        return [
            'platform' => 'woocommerce-agentcart-plugin',
            'id' => (string) $order->get_id(),
            'number' => $order->get_order_number(),
            'status' => $order->get_status(),
            'payment_status' => $order->is_paid() ? 'paid' : 'unpaid',
            'payment_method' => $order->get_payment_method(),
            'fulfillment' => self::serialize_fulfillment($order),
            'refund_policy' => self::refund_policy($order),
            'refunds' => self::serialize_refunds($order),
            'updated_at' => $order->get_date_modified() ? $order->get_date_modified()->date('c') : null,
        ];
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
                'meta_key' => $meta_key,
                'meta_value' => $meta_value,
            ]);
            if (!empty($existing_orders)) {
                return $existing_orders[0];
            }
        }
        return null;
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

    private static function verify_payment_receipt($quote, $receipt, $body, WP_REST_Request $request) {
        $expected_amount = intval($quote['total_cents'] ?? 0);
        $expected_currency = (string) ($quote['currency'] ?? get_woocommerce_currency());
        $receipt_amount = intval($receipt['amount_cents'] ?? 0);
        $receipt_currency = (string) ($receipt['currency'] ?? '');
        if ($receipt_amount !== $expected_amount || strtoupper($receipt_currency) !== strtoupper($expected_currency)) {
            return new WP_Error(
                'agentcart_payment_amount_mismatch',
                'Payment receipt amount or currency does not match the stored quote.',
                ['status' => 402]
            );
        }

        $verifier_url = self::payment_verifier_url();
        if ($verifier_url !== '') {
            $verification = self::call_payment_verifier($verifier_url, $quote, $receipt, $body);
            if (is_wp_error($verification)) {
                return $verification;
            }
            return $verification;
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
            'rail' => self::payment_rail_from_receipt($receipt, $body),
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'note' => 'Merchant token authenticated AgentCart. Configure a payment verifier before production use.',
        ];
    }

    private static function call_payment_verifier($verifier_url, $quote, $receipt, $body) {
        $rail = self::payment_rail_from_receipt($receipt, $body);
        $payload = [
            'operation' => 'payment',
            'quote' => $quote,
            'quote_hash' => (string) ($quote['quote_hash'] ?? ''),
            'payment_receipt' => $receipt,
            'agentcart_order_id' => sanitize_text_field((string) ($body['agentcart_order_id'] ?? '')),
            'expected' => [
                'amount_cents' => intval($quote['total_cents'] ?? 0),
                'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                'merchant_id' => self::merchant()['id'],
                'rail' => $rail,
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
        $verified_network = (string) ($decoded['network'] ?? '');
        $expected_network = self::tempo_network();
        $verified_recipient = strtolower((string) ($decoded['recipient'] ?? ''));
        $expected_recipient = strtolower(self::tempo_recipient());
        $verified_rail = self::normalize_payment_rail((string) ($decoded['rail'] ?? ''));
        $verified_stripe_profile_id = sanitize_text_field((string) ($decoded['stripe_profile_id'] ?? ''));
        $expected_stripe_profile_id = self::stripe_profile_id();
        $transaction_reference = sanitize_text_field((string) ($decoded['transaction_reference'] ?? ''));
        if (
            $verified_quote_hash === ''
            || !hash_equals($expected_quote_hash, $verified_quote_hash)
            || $verified_amount !== intval($quote['total_cents'] ?? 0)
            || $verified_currency !== $expected_currency
        ) {
            return new WP_Error('agentcart_payment_verifier_mismatch', 'External payment verifier response does not match the quote.', ['status' => 402]);
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
        if ($transaction_reference === '') {
            return new WP_Error('agentcart_payment_reference_required', 'External payment verifier must return a transaction_reference.', ['status' => 402]);
        }
        $existing_orders = wc_get_orders([
            'limit' => 1,
            'return' => 'objects',
            'meta_key' => '_agentcart_payment_transaction_reference',
            'meta_value' => $transaction_reference,
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
        return [
            'state' => 'rail_refund_verified',
            'mode' => 'external_verifier',
            'rail' => $verified_rail,
            'real_refund_verified' => !empty($decoded['real_refund_verified']),
            'amount_cents' => $verified_amount,
            'currency' => $currency,
            'quote_hash' => $quote_hash,
            'original_transaction_reference' => $transaction_reference,
            'refund_reference' => $refund_reference,
            'provider' => sanitize_text_field((string) ($decoded['provider'] ?? 'external_verifier')),
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

    private static function serialize_refunds(WC_Order $order) {
        $result = [];
        foreach ($order->get_refunds() as $refund) {
            $verification_raw = $refund->get_meta('_agentcart_refund_verification', true);
            $verification = is_string($verification_raw) ? json_decode($verification_raw, true) : null;
            $result[] = [
                'id' => (string) $refund->get_id(),
                'amount_cents' => self::cents((float) $refund->get_amount()),
                'currency' => $order->get_currency(),
                'reason' => $refund->get_reason(),
                'rail' => (string) $refund->get_meta('_agentcart_refund_rail', true),
                'verification' => is_array($verification) ? $verification : null,
                'created_at' => $refund->get_date_created() ? $refund->get_date_created()->date('c') : null,
            ];
        }
        return $result;
    }

    private static function refund_policy(WC_Order $order) {
        return [
            'endpoint' => rest_url(self::API_NAMESPACE . '/orders/' . $order->get_id() . '/refunds'),
            'requires_merchant_token' => true,
            'remaining_refundable_cents' => self::cents((float) $order->get_remaining_refund_amount()),
            'currency' => $order->get_currency(),
            'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
            'production_requires_rail_refund_verification' => true,
            'rails' => self::payment_rails(),
        ];
    }

    private static function quote_refund_policy() {
        return [
            'returns_url' => self::merchant()['returns_url'],
            'refund_endpoint_template' => rest_url(self::API_NAMESPACE . '/orders/{id}/refunds'),
            'requires_merchant_token' => true,
            'demo_mode_records_woo_refund_only' => self::payment_verifier_url() === '',
            'production_requires_rail_refund_verification' => true,
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
        return $rail;
    }

    private static function woo_payment_method_for_rail($rail) {
        if ($rail === 'stripe-card-mpp') {
            return 'stripe_card_mpp';
        }
        if ($rail === 'tempo-mpp') {
            return 'tempo_mpp';
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
        return 'AgentCart MPP';
    }

    private static function serialize_fulfillment(WC_Order $order) {
        $tracking = self::tracking_from_order_meta($order);
        $delivery_window = self::stored_delivery_window($order);
        $state = $tracking['tracking_number'] ? 'shipped' : ($order->has_status('completed') ? 'fulfilled' : 'preparing');
        return [
            'state' => $state,
            'order_status' => $order->get_status(),
            'carrier' => $tracking['carrier'],
            'tracking_number' => $tracking['tracking_number'],
            'tracking_url' => $tracking['tracking_url'],
            'estimated_delivery_window' => $delivery_window,
            'source' => $tracking['source'],
            'note' => $tracking['tracking_number'] ? 'Carrier tracking metadata was read from WooCommerce order meta.' : 'No carrier tracking metadata is attached yet.',
        ];
    }

    private static function tracking_from_order_meta(WC_Order $order) {
        $result = [
            'carrier' => null,
            'tracking_number' => null,
            'tracking_url' => null,
            'source' => 'woocommerce_order_meta',
        ];
        $shipment_items = $order->get_meta('_wc_shipment_tracking_items', true);
        if (is_array($shipment_items) && !empty($shipment_items)) {
            $item = reset($shipment_items);
            if (is_array($item)) {
                $result['carrier'] = sanitize_text_field((string) ($item['tracking_provider'] ?? $item['custom_tracking_provider'] ?? ''));
                $result['tracking_number'] = sanitize_text_field((string) ($item['tracking_number'] ?? ''));
                $result['tracking_url'] = esc_url_raw((string) ($item['custom_tracking_link'] ?? $item['tracking_link'] ?? ''));
                $result['source'] = 'woocommerce_shipment_tracking';
                return $result;
            }
        }
        $result['carrier'] = sanitize_text_field((string) ($order->get_meta('_tracking_provider', true) ?: $order->get_meta('_carrier', true)));
        $result['tracking_number'] = sanitize_text_field((string) ($order->get_meta('_tracking_number', true) ?: $order->get_meta('tracking_number', true)));
        $result['tracking_url'] = esc_url_raw((string) ($order->get_meta('_tracking_url', true) ?: $order->get_meta('tracking_url', true)));
        return $result;
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
            'payment_profile' => [
                'verification_mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'tempo_network' => self::tempo_network(),
                'tempo_recipient' => self::tempo_recipient(),
                'stripe_profile_id' => self::stripe_profile_id(),
            ],
        ];
    }

    private static function payment_requirements($quote) {
        return [
            'amount_cents' => intval($quote['total_cents'] ?? 0),
            'currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
            'quote_hash' => (string) ($quote['quote_hash'] ?? self::quote_hash($quote)),
            'checkout_endpoint' => rest_url(self::API_NAMESPACE . '/orders'),
            'idempotency' => [
                'required' => true,
                'accepted_fields' => ['agentcart_order_id', 'idempotency_key', 'Idempotency-Key'],
                'replay_state' => 'idempotent_replay',
            ],
            'verification' => [
                'mode' => self::payment_verifier_url() !== '' ? 'external_verifier' : 'trusted_agentcart_token',
                'external_verifier_configured' => self::payment_verifier_url() !== '',
            ],
            'protocols' => [
                [
                    'id' => 'tempo-mpp',
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
                    'type' => 'card',
                    'available' => self::stripe_profile_id() !== '' && self::payment_verifier_url() !== '',
                    'network_id' => self::stripe_profile_id(),
                    'amount_cents' => intval($quote['total_cents'] ?? 0),
                    'quote_currency' => (string) ($quote['currency'] ?? get_woocommerce_currency()),
                    'settlement_note' => 'Stripe/card MPP requires Stripe machine-payment access, a Stripe profile/network id, and an external verifier that validates Shared Payment Token credentials and refunds.',
                    'setup_required' => self::stripe_profile_id() === '' || self::payment_verifier_url() === '',
                ],
                [
                    'id' => 'http-402-compatible',
                    'scheme' => 'Payment',
                    'quote_hash_required' => true,
                ],
            ],
        ];
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
            'token_address' => '0x20c0000000000000000000000000000000000000',
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
            'id' => defined('AGENTCART_MERCHANT_ID') ? AGENTCART_MERCHANT_ID : 'woocommerce-demo-shop',
            'name' => get_bloginfo('name') ?: 'WooCommerce Demo Shop',
            'merchant_of_record' => [
                'name' => get_bloginfo('name') ?: 'WooCommerce Demo Shop',
                'country' => WC()->countries->get_base_country() ?: 'DE',
                'vat_id' => get_option('woocommerce_store_vat_number') ?: 'demo-vat',
                'support_email' => self::support_email(),
            ],
            'terms_url' => wc_get_page_permalink('terms') ?: home_url('/terms'),
            'returns_url' => home_url('/returns'),
        ];
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

    private static function is_product_agentcart_enabled(WC_Product $product) {
        return $product->get_meta(self::PRODUCT_ENABLED_META, true) === 'yes';
    }

    private static function agentcart_enabled_product_count() {
        if (!function_exists('wc_get_products')) {
            return 0;
        }
        $products = wc_get_products([
            'status' => 'publish',
            'type' => ['simple'],
            'limit' => -1,
            'return' => 'ids',
            'meta_query' => self::agentcart_enabled_meta_query(),
        ]);
        return count($products);
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
                'vat_rate_bps' => self::vat_rate_bps($product),
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
        return [
            'id' => 'woo_' . $product->get_id(),
            'product_id' => 'woo_' . $product->get_id(),
            'source_product_id' => $product->get_id(),
            'merchant_id' => self::merchant()['id'],
            'sku' => $product->get_sku() ?: 'WOO-' . $product->get_id(),
            'title' => wp_strip_all_tags($product->get_name()),
            'description' => wp_strip_all_tags($product->get_short_description() ?: $product->get_description()),
            'category' => $category,
            'brand' => get_bloginfo('name') ?: 'WooCommerce',
            'unit_size' => $product->get_weight() ?: 'unit',
            'image_urls' => $image_urls,
            'price_cents' => self::cents((float) wc_get_price_including_tax($product, ['qty' => 1])),
            'currency' => get_woocommerce_currency(),
            'vat_rate_bps' => self::vat_rate_bps($product),
            'stock' => $product->managing_stock() && $product->get_stock_quantity() !== null ? intval($product->get_stock_quantity()) : 999,
            'availability' => $product->is_in_stock() ? 'in_stock' : 'out_of_stock',
            'shipping_regions' => self::shipping_countries(),
            'eligible_for_agent_checkout' => self::is_product_agentcart_enabled($product),
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
