// Only resumes ledger operations created by an already-authorized refund request.
import crypto from 'node:crypto';
import { runSqlite, sqlString as q } from './verifier-sqlite-replay-store.mjs';

export function reconciliationQueue(db) {
  const rows = sql => JSON.parse(runSqlite(db, `.timeout 5000\n${sql}`, { json: true }).trim() || '[]');
  runSqlite(db, `CREATE TABLE IF NOT EXISTS refund_reconciliation (
    request_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at INTEGER NOT NULL DEFAULT 0, lease_token TEXT NOT NULL DEFAULT '',
    lease_until INTEGER NOT NULL DEFAULT 0, last_error_code TEXT NOT NULL DEFAULT '');`);
  return {
    claim(now = Date.now()) {
      const token = crypto.randomUUID();
      const result = rows(`BEGIN IMMEDIATE;
        INSERT OR IGNORE INTO refund_reconciliation(request_key)
          SELECT request_key FROM refund_operations WHERE state IN ('reserved','prepared','pending')
          AND request_key NOT IN (SELECT request_key FROM refund_reconciliation)
          ORDER BY created_at LIMIT 1000;
        UPDATE refund_reconciliation SET lease_token=${q(token)}, lease_until=${now + 300000}, attempts=attempts+1
          WHERE request_key=(SELECT r.request_key FROM refund_reconciliation r JOIN refund_operations o USING(request_key)
          WHERE o.state IN ('reserved','prepared','pending') AND r.attempts < 8
          AND r.next_attempt_at<=${now} AND r.lease_until<=${now}
          ORDER BY r.next_attempt_at,o.created_at,r.request_key LIMIT 1)
          RETURNING request_key, attempts, lease_token;
        COMMIT;`);
      return result[0] || null;
    },
    finish(claim, error, now = Date.now()) {
      const delay = Math.min(3600000, 60000 * 2 ** Math.min(claim.attempts - 1, 6));
      // A stale worker cannot release the lease of a replacement worker.
      runSqlite(db, `UPDATE refund_reconciliation SET lease_until=0, lease_token='',
        next_attempt_at=${now + delay}, last_error_code=${q(error ? 'provider_retry_failed' : '')}
        WHERE request_key=${q(claim.request_key)} AND lease_token=${q(claim.lease_token)};`);
    },
    diagnostics(now = Date.now()) {
      const item = rows(`SELECT COUNT(*) AS queued,
        COALESCE(SUM(CASE WHEN r.attempts>=8 THEN 1 ELSE 0 END),0) AS exhausted,
        COALESCE(SUM(CASE WHEN r.lease_until>${now} THEN 1 ELSE 0 END),0) AS leased
        FROM refund_reconciliation r JOIN refund_operations o USING(request_key)
        WHERE o.state IN ('reserved','prepared','pending');`)[0];
      return item;
    },
  };
}

export async function reconcileRefunds({ store, queue, advance, now = Date.now, limit = 10 }) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) throw new Error('reconciliation_batch_invalid');
  const result = { attempted: 0, succeeded: 0, errors: 0 };
  const started = now();
  for (let i = 0; i < limit; i++) {
    if (now() - started >= 45000) break;
    const claim = queue.claim(now());
    if (!claim) break;
    result.attempted++;
    let failed = false;
    try {
      const op = store.get(claim.request_key);
      if (!op || !['reserved', 'prepared', 'pending'].includes(op.state)) continue;
      const updated = await advance(op);
      if (updated.state === 'succeeded') result.succeeded++;
    } catch {
      failed = true;
      result.errors++;
    } finally {
      queue.finish(claim, failed, now());
    }
  }
  return result;
}
