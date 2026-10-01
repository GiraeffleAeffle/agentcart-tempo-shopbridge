# Approval And Audit Golden Fixtures

`golden-fixtures.json` defines the shared
`agentcart.approval_audit_hash_contract.v1` fixture set. It pins a canonical
Final Quote, payment receipt, approval decision timestamps, and the expected
hashes for service-backed approvals, skill-only approval/payment handoff,
portable Audit Packet import, and service audit export.

The fixture is intentionally compact. Tests regenerate Approval Records,
approval decisions, payment handoffs, Audit Packets, audit imports, and audit
exports from these inputs, then compare the resulting hashes.

The golden hashes cover a quote without registry provenance. Registry-bound
quotes are covered by the cross-runtime parity test
`test_registry_bound_quotes_have_matching_cross_runtime_approval_contracts` in
`gateway/tests/test_approval_audit_golden_fixtures.py`.

Cross-runtime serialization, Unicode ordering/escaping, and historical ledger
hash preservation are specified by
[`../canonical-json/README.md`](../canonical-json/README.md) and pinned by its
shared vectors. New audit packet imports use raw UTF-8, so non-ASCII approver
names verify identically in the direct skill and gateway.
