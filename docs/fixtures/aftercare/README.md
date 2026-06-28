# Aftercare State Fixtures

`state-fixtures.json` defines the shared
`agentcart.aftercare_state_contract.v1` fixture set for buyer-facing aftercare.
It covers unpaid demo state, paid order, delayed delivery, shipped tracking,
cancellation requiring a separate refund, partial refund, verifier-backed
refund, and refund failure.

The fixtures are consumed by service and Direct Skill tests. Plugin source tests
assert the same field names and untrusted merchant-policy metadata remain
published by the ShopBridge plugin contract surface.
