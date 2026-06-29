# Verifier Operations Readiness

Status: pilot operations pack for the Stripe/card MPP verifier. This runbook is
for a supervised external beta with a single-host SQLite replay store. It does
not turn the verifier into a managed payment provider or multi-region ledger.

## Live Surfaces

The Stripe/card verifier implementation is
`gateway/scripts/stripe-mpp-verifier.mjs`.

Required HTTP surfaces:

- `GET /health`: readiness snapshot. It reports `ok`, `missing`,
  `replay_store_driver`, `replay_store_kind`, `replay_store_required`,
  `replay_store_durable`, `replay_store_locking`,
  `replay_store_writable`, `replay_store_counts`, `replay_store_error`,
  replay-journal fields, and alert configuration.
- `GET /metrics` or `GET /metrics.json`: operational counters using schema
  `agentcart.verifierMetrics.v1`. If
  `AGENTCART_PAYMENT_VERIFIER_TOKEN` is set, the metrics request must include
  the verifier bearer token.
- structured stdout logs with schema `agentcart.verifierEvent.v1`, including
  `verifier_request` and `verifier_alert_delivery` events.
- verifier alert payloads with schema
  `agentcart.verifier_alert_notification.v1`.

Required metrics fields:

- `success_rate`, `outcomes`, `by_operation`, `by_rail`, and `by_status`;
- `rejections.replay_conflict`;
- `provider_errors`;
- `settlement.real_settlement_verified`,
  `settlement.real_refund_verified`, and `settlement.idempotent_replay`;
- `replay_store` diagnostics using
  `agentcart.verifierReplay.sqlite.v1` when SQLite is selected;
- `replay_journal.appended`, `replay_journal.failed`, and
  `replay_journal.last_error`;
- `alerts.sent`, `alerts.failed`, `alerts.throttled`, and
  `alerts.last_delivery`.

## Pilot Configuration

Use the production payment overlay as the shape for real pilot env files:

```env
AGENTCART_CHECKOUT_MODE=external_verifier_only
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH=/data/verifier/replay-journal.jsonl
AGENTCART_VERIFIER_ALERT_WEBHOOK_URL=https://ops.example.invalid/agentcart-verifier-alerts
AGENTCART_VERIFIER_ALERT_MIN_SEVERITY=warning
AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS=300
```

Before enabling public checkout, capture:

```sh
VERIFIER_BASE_URL=https://verifier.example.com

curl -fsS "$VERIFIER_BASE_URL/health" \
  > pilot-evidence/example-shop/pilot/pilot-payment-mode/verifier_health_or_fixture_result.md

curl -fsS -H "Authorization: Bearer $AGENTCART_PAYMENT_VERIFIER_TOKEN" \
  "$VERIFIER_BASE_URL/metrics" \
  > pilot-evidence/example-shop/pilot/pilot-payment-mode/verifier_metrics_snapshot.md
```

If the verifier is exposed at a different base path, use its real `/health` and
`/metrics` URLs. The evidence file should include the exact URL, timestamp,
operator, redacted command, and JSON snippet.

## Alert Thresholds

Critical alerts require the pilot operator to disable public checkout until the
cause is understood:

- `/health` returns non-2xx or `ok: false`;
- `replay_store_required` is true but `replay_store_durable` is false;
- `replay_store_writable` is false or `replay_store_error` is not null;
- `replay_journal_required` is true but `replay_journal_writable` is false;
- provider errors prevent payment or refund verification for a real pilot order.

Warning alerts require same-day investigation:

- `rejections.replay_conflict` increases during the pilot window;
- `provider_errors` increases for retryable provider classes;
- `replay_journal.failed` increases;
- `alerts.failed` increases or alert delivery is repeatedly throttled.

Info events are recorded but do not stop checkout by themselves:

- verifier restart;
- replay store driver change during maintenance;
- first successful real-settlement or real-refund verification.

The incident owner records each alert response in
`pilot/pilot-payment-mode/verifier_alert_delivery_result.md`, including whether
checkout was paused and what evidence was attached.

## Backup And Restore Drill

Run the drill before real pilot orders. The operator owns both the SQLite replay
store and replay journal.

1. Stop public checkout or put the verifier into a maintenance window.
2. Confirm `/health` reports `replay_store_driver=sqlite`,
   `replay_store_kind=sqlite`, `replay_store_writable=true`, and no
   `replay_store_error`.
3. Back up the SQLite database with SQLite's online backup API:

   ```sh
   sqlite3 /data/verifier/replay-store.sqlite \
     ".backup '/data/verifier/replay-store.backup.sqlite'"
   ```

4. Copy the replay journal with the same timestamp:

   ```sh
   cp /data/verifier/replay-journal.jsonl \
     /data/verifier/replay-journal.backup.jsonl
   ```

5. Record SHA-256 checksums for both files:

   ```sh
   sha256sum /data/verifier/replay-store.backup.sqlite \
     /data/verifier/replay-journal.backup.jsonl
   ```

6. Restore into a temporary path and run diagnostics:

   ```sh
   cp /data/verifier/replay-store.backup.sqlite /tmp/replay-store.restore.sqlite
   node gateway/scripts/verifier-sqlite-replay-store.mjs diagnostics \
     --db /tmp/replay-store.restore.sqlite
   ```

7. Save the commands, checksums, diagnostic output, operator, timestamp, and
   rollback decision in
   `pilot/pilot-payment-mode/sqlite_replay_backup_restore_drill.md`.

Do not re-enable public checkout after host loss until the replay store is
restored or the decision record explicitly accepts a clean replay store with no
open payment/refund investigations.

## Provider Error Review

The verifier classifies provider failures through `provider_error_class` and
counts them in `/metrics.provider_errors`. For each pilot day, record:

- top provider error classes and counts;
- whether any class was retryable;
- affected operation (`payment` or `refund`) and rail;
- correlation ids from structured logs;
- whether the merchant or buyer saw an incorrect state.

Save the review in `pilot/pilot-payment-mode/provider_error_review.md`.

## Pilot Evidence Files

The pilot evidence runner now expects these verifier operations files under
`pilot/pilot-payment-mode/`:

```text
verifier_health_or_fixture_result.md
verifier_metrics_snapshot.md
sqlite_replay_backup_restore_drill.md
verifier_alert_delivery_result.md
provider_error_review.md
```

The release decision should quote these report snippets:

```json
{
  "id": "pilot-readiness",
  "missing_evidence": [],
  "evidence_summary": {
    "missing": 0
  }
}
```

```json
{
  "id": "production-payment-profile",
  "status": "passed",
  "details": {
    "replay_store_driver": "sqlite",
    "checkout_mode": "external_verifier_only"
  }
}
```

If any of those snippets are missing, the go/no-go decision must stay no-go or
explicitly list the accepted risk.
