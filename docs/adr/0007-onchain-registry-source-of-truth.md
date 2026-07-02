# ADR 0007: Onchain Merchant Registry Source Of Truth

## Status

Proposed

## Context

The hosted registry alpha can verify merchant domain proofs, manifests,
revocation documents, endpoint scope, payment bindings, transparency logs, and
feed proofs. It is still operated as an indexer/cache. Public production
discovery needs a neutral source of truth that agents can verify without trusting
one hosted AgentCart registry.

The registry must resist fake shops and sybil spam without becoming an ad
marketplace. ADR 0003 remains binding: the registry anchors merchant identity
and integrity only. Product search, final quotes, and ranking stay buyer-side.

## Decision

Use an onchain registry as the public source of truth for merchant record
commitments, revocations, and validator attestations. Keep full commerce data
offchain.

The first production contract should store only compact identity/integrity
state:

- merchant controller address;
- canonical record id and record hash;
- record URI for the full offchain registry record;
- domain hash and merchant id hash;
- registry claim hash;
- payment binding hash;
- revocation URI hash;
- freshness timestamp;
- status: active, revoked, challenged, or suspended;
- optional refundable merchant bond;
- latest validator attestation hash.

The full registry record remains offchain at `record_uri` or the merchant
bundle URL. Agents fetch it, verify the onchain `record_hash`, then run the
existing registry trust contract checks against manifest, domain proof,
revocation document, endpoint scope, freshness, and payment binding.

## Fake-Shop Resistance

Onchain registration alone must not make a merchant eligible. Eligibility
requires all of:

1. the onchain record is active and not suspended;
2. the full record hash matches the onchain commitment;
3. the merchant controls the registered HTTPS domain through the existing
   well-known proof flow;
4. the manifest registry claim hash matches the onchain record;
5. payment network and recipient match the manifest payment profiles;
6. revocation URL is valid and does not revoke the record;
7. at least one accepted validator attestation confirms the checks.

The pilot can use a permissioned validator set. Permissionless validation can be
added later through stake-backed validator attestations once objective challenge
rules are stable.

## Fairness

Registration bond, validator stake, or challenge bonds must not affect ranking.
They are only anti-spam and accountability mechanisms.

The onchain registry returns an eligible set, not a leaderboard. Buyer agents
rank merchants only after private final quote requests using local policy,
price, delivery, payment readiness, stock, and trust evidence.

Small merchants should have a low-friction path:

- no required stake for supervised pilots;
- bounded refundable bond when permissionless registration opens;
- no paid placement fields;
- deterministic or neutral indexer ordering;
- optional sponsored transaction path operated by a neutral registry service.

## Challenge Scope

Early slashing/challenge rules should cover objective failures only:

- domain proof missing or mismatched;
- manifest claim hash mismatch;
- revocation document revokes the active record;
- payment binding mismatch;
- endpoints leave the registered domain;
- record remains stale past the freshness window.

Subjective quality, price, delivery speed, support quality, and product ranking
must remain offchain signals for buyer-side ranking or separate reputation
adapters. They should not be slashable registry claims in the first contract.

## Consequences

- The hosted registry becomes an indexer, monitor, and convenience API.
- Smart contract work can start from the existing onchain projection fixture
  without moving product, quote, buyer, order, or payment data on-chain.
- The first contract must be paired with an indexer adapter and replayable
  fixtures before a production deployment.
- Governance must be explicit: upgradeability, validator set changes, emergency
  write pause, and slashing rules need review before mainnet.
