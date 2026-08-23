# Onchain Merchant Registry Adapter

Status: v1 Solidity prototype. The repo currently ships an off-chain hosted
registry adapter for pilots. The intended public trust anchor is a smart
contract or append-only registry that can expose the same minimal merchant
commitment and event shape. The proposed source-of-truth concept is tracked in
`docs/ONCHAIN_MERCHANT_REGISTRY_CONCEPT.md` and ADR 0007.

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

The executable projection fixture is:

```text
docs/fixtures/registry/onchain-adapter-contract.json
```

The minimal Solidity interface fixture is:

```text
contracts/interfaces/IAgentCartMerchantRegistry.sol
```

The v1 Solidity implementation is:

```text
contracts/AgentCartMerchantRegistry.sol
```

This first implementation stores controller, domain hash, record hash, status,
freshness timestamps, revocation hashes, per-validator attestation state,
attestation generation, threshold-based quorum summary, flag cooldown metadata,
approval-gated supersession state, and delayed governance actions with bounded
execution windows. It does not include staking, slashing, paid ranking, onchain
catalog data, or challenge payouts. Permissionless flags are event-only.

When Foundry is installed, the repo verification script runs the Solidity
lifecycle tests with the pinned `foundry.toml` settings. Environments without
Foundry still run the registry projection and invariant tests.

The contract-event replay fixture is:

```text
docs/fixtures/registry/onchain-contract-events.json
```

The production-shaped RPC collector is:

```text
gateway/scripts/onchain-registry-indexer.mjs
```

It refuses unfinalized upper bounds, records the finalized block number/hash,
chunks log reads, rejects private or redirecting record URIs, pins each fetch
to the public DNS addresses that passed validation, verifies every fetched
full-record hash, and writes output atomically. Remote buyers also reject a
snapshot older than ten minutes by default. A testnet operator run looks like:

```sh
node gateway/scripts/onchain-registry-indexer.mjs \
  --rpc-url https://rpc.example \
  --registry-address 0xREGISTRY \
  --from-block DEPLOYMENT_BLOCK \
  --output /var/lib/agentcart/onchain-contract-events.json

python3 gateway/scripts/registry_record.py index-contract-events \
  --events-file /var/lib/agentcart/onchain-contract-events.json \
  --output /var/lib/agentcart/onchain-contract-index.json
```

`--allow-private-record-uri` exists only for isolated tests. Do not use it for
a public indexer.

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
- `controller`
- `registry_address`
- `record_id`
- `agent_id`
- `registration_uri`
- `registration_tx_hash`
- `attestation_hash`
- `protocol_profile_ids`
- `supported_protocols`
- `ship_to_countries`

The fixture is a projection and event/indexer shape, not the v1 contract storage
layout. ADR 0007 requires the first contract to store only state it can enforce:
controller, record hash, normalized domain hash, contract-set timestamp, status,
current attestation state, and compact abuse/governance controls. Merchant id,
manifest URL, registry claim hash, payment binding, revocation URL, shipping
countries, and protocol lists remain inside the hashed offchain record and
emitted event projection.

The current `onchain_identity` and `erc8004_identity` fields in registry records
map into optional projection fields. They let early records point at an
ERC-8004-style service id, registry contract, transaction hash, or attestation
hash without making onchain registration mandatory for pilot merchants.

Public onchain eligibility also needs a controller-bound domain proof. The
well-known proof document and trust contract must verify the controller address,
chain id, registry address, expected record id, and record hash before a public
onchain record is considered eligible.

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

## Append-Only Ledger Prototype

The same helper can write and index a local append-only JSONL ledger that mirrors
the event stream a future smart contract or indexer would expose. It stores only
the compact onchain projection plus revocation events.

Append an upsert event:

```sh
python3 gateway/scripts/registry_record.py append-onchain \
  --ledger-file onchain-registry.jsonl \
  --operation upsert \
  --record-file merchant-registry-record.json
```

Append a revoke event:

```sh
python3 gateway/scripts/registry_record.py append-onchain \
  --ledger-file onchain-registry.jsonl \
  --operation revoke \
  --record-hash 0e8f8493e57e69734713cbfdc16c0effda09df4e304b72c08e50ed8187a97bef \
  --reason merchant_admin_revoke
```

Rebuild the index:

```sh
python3 gateway/scripts/registry_record.py index-onchain \
  --ledger-file onchain-registry.jsonl
```

The index command verifies sequence numbers, previous-event hashes, event
hashes, and record hashes before returning active onchain records, revocations,
and a compact proof over record hashes, revoked hashes, and the log head.

## Contract Event Replay

The helper can also replay ordered smart-contract events into the same indexer
shape without deploying Solidity:

```sh
python3 gateway/scripts/registry_record.py index-contract-events \
  --events-file docs/fixtures/registry/onchain-contract-events.json
```

`MerchantRegistered` and `MerchantUpdated` logs must be paired with the fetched
offchain record projection for the advertised `recordURI`; the indexer rejects
the event stream if the projection hash does not match the event `recordHash`.
`MerchantAttested` records attestation metadata for the current record hash,
keyed by validator, and the projection calculates threshold/current state from
validator lifecycle events and expiry. Controller rotation atomically binds a
replacement record hash and URI and clears prior attestations.
`MerchantSuspended` removes the record from active discovery and clears
attestation state until `MerchantUnsuspended` plus fresh attestation.
Force-revocation and supersession request/approval/cancel/activate logs remain
explicit in the projection; activation is the first destructive supersession
step and requires validator or owner approval plus the post-approval delay.
`MerchantFlagged` remains event-only so it never changes eligibility by itself.

The hosted registry feed proof can also be RSA-SHA256 signed. Operators should
sign the canonical feed-proof signature payload and publish the public key URL
next to any external or onchain anchor. The anchor must pin only the feed-proof
payload hash and transparency-log head, not merchant catalogs, prices, private
quotes, orders, buyer demand, or payment receipts.

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
2. Wait for the configured finality depth before accepting a payment binding.
3. Reject records missing required projection fields.
4. Verify the canonical record hash when the full record is available.
5. Normalize and hash the domain with the configured IDN/punycode and
   public-suffix-list rules.
6. Verify the full record domain matches the onchain domain hash.
7. Fetch the merchant manifest from `manifest_url`.
8. Verify the manifest domain matches the registered domain.
9. Verify the manifest registry claim hash matches `registry_claim_hash`.
10. Check the controller-bound domain proof document.
11. Check revocation URL and revocation document.
12. Verify payment network and recipient match manifest payment profiles.
13. Reject catalog, quote, or order endpoints outside the registered domain.
14. Apply the configured attestation policy.
15. Run private quote requests and buyer-side ranking only after verification.

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

The proposed onchain registry concept keeps this conservative order:
controller-bound domain proof and validator attestations come before
permissionless stake/slashing. v1 challenges are event-only. Any future merchant
bond must be fixed-size, refundable, capped, and excluded from ranking.

## Standards Fit

ERC-8004 is the closest current standard direction for public identity,
reputation, and validation mapping. AgentCart should keep using its stable
commerce model internally, then map the merchant registry projection into
ERC-8004-style identity/validation metadata at the edge.

ERC-8183-style escrow and evaluator attestations are a later fit for custom
orders, services, pre-orders, and disputes. They should not complicate normal
WooCommerce grocery/retail checkout.
