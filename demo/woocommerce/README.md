# AgentCart WooCommerce Demo Shop

This is the hackathon fake-shop path recommended by the judges:

```text
WooCommerce merchant installs AgentCart ShopBridge
  -> AgentCart discovers products and asks the merchant for a quote
  -> household policy + Home Assistant approval happen in AgentCart
  -> Tempo MPP proof is attached by AgentCart
  -> ShopBridge creates a paid WooCommerce order
```

The merchant remains merchant of record. The plugin does not scrape another
shop and does not bypass WooCommerce order handling.

## Run Locally

```sh
cd demo/woocommerce
cp .env.example .env
curl -fL -o woocommerce.latest-stable.zip https://downloads.wordpress.org/plugin/woocommerce.latest-stable.zip
docker compose up -d wordpress db
docker compose run --rm wpcli
```

The seed script configures the demo shop with:

- EUR pricing with tax calculation enabled;
- Germany plus nearby EU countries as the allowed shipping set;
- VAT rates for those demo countries;
- a taxable `Tracked parcel` flat-rate shipping method at `4.90 EUR`;
- terms and returns pages used by the ShopBridge manifest;
- AgentCart aftercare defaults for returns, substitution approval, and
  cancellation-request drafts;
- demo tracking metadata for existing AgentCart-created Woo orders.

Open:

```text
http://127.0.0.1:8098
http://127.0.0.1:8098/wp-admin
```

Default demo admin:

```text
merchant / agentcart-demo-admin
```

## Point AgentCart At The Plugin

Set these in AgentCart:

```env
WOOCOMMERCE_MODE=plugin
WOOCOMMERCE_BASE_URL=http://127.0.0.1:8098
WOOCOMMERCE_AGENTCART_TOKEN=agentcart-woo-demo-token
WOOCOMMERCE_MERCHANT_ID=woocommerce-demo-shop
WOOCOMMERCE_MERCHANT_NAME="AgentCart Demo Shop"
```

Then search catalog from AgentCart for:

```text
tea
shaver
detergent
coffee
```

After approval and MPP proof, the WooCommerce admin should show a paid
`processing` order with AgentCart metadata. If you rerun the seeder after an
order exists, it attaches demo carrier/tracking fields so the ShopBridge order
status endpoint can expose them to AgentCart.

## Plugin API

Public discovery, catalog, product, and quote endpoints do not require the merchant token. Paid order creation and refunds require:

```http
X-AgentCart-Merchant-Token: agentcart-woo-demo-token
```

Endpoints:

- `GET /wp-json/agentcart/v1/capability`
- `GET /wp-json/agentcart/v1/catalog?search=shaver`
- `GET /wp-json/agentcart/v1/products/{id}`
- `POST /wp-json/agentcart/v1/quote`
- `POST /wp-json/agentcart/v1/orders`
