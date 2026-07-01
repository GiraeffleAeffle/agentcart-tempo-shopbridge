# Onchain Merchant Registry Adapter

Status: design contract. The repo currently ships an off-chain hosted registry
adapter for pilots. The intended public trust anchor is a smart contract or
append-only registry that can expose the same minimal merchant record shape.

## Position

The registry is identity and integrity infrastructure, not a marketplace. It
should let agents answer:

- which merchant id controls this domain;
- where the merchant manifest lives;
- which registry claim hash the merchant committed to;
- which payment destination is expected;
- whether the record is fresh or revoked.

It should not publish product catalogs, stock, prices, private quotes, buyer
addresses, household tasks, payment receipts, or order payloads.

## Contract-Facing Record

The executable fixture is:

```text
docs/fixtures/registry/onchain-adapter-contract.json
```

Required fields:

- `record_hash`
- `record_hash_alg`
- `merchant_id`
- `domain`
- `manifest_url`
- `registry_claim_hash_alg`
- `registry_claim_hash`
- `payment_network`
- `payment_recipient`
- `updated_at`
- `revocation_url`

Optional ERC-8004-style mapping fields:

- `chain_id`
- `registry_address`
- `agent_id`
- `registration_uri`
- `registration_tx_hash`
- `attestation_hash`
- `protocol_profile_ids`
- `supported_protocols`
- `ship_to_countries`

The current `onchain_identity` and `erc8004_identity` fields in registry records
map into these optional fields. They let early records point at an ERC-8004-style
service id, registry contract, transaction hash, or attestation hash without
making onchain registration mandatory for pilot merchants.

## Projection Helper

The projection is executable in the registry helper. For a live ShopBridge
manifest:

```sh
python3 gateway/scripts/registry_record.py build \
  --manifest-url https://shop.example/.well-known/agentcart.json \
  --format onchain
```

For an existing registry record:

```sh
python3 gateway/scripts/registry_record.py project-onchain \
  --record-file merchant-registry-record.json
```

The command emits only the contract-facing identity and integrity fields. It
fails closed if required fields such as `registry_claim_hash`, payment binding,
or revocation URL are missing.

## Gateway Role

The gateway registry endpoint is an indexer/cache and monitor, not the source of
truth once the smart contract registry exists. It may cache:

- onchain records;
- verification state and machine-readable verification errors;
- manifest and revocation check timestamps;
- transparency or block/indexer heads.

It must not cache private buyer demand, private quotes, approval decisions,
payment receipts, buyer addresses, or order payloads as registry state.

## Agent Verification

Agents should:

1. Read the record from the smart contract or a trusted indexer.
2. Reject records missing required onchain fields.
3. Verify the canonical record hash when the full record is available.
4. Fetch the merchant manifest from `manifest_url`.
5. Verify the manifest domain matches the registered domain.
6. Verify the manifest registry claim hash matches `registry_claim_hash`.
7. Check revocation URL and revocation document.
8. Verify payment network and recipient match manifest payment profiles.
9. Reject catalog, quote, or order endpoints outside the registered domain.
10. Run private quote requests and buyer-side ranking only after verification.

## Staking Hooks

Staking is intentionally not required for pilot merchants. The adapter contract
names three future extension hooks:

- merchant registration bond: optional anti-spam bond for permissionless public
  listings;
- validator attestation stake: future stake-backed verification that domain,
  manifest, revocation, and payment-binding checks were performed;
- curator challenge bond: future challenge mechanism for stale, fraudulent, or
  policy-ineligible records.

These hooks should be added after the identity layer is stable. Otherwise, the
system risks making merchant onboarding expensive before discovery semantics are
proven.

## Standards Fit

ERC-8004 is the closest current standard direction for public identity,
reputation, and validation mapping. AgentCart should keep using its stable
commerce model internally, then map the merchant registry projection into
ERC-8004-style identity/validation metadata at the edge.

ERC-8183-style escrow and evaluator attestations are a later fit for custom
orders, services, pre-orders, and disputes. They should not complicate normal
WooCommerce grocery/retail checkout.
