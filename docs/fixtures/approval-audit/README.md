# Approval And Audit Golden Fixtures

`golden-fixtures.json` defines the shared
`agentcart.approval_audit_hash_contract.v1` fixture set. It pins a canonical
Final Quote, payment receipt, approval decision timestamps, and the expected
hashes for service-backed approvals, skill-only approval/payment handoff,
portable Audit Packet import, and service audit export.

The fixture is intentionally compact. Tests regenerate Approval Records,
approval decisions, payment handoffs, Audit Packets, audit imports, and audit
exports from these inputs, then compare the resulting hashes.
