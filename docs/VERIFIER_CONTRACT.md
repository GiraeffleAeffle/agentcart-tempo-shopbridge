# Payment Verifier Contract

ShopBridge has two payment verification modes:

- `external_verifier`: production shape. ShopBridge calls an external verifier
  before creating a paid WooCommerce order or recording a rail-verified refund.
- `trusted_agentcart_token`: local/private mode. A trusted AgentCart gateway
  creates the WooCommerce order after its own approval and MPP-shaped checkout.
  This is not production settlement.

For production order creation, ShopBridge should also be configured with
checkout mode `external_verifier_only`. That keeps the merchant token available
for private gateway/admin operations without allowing token-authenticated demo
checkout to mark a WooCommerce order paid.

Verifier URLs are public-network endpoints by default: ShopBridge rejects
embedded credentials and private, reserved, loopback, or link-local verifier
hosts unless `AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL=1` is set for a
local/staging deployment. Production payment profiles must leave that override
disabled.

The verifier is intentionally a separate module because the checks are
rail-specific. Tempo stablecoin, Stripe/card MPP, Lightning, bank, or custom
rails should not change the catalog, quote, approval, order, delivery, and audit
flow.

## Payment Verification Request

ShopBridge sends:

```json
{
  "operation": "payment",
  "quote": {},
  "quote_hash": "sha256...",
  "payment_contract": {},
  "payment_contract_hash": "sha256...",
  "payment_receipt": {},
  "agentcart_order_id": "order_...",
  "expected": {
    "quote_hash": "sha256...",
    "amount_cents": 1480,
    "currency": "USD",
    "merchant_id": "woocommerce-demo-shop",
    "rail": "tempo-mpp",
    "payment_contract_hash": "sha256...",
    "tempo_network": "testnet",
    "tempo_recipient": "0x...",
    "stripe_profile_id": "acct_..."
  }
}
```

The canonical Stripe/card MPP fixture is checked in at
`docs/fixtures/verifier/payment-request.stripe-card-mpp.json`.
The canonical Tempo MPP fixture is checked in at
`docs/fixtures/verifier/payment-request.tempo-mpp.json`.

For the bundled verifier, `amount_cents`, `currency`, `rail`, `quote_hash`, and
`merchant_id` must come from the authenticated merchant's `expected` block or
trusted `quote` object. Quote fallbacks are `total_cents`, `currency`, `rail`,
`quote_hash`, and `merchant_id` (or `merchant.id`), respectively. The caller
must obtain these values from its server-side quote/configuration, not copy
them from buyer-supplied payment proof. `payment_receipt` fields are compared
against those expectations and never supply missing values. A top-level
`quote_hash` alone is not sufficient, and the deployment's default currency
does not substitute for a missing payment expectation. Missing expectations
are rejected with HTTP 400 before settlement lookup or replay claim.

For Tempo, `expected.tempo_recipient` and `expected.tempo_network` must name the
merchant-configured destination. If omitted, they may come only from the
trusted quote's `payment_requirements.protocols` entry with `id=tempo-mpp`
(`recipient` and `tempo_network` or `network`). Missing recipient/network is
HTTP 400; the recipient must be a valid EVM address. Proof/receipt destination
fields may be compared but never become the settlement target.

The bundled verifier supports `tempo-mpp`, `stripe-card-mpp`, and
`x402-compatible`. The x402 adapter is restricted to v2 exact EIP-3009 USDC on
Base Sepolia; its requirements and receipt use `amount` for atomic units.

The verifier must reject the payment unless it can prove:

- the payment credential or receipt is valid for the selected rail;
- the payment is bound to the exact `quote_hash`;
- the `payment_contract_hash` matches every supplied copy in the quote,
  receipt, request, and verifier response;
- amount and currency match the trusted quote; no quote-bound FX conversion is
  implemented by the bundled verifier;
- selected rail matches the receipt and merchant setup;
- Tempo recipient and network match the merchant configuration for Tempo rails;
- Stripe profile matches the merchant configuration for Stripe/card rails;
- x402 network, token asset, payTo, and atomic `amount` match the quote; the
  signed nonce commits to the quote hash, payment contract hash, and exact
  checkout resource URL;
- the transaction reference has not been used before;
- the payment was not expired, revoked, or already refunded.

Expected success response:

```json
{
  "ok": true,
  "quote_hash": "sha256...",
  "payment_contract_hash": "sha256...",
  "amount_cents": 1480,
  "currency": "USD",
  "rail": "tempo-mpp",
  "network": "testnet",
  "recipient": "0x...",
  "payer_address": "0x...",
  "payer_source": "did:pkh:eip155:...",
  "asset": "0x...",
  "pay_to": "0x...",
  "amount": "14800000",
  "transaction_reference": "0x...",
  "replay_reference": "0x...",
  "replay_request_hash": "sha256...",
  "real_settlement_verified": true
}
```

The canonical Stripe/card MPP success fixture is checked in at
`docs/fixtures/verifier/payment-success.stripe-card-mpp.json`.
The canonical Tempo MPP success fixture is checked in at
`docs/fixtures/verifier/payment-success.tempo-mpp.json`.

ShopBridge rejects mismatched quote hash, payment contract hash, amount,
currency, rail, rail-specific merchant recipient/profile fields, or missing
transaction reference. Exact verifier retries may return
`idempotent_replay: true` with the same transaction reference. Reused payment
references with different amount, currency, quote hash, payment contract hash,
rail, or destination/profile fail closed with `replay_conflict: true`.

## Refund Verification Request

ShopBridge sends:

```json
{
  "operation": "refund",
  "merchant": {},
  "order": {
    "id": "123",
    "agentcart_order_id": "order_...",
    "quote_hash": "sha256...",
    "transaction_reference": "0x...",
    "payment_verification": {}
  },
  "refund": {
    "amount_cents": 1480,
    "currency": "EUR",
    "reason": "Customer requested refund",
    "rail": "stripe-card-mpp",
    "requested_reference": "refund-order-123-1",
    "recipient": "0x...",
    "asset": "pathUSD"
  },
  "expected": {
    "amount_cents": 1480,
    "currency": "EUR",
    "quote_hash": "sha256...",
    "original_transaction_reference": "0x...",
    "refund_recipient": "0x...",
    "asset": "pathUSD"
  }
}
```

The canonical Stripe/card MPP refund request fixture is checked in at
`docs/fixtures/verifier/refund-request.stripe-card-mpp.json`.
The canonical Tempo MPP refund request fixture is checked in at
`docs/fixtures/verifier/refund-request.tempo-mpp.json`.

The requested refund rail must be available for the order currency and equal
the original payment rail. ShopBridge rejects any other rail with
`agentcart_refund_rail_mismatch`; selecting an available alternative rail does
not authorize refunding a payment made on a different rail.

The verifier must execute or verify the refund through the original rail and
return:

```json
{
  "ok": true,
  "amount_cents": 1480,
  "currency": "EUR",
  "quote_hash": "sha256...",
  "original_transaction_reference": "0x...",
  "rail": "stripe-card-mpp",
  "refund_reference": "re_...",
  "replay_reference": "re_...",
  "replay_request_hash": "sha256...",
  "real_refund_verified": true
}
```

The canonical Stripe/card MPP refund success fixture is checked in at
`docs/fixtures/verifier/refund-success.stripe-card-mpp.json`.
The canonical Tempo MPP refund success fixture is checked in at
`docs/fixtures/verifier/refund-success.tempo-mpp.json`.

Tempo refund fixtures are deliberately USD/pathUSD denominated. A Tempo refund
success response must bind the refund transfer to the original transaction
reference, merchant recipient, source/refund recipient, network, asset, quote
hash, and replay reference before `real_refund_verified=true` is accepted. Do
not claim EUR settlement or EUR refunds from a pathUSD proof: the bundled
verifier has no quote-bound FX implementation.

Negative contract fixtures are checked in at `docs/fixtures/verifier/negative/`.
They cover amount mismatch, quote-hash mismatch, payment-contract mismatch,
Stripe profile mismatch, payment reference replay, payment replay conflict,
refund original-reference mismatch, missing refund requested reference, and
refund reference replay.

ShopBridge requires a refund idempotency key before calling the verifier. It
rejects refund amounts above the remaining refundable amount, exact idempotent
replays return the existing WooCommerce refund, and conflicting replays fail
closed. ShopBridge also rejects mismatched `quote_hash`, original transaction
reference, rail, amount, currency, missing refund reference, or a reused refund
reference already recorded on the same order. A configured external verifier
must return `real_refund_verified=true`; otherwise ShopBridge does not create a
WooCommerce refund record for that verifier response. AgentCart also validates
provider reference, verifier mode/state, amount, currency, and rail before it
marks its own refund record as `real_refund_verified`. Production verifier
implementations should also reject reused refund references globally for the
payment rail/account.

## Current Demo Scope

The repo implements the commerce flow, the verifier contract, a Stripe/card MPP
sandbox verifier for Link CLI testing, a guarded Tempo refund adapter, and an
x402 v2 Base Sepolia settlement adapter. A production verifier still belongs to
the selected payment rail or payment provider deployment because it must carry
provider credentials, refund authority, replay protection, and monitoring.

Tempo, x402, or other CLI proof helpers are value-proof artifacts only. Even on
a successful mainnet command, AgentCart does not set `real_settlement` from CLI
success alone. Latest `mppx` checked on 2026-07-01 is `0.8.1`; the repo had
`0.7.0` pinned before this research. The newer package adds hardening and
x402/EVM surface work, but still does not expose a one-time Tempo refund API for
completed WooCommerce orders. Session-channel `refundedToPayer` receipts cover
unused session deposits, not refunding a completed one-time shop order. Real
settlement and refund claims require the external verifier response to bind
amount, currency, merchant recipient/profile, quote hash, payment
contract hash, and a non-replayed transaction or refund reference.

For Tempo charge-flow settlement, configure the verifier with
`AGENTCART_TEMPO_SETTLEMENT_MODE=verify` and the matching token/asset settings.
The verifier must wait for the Tempo transaction receipt and require an ERC-20
`Transfer` from the proof payer to the merchant recipient for the exact quote
amount before returning `real_settlement_verified=true`. With settlement mode
disabled, the verifier may accept a demo proof for staging, but it must return
`real_settlement_verified=false` and must not make a refund eligible for live
rail execution.

The known pathUSD and USDC.e token addresses are USD-denominated. In verify
mode, a non-USD quote (including EUR 15.80 paid with 15.80 pathUSD) is rejected
with HTTP 400 and `provider_error_class=tempo_settlement_currency_mismatch`
before any replay claim or RPC lookup. Unknown token denominations fail closed;
an asset display-name override cannot change denomination. No quote-bound FX
contract is implemented. Disabled mode retains explicit `demo_fixed_1_1`
proofs for the local EUR demo with `real_settlement_verified=false`.

For Tempo charge-flow refunds, configure the verifier with
`AGENTCART_TEMPO_REFUND_MODE=live`,
`AGENTCART_TEMPO_REFUND_PRIVATE_KEY`, and the matching token/asset settings.
The refund private key must resolve to the original payment recipient, and the
refund recipient must match the original payer address. With refund mode
disabled or a wallet mismatch, the verifier fails closed and ShopBridge does not
record a rail-verified refund.

The current EUR stablecoin decision fixture is
`docs/fixtures/verifier/euro-stablecoin-rail-plan.json`. It pins the first
Tempo staging shop as USD/pathUSD and treats EURC or Monerium EURe as x402/EVM
rail candidates that need facilitator support plus the same verifier/refund
contract before WooCommerce can mark settlement or refunds real.

## x402 v2 Base Sepolia Settlement

`gateway/scripts/verifier-x402.mjs` implements the verifier's x402 rail.
It supports only v2 `exact` EIP-3009 USDC on Base Sepolia (`eip155:84532`),
not mainnet, Permit2, other assets, or x402 refunds. Refund requests fail closed
without moving funds.

| Environment variable | Default / requirement |
| --- | --- |
| `AGENTCART_X402_MODE` | `disabled`; only `disabled` or `settle` |
| `AGENTCART_X402_NETWORK` | `eip155:84532` |
| `AGENTCART_X402_FACILITATOR_URL` | `https://x402.org/facilitator` |
| `AGENTCART_X402_RPC_URL` | `https://sepolia.base.org` |
| `AGENTCART_X402_CONFIRMATIONS` | `1` |
| `AGENTCART_X402_FACILITATOR_TIMEOUT_MS` | `7000`; range `100`–`7000` |

Settle mode requires `AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite` and a
configured `AGENTCART_VERIFIER_REPLAY_STORE_PATH`. Facilitator and RPC URLs
must use HTTPS and resolve to global addresses only; redirects are errors.
Only isolated local tests may opt into private outbound URLs with
`AGENTCART_X402_ALLOW_PRIVATE_URLS=true`. Leave this unset in deployments.

An authenticated operation checks facilitator `/supported`, caching supported
capabilities for ten minutes. `/health` performs no facilitator or RPC calls
and is not proof of live facilitator support. The complete path has a 12000 ms
global budget, below the plugin's 15-second request timeout. Verify is capped at
2500 ms, settle at the configured timeout (default 7000 ms), and confirmation
at 1500 ms total. Each RPC call is also capped at 1500 ms and the remaining
global budget; ambiguous submission outcomes always reconcile.

The verifier enforces equality between the advertised requirements and
`paymentPayload.accepted`. Receipts require method `x402-compatible`, status
`authorized`, `x402_version: 2`, atomic `amount`, network, asset, pay_to,
quote_hash, payment_contract_hash, amount_cents, currency, and a padded-base64
v2 PaymentPayload in `x402_payment_signature`.

The signed authorization nonce must be the lowercase 0x-prefixed value:

```text
keccak256(utf8("shopbridge-x402-nonce-v1") || bytes32(quote_hash)
  || bytes32(payment_contract_hash) || keccak256(utf8(resource_url)))
```

Both SHA-256 hashes are decoded from 64 hex characters to 32 bytes.
`resource_url` is the exact PAYMENT-REQUIRED `resource.url`, equal to the
quote's `payment_requirements.checkout_endpoint`. The verifier checks this
commitment before any facilitator call. For quote hash `a` repeated 64 times,
contract hash `b` repeated 64 times, and resource
`https://shop.example/wp-json/agentcart/v1/orders`, the nonce is
`0x68d8b9f6ce3e20691028d2c78b6904e615d34346820c101f4168c4f5a44c74d2`.

`maxTimeoutSeconds` is an integer from 30 through 300. Before `/verify`, the
integer-string authorization times must satisfy `validAfter <= now + 60`,
`now < validBefore`, and `validBefore <= now + maxTimeoutSeconds + 60`.
The buyer handoff uses `validAfter: "0"` and `validBefore = now + maxTimeoutSeconds`.
An expired previously reserved authorization is reconciled, not resubmitted.

Before any possible submission, SQLite records the reservation-time latest
block (`start_block`), a resumable `scan_cursor`, the expiry (`valid_before`),
and the facilitator transaction hash as soon as known. Reconciliation checks
the recorded transaction and scans AuthorizationUsed forward from the fixed
reservation block in chunks of at most 500 blocks, preserving the cursor
across bounded requests. Migrated reservations without a block reference scan
from genesis. The unconfirmed tip is rescanned rather than skipped.

A used nonce remains recoverable until its AuthorizationUsed log and receipt
can be confirmed. Missing logs, RPC errors, and verify-invalid after any prior
submission lease yield retryable `x402_settlement_unconfirmed`, not a terminal
failure. Expiry is definitive only when block B at `latest - confirmations`
has timestamp at least `validBefore` and `authorizationState(from, nonce)`
read pinned to that same block B is false. Wall-clock expiry or an unused nonce
at a lagging latest head is not failure evidence. An authorization-linked
confirmed transfer mismatch can also fail the row. Successful settlement
requires a successful receipt, matching USDC Transfer and AuthorizationUsed
logs, and the configured confirmations; facilitator success alone is not
payment evidence.

Exact stored-success retries return without network calls. Ambiguous retries
reconcile before resubmission. Preserve the signed authorization and database;
do not re-sign, discard reservations, or replace the database after a timeout.

Validate the checked-in fixtures and the WooCommerce plugin payload field names:

```sh
python3 scripts/verify-verifier-fixtures.py
```

The Stripe sandbox verifier supports lock-protected file-backed replay
protection with `AGENTCART_VERIFIER_REPLAY_STORE_PATH` or
`STRIPE_MPP_REPLAY_STORE_PATH`. If no path is configured, it keeps an in-memory
replay store for the running process. Set
`AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true` for production-shaped verifier
runs; `/health` then fails closed unless a replay store path is configured.
`AGENTCART_VERIFIER_REPLAY_LOCK_TIMEOUT_MS` controls the local lock timeout.
Optionally set `AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH` or
`STRIPE_MPP_REPLAY_JOURNAL_PATH` to append sanitized
`agentcart.verifierReplayJournal.v1` events for accepted claims, exact
idempotent retries, and replay conflicts. Set
`AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL=true` when support/audit operations
must fail closed unless that journal is writable.
`/health` exposes replay-store kind, whether durable replay is required and
configured, lock mode, writeability, bucket counts, replay-store read/write
errors, replay-journal writeability, entry count, and journal errors. Each
accepted replay entry stores a `request_hash` over the replay bucket, provider
reference, and quote/payment/refund fields. Exact repeats are marked as
idempotent; changed repeats are rejected as replay conflicts. The journal hashes
the rail reference instead of writing raw payment or refund references.
Provider failures are classified in JSON with `provider_error_class`,
`provider_status`, `provider_code`, `request_id`, and `retryable` fields.
The sandbox verifier also exposes `/metrics` with process-local operation,
rail, status, rejection, provider-error, latency, replay, settlement, and refund
counters plus replay-journal appended/failed counters, and emits structured
`agentcart.verifierEvent.v1` request logs with a correlation id.
When `AGENTCART_VERIFIER_ALERT_WEBHOOK_URL` is configured, rejected or failed
verifier requests also emit `agentcart.verifier_alert_notification.v1` webhook
events with severity, code, operation, rail, status, quote hash, payment
contract hash, retryability, and correlation id. Repeated alert fingerprints are
throttled by `AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS`.

For production, use a durable store with transactional uniqueness constraints
for payment transaction references, refund requested references, and refund
references. The checked-in lockfile store plus append-only journal is suitable
for sandbox, local self-hosted testing, and support diagnostics; it is not a
managed payment-provider ledger.
