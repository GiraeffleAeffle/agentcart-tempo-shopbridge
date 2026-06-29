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
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=json
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/tmp/agentcart-stripe-mpp-replay.json
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS=5000
AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH=/tmp/agentcart-stripe-mpp-replay-journal.jsonl
AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL=false
AGENTCART_VERIFIER_ALERT_WEBHOOK_URL=
AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN=
AGENTCART_VERIFIER_ALERT_MIN_SEVERITY=warning
AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS=300
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
- metrics: `http://127.0.0.1:4260/metrics`
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
- replayed payment, refund request, and refund references

On success it returns the Stripe PaymentIntent id as `transaction_reference`.

Refund requests use the same verifier URL with `operation: refund`; the
verifier calls Stripe refunds against the original PaymentIntent reference.
The refund `requested_reference` is passed to Stripe as the idempotency key and
stored in the replay store after a successful refund response.

`/health` reports the replay store driver/kind, whether durable replay is
required, whether a durable replay store is configured, lock mode, bucket
counts, and any replay-store read error. It also reports the optional replay
journal path, writeability, required flag, entry count, and last journal error.
Set
`AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true` for production-shaped runs so
health fails closed unless `AGENTCART_VERIFIER_REPLAY_STORE_PATH` or
`STRIPE_MPP_REPLAY_STORE_PATH` is set. Set
`AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL=true` when support/audit operations
must fail closed unless `AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH` or
`STRIPE_MPP_REPLAY_JOURNAL_PATH` is writable.
File-backed replay storage uses a sibling `.lock` file around replay mutations
so concurrent verifier processes do not accept the same payment or refund
reference. The replay journal appends sanitized
`agentcart.verifierReplayJournal.v1` events for accepted claims, exact
idempotent retries, and replay conflicts. It hashes the rail reference instead
of writing the raw transaction or refund reference. Stripe provider failures
return structured `provider_error_class`, `provider_status`, `provider_code`,
`request_id`, and `retryable` fields for operator triage.

The selected production pilot replay store is SQLite, recorded in
`docs/adr/0006-sqlite-verifier-replay-store-for-pilot.md`. Use it with:

```sh
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
```

SQLite replay storage enforces transactional uniqueness for payment
transaction references, refund requested references, and refund references. The
prototype and concurrency smoke are:

```sh
node gateway/scripts/verifier-sqlite-replay-store.mjs diagnostics \
  --db /data/verifier/replay-store.sqlite
bash gateway/scripts/verifier-sqlite-replay-smoke.sh
```

Keep the JSON/lockfile store for local sandbox demos or old evidence folders.
For production-shaped pilots, cut over during a maintenance window, keep the old
JSON replay file read-only for audit, start the verifier with the SQLite driver,
and confirm `/health` reports `replay_store_driver=sqlite`,
`replay_store_kind=sqlite`, `replay_store_durable=true`, and no
`replay_store_error`.

`/metrics` returns in-memory JSON metrics for the running verifier process:
success rate, status counts, operation and rail buckets, rejection reasons,
provider error classes, latency, replay counts, and settlement/refund
verification counters. Metrics also include replay journal configured/required
state, entry count, appended/failed write counters, and the last journal error.
Each handled request also emits one structured
`agentcart.verifierEvent.v1` JSON log line with an
`x-agentcart-correlation-id` response header. The metrics endpoint intentionally
does not include payment credentials or bearer tokens.

Verifier failure alert delivery is opt-in. Set
`AGENTCART_VERIFIER_ALERT_WEBHOOK_URL` to receive
`agentcart.verifier_alert_notification.v1` events when verifier requests are
rejected or fail. `AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN` is sent as a Bearer
token, `AGENTCART_VERIFIER_ALERT_MIN_SEVERITY` controls noise, and
`AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS` suppresses repeated alerts for the
same operation, rail, status, and rejection code.

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
