# sqlite_replay_backup_restore_drill

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:35Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: remote SQLite `VACUUM INTO`, integrity check, and replay diagnostics on a temporary restored copy

## Evidence

The live replay database was copied consistently to
`/tmp/replay-drill.sqlite` using SQLite `VACUUM INTO`. `PRAGMA integrity_check`
on the copy returned `ok`. Running the normal replay-store diagnostics against
the restored copy reported `writable=true`, `error=null`, and exactly the live
counts: 19 payment claims, 8 refund-request claims, and 8 refund claims. The
temporary database and its WAL/SHM sidecars were removed after verification.
The live replay database was never replaced or modified by the drill.

## Talos PVC restart drill (2026-08-23)

The fresh Talos SQLite database contained exactly one `payments`, one
`refund_requests`, and one `refunds` claim after the live testnet flow. An
online backup was written to the same PVC and hashed as
`f7f5d083284781f99a32c75748fa3844893d05285326ec56ac71f48855101d2d`.

After a Kubernetes rollout restart, the replacement pod became Ready and the
three counts matched byte-for-byte. Health reported SQLite immediate-transaction
locking, durable and writable required storage, and a writable required journal.
A later conflict probe returned 409 and left all three counts unchanged.
