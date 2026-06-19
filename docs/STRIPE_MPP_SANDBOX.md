# Stripe MPP Sandbox Verifier

The WooCommerce plugin can advertise `stripe-card-mpp` when a Stripe profile and
external verifier are configured. The verifier keeps Stripe secrets out of
WordPress and returns quote-bound verification results to ShopBridge.

## Local Secrets

Create an ignored local env file:

```sh
cat > .env.stripe-mpp.local <<'EOF'
STRIPE_SANDBOX_SECRET_KEY=sk_test_...
STRIPE_PROFILE_ID=profile_test_...
MPP_SECRET_KEY=replace-with-random-32-byte-base64
AGENTCART_PAYMENT_VERIFIER_TOKEN=replace-with-random-hex-token
EOF
```

Do not commit this file. `STRIPE_SANDBOX_SECRET_KEY` stays in the verifier
service only.

## Run The Verifier

```sh
cd gateway
set -a
. ../.env.stripe-mpp.local
set +a
npm run stripe:mpp:verifier
```

Default endpoints:

- health: `http://127.0.0.1:4260/health`
- challenge helper: `http://127.0.0.1:4260/stripe-mpp/challenge`
- paid test endpoint: `http://127.0.0.1:4260/stripe-mpp/paid`
- ShopBridge verifier: `http://127.0.0.1:4260/agentcart/verify`

## Configure ShopBridge

In WooCommerce -> AgentCart:

- Stripe profile / network id: `STRIPE_PROFILE_ID`
- Payment verifier URL: externally reachable verifier URL ending in
  `/agentcart/verify`
- Payment verifier token: `AGENTCART_PAYMENT_VERIFIER_TOKEN`

When these fields are set, the manifest and quote payment requirements mark
`stripe-card-mpp` as available.

## Test Credential Flow

Stripe MPP SPT testing uses the Link CLI. The buyer side must obtain an
`Authorization: Payment ...` credential for the exact challenge and include it
in the AgentCart/Woo order request as `payment_receipt.authorization` or
`payment_receipt.credential`.

The verifier checks:

- quote hash
- amount and currency
- `stripe-card-mpp` rail
- Stripe profile id
- MPP challenge signature and expiry
- Stripe SPT charge result

On success it returns the Stripe PaymentIntent id as `transaction_reference`.

Refund requests use the same verifier URL with `operation: refund`; the
verifier calls Stripe refunds against the original PaymentIntent reference.

## Link CLI Smoke Test

After starting the verifier, authenticate Link CLI:

```sh
npx --yes @stripe/link-cli auth login
npx --yes @stripe/link-cli payment-methods list
```

Then run the smoke test with one of the listed payment method ids:

```sh
cd gateway
LINK_PAYMENT_METHOD_ID=csmrpd_... npm run stripe:link:smoke
```

The script creates a test spend request for the configured `profile_test_...`,
pays `POST /stripe-mpp/paid`, and writes raw diagnostic output to `/tmp`.
