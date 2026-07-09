# USD hardening rollout and testnet settlement evidence

- Recorded at: 2026-07-09T20:36Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Target: `https://woo-usd.agentcart.eu`

## Deployment result

The Ansible USD playbook completed with 24 tasks, 11 changes, zero failures,
and zero unreachable hosts. A root-only rollback archive was created at
`/opt/agentcart-rollbacks/usd-pre-hardening-20260709T202300Z.tar.gz` before
the deployment. WordPress and the verifier were stopped during replay-store
migration, then recreated successfully. The database, WordPress, and verifier
containers were healthy after rollout; the verifier publishes no host port.

The live capability document reported `production_ready=true`,
`verifier_trust_mode=pinned_internal`, and
`internal_verifier_trust_is_pinned=true`. The non-mutating release gate passed
with a USD quote, 500-cent shipping, one VAT line, and all six production setup
steps complete.

## Replay-store migration and drill

The JSON-to-SQLite import migrated 32 claims: 18 payments, 7 refund requests,
and 7 refunds. A second import reported `imported=0` and `skipped=32`, proving
the migration was idempotent. After the settlement smoke, live diagnostics
reported 19 payments, 8 refund requests, and 8 refunds with `writable=true`
and no error.

A consistent SQLite backup was made with `VACUUM INTO` to a temporary database.
`PRAGMA integrity_check` returned `ok`, and diagnostics on the restored copy
reported the same 19/8/8 counts. The temporary drill database was removed.

## Tempo MPP testnet result

The strict settlement harness ran with real refund verifier evidence required:

`AGENTCART_WOO_SMOKE_REQUIRE_REAL_REFUND_VERIFIER_EVIDENCE=1 scripts/woocommerce-usd-mppx-settlement-smoke.sh`

It exited successfully. The quote total was 1,578 cents USD on Tempo testnet
using pathUSD. Payment transaction
`0x786ac168d49ba11a0a2923efff790b06a0ea38aa34a63e360ec5c50cb6f7019e`
was bound to payment contract hash
`230ea41e82a2635dfdc7a3db0749bca784bfeed423d0e836aa06b2121e694c1d`.
WooCommerce order 101 was created as paid. Cancellation correctly moved it to
`cancelled_refund_required` without claiming money returned. Refund 102 then
succeeded with verifier-backed reference
`0x500b8e02ac26cdd586cad4637f1feda4a42f58a28895ed7207d078f48a28f153`
and `real_refund_verified=true`.

Verifier metrics after the run showed one successful payment, one successful
refund, two successful Tempo MPP rail operations, zero rejections, zero errors,
and zero provider errors. This is testnet evidence and is not a real-money
settlement claim.
