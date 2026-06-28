# Registry Trust Fixtures

`trust-fixtures.json` is the shared trust-contract fixture set for registry
verification. The same cases are consumed by the AgentCart service, the
ShopBridge Direct Skill, and `gateway/scripts/registry_record.py`.

The positive fixture represents a merchant-owned HTTPS domain-proof record. The
negative fixtures exercise claim-hash drift, endpoint-domain drift, payment
recipient drift, stale records, revocation documents, onchain identity drift,
and invalid onchain identity metadata. Verifiers should reject each negative
case before catalog or quote calls and expose machine-readable
`verification.errors`.
