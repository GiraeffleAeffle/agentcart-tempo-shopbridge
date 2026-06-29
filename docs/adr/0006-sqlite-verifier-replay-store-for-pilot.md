# ADR 0006: SQLite Verifier Replay Store For Pilot

## Status

Accepted

## Context

The external payment/refund verifier must reject replayed payment transaction
references, refund requested references, and refund references. The current
sandbox verifier uses a JSON replay store guarded by a sibling lockfile. That is
adequate for local demos, but production-shaped pilots need transactional
uniqueness, clearer health diagnostics, and a migration path to a managed
database.

The first public pilot is still a single-operator, self-hosted deployment. The
repo already targets a home-server compose package and avoids adding verifier
runtime dependencies beyond Node, Stripe, MPP tooling, and system packages.

## Decision

Use SQLite as the production pilot replay store for the verifier.

The verifier supports this through:

```env
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
```

SQLite is selected because it gives transactional uniqueness with
`BEGIN IMMEDIATE` and a primary key over `(bucket, reference_hash)`, while still
matching the operational shape of the current single-host deployment. The
verifier stores SHA-256 reference hashes rather than raw rail references in the
SQLite primary key.

The sandbox JSON/lockfile store remains available for local demos and backwards
compatibility. It is not the selected production pilot store.

## Operational Ownership

The gateway/verifier operator owns the SQLite database file, its filesystem
permissions, backups, and restore drills. The merchant operator owns
WooCommerce orders and refund evidence, but does not own verifier replay
storage.

For the home-server deployment, the database lives under the verifier data
volume:

```text
/data/verifier/replay-store.sqlite
```

Operator responsibilities:

- keep the file on durable storage;
- restrict read/write permissions to the verifier service account;
- back up the SQLite database and replay journal together;
- monitor `/health`, `/metrics`, and verifier alert delivery;
- restore the database before re-enabling public checkout after host loss.

## Prototype Contract

The prototype is implemented in
`gateway/scripts/verifier-sqlite-replay-store.mjs` and used by
`gateway/scripts/stripe-mpp-verifier.mjs` when
`AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite`.

The SQLite table enforces uniqueness for these buckets:

- `payments`: payment transaction references;
- `refund_requests`: merchant/provider refund idempotency requested references;
- `refunds`: provider refund references.

Exact replay of the same bucket/reference/request hash is treated as an
idempotent replay. Reuse of the same bucket/reference with different payment or
refund fields returns a replay conflict.

Health and metrics keep the existing verifier surface:

- `/health` reports `replay_store_driver`, `replay_store_kind`,
  `replay_store_required`, `replay_store_durable`, `replay_store_locking`,
  `replay_store_writable`, `replay_store_counts`, and `replay_store_error`;
- `/metrics` includes the same `replay_store` diagnostics snapshot and existing
  replay conflict counters.

The concurrent prototype smoke is:

```sh
bash gateway/scripts/verifier-sqlite-replay-smoke.sh
```

It starts separate Node processes that claim conflicting references against one
SQLite database and proves that only one claim can win per bucket/reference.

## Migration From JSON Lockfile Store

For an existing sandbox replay store:

1. Stop the verifier.
2. Keep the JSON store and replay journal as incident/audit evidence.
3. Create a fresh SQLite store:

   ```sh
   export AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
   export AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
   node gateway/scripts/verifier-sqlite-replay-store.mjs diagnostics \
     --db "$AGENTCART_VERIFIER_REPLAY_STORE_PATH"
   ```

4. If preserving historical replay claims is required, import each JSON bucket
   key as a SQLite claim using the same metadata before restart. For early
   pilots, prefer a clean cutover during a maintenance window and keep the old
   JSON file read-only for audit.
5. Restart the verifier and confirm `/health` reports
   `replay_store_driver=sqlite`, `replay_store_kind=sqlite`,
   `replay_store_durable=true`, and no replay-store error.
6. Keep the old JSON store until the audit owner confirms no open order/refund
   investigation depends on it.

Do not run two verifier instances against different replay stores for the same
merchant/payment rail.

## Dashboard And Alert Requirements

The pilot operator dashboard must show:

- `/health` status and replay-store error state;
- replay store driver, path label, locking mode, writability, and bucket counts;
- `/metrics` replay conflict count by operation and rail;
- provider error class counts and verifier success rate;
- replay journal append/failure counts;
- alert delivery state and last delivery result.

Alerting requirements:

- critical: `/health` is not ok, SQLite store is not writable, or durable replay
  is required but unavailable;
- warning: replay conflict count increases, replay journal writes fail, or
  provider errors become retryable;
- info: verifier restarted or replay store driver changed.

## Consequences

- The pilot gets transactional replay uniqueness without adding a managed
  database dependency.
- SQLite remains a pilot store, not a multi-region registry or provider ledger.
- A later Postgres or managed SQL adapter can preserve the same bucket/reference
  uniqueness contract and health/metrics fields.
- Operators must back up one additional verifier database file.
