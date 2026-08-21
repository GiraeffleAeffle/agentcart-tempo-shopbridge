# ADR 0007: Onchain Merchant Registry Source Of Truth

## Status

Accepted for the testnet pilot; production eligibility remains gated by ADR
0008 and the evidence below.

## Implementation Status

As of 2026-08-21, the technical testnet baseline is implemented:

- `AgentCartMerchantRegistry` implements registration, immutable hash-level
  revocation, suspension, validator attestations, atomic controller rotation,
  and delayed supersession/recovery;
- the AgentCart Service, Direct Skill, and registry tooling consume one shared
  registry-trust module for claim, proof, endpoint, payment, freshness,
  revocation, and controller-bound onchain checks;
- one shared onchain projection replays lifecycle events, retains historical
  record hashes, and fails closed on malformed or non-finalized envelopes;
- the reference indexer reads through the RPC `finalized` tag and records the
  finalized block number and hash, while the registry chart can refresh and
  atomically publish only complete snapshots without Kubernetes API access; and
- the public-registry chart can expose immutable, content-addressed full-record
  documents for event replay and recovery.

The contract is deployed empty on Tempo Moderato as described in ADR 0008.
No merchant registration, revoke/recovery lifecycle, independent review, or
production/mainnet deployment is complete yet. Those are acceptance evidence,
not missing data-model design.

## Context

The hosted registry alpha can verify merchant domain proofs, manifests,
revocation documents, endpoint scope, payment bindings, transparency logs, and
feed proofs. It is still operated as an indexer/cache. Public production
discovery needs a neutral source of truth that agents can verify without
trusting one hosted AgentCart registry.

ADR 0003 remains binding: the registry anchors merchant identity and integrity
only. Product search, final quotes, order data, payment receipts, buyer demand,
and ranking stay offchain and buyer-side.

The registry can prove authenticity and integrity of a merchant claim. It cannot
prove that a first-party merchant is honest, will ship goods, or will provide
good support. Fraud resistance beyond identity/integrity belongs in later
reputation, delivery, refund, and dispute evidence.

## Decision

Use an onchain registry as the public source of truth for merchant record
commitments, revocations, and validator attestations. Keep full commerce data
offchain.

The first production contract should store only state that the contract can
enforce:

- merchant controller address;
- canonical record hash;
- normalized domain hash, with one active record per domain hash;
- contract-set freshness timestamp;
- status: active, revoked, or suspended;
- current per-validator attestation state and conservative quorum summary for
  the active record hash.

Do not store fields that the contract cannot verify from calldata or chain
state, such as merchant id hash, registry claim hash, payment binding hash,
revocation URI hash, supported protocols, shipping countries, or product/search
metadata. Emit record URI and other projection fields in events so indexers can
replay state, but keep the hash commitment as the onchain source of truth.

The full registry record remains offchain at `record_uri` or the merchant
bundle URL. Agents fetch it, verify the onchain `record_hash`, then run the
existing registry trust contract checks against manifest, domain proof,
revocation document, endpoint scope, freshness, and payment binding.

## Controller-Bound Domain Proof

Onchain eligibility requires a domain proof that binds the merchant-controlled
domain to the onchain controller. A public merchant bundle without this binding
is copyable and can be front-run by an attacker.

The well-known proof document and `agentcart.registry_trust_contract.v1` must be
extended before Solidity deployment to include and verify:

- `controller`;
- `chain_id`;
- `registry_address`;
- expected `record_id` or the deterministic inputs used to derive it;
- `record_hash`.

A proof missing these fields can still support hosted alpha discovery, but it
must not satisfy onchain public eligibility. The controller key should not live
on the WordPress web server.

## Eligibility

Onchain registration alone must not make a merchant eligible. A buyer agent or
indexer treats a merchant record as eligible only when all checks pass:

1. the onchain record is active and not suspended;
2. the full record hash matches the onchain commitment;
3. the registered domain is normalized consistently, including IDN/punycode and
   public-suffix-list handling;
4. the merchant controls the registered HTTPS domain through the controller-bound
   well-known proof flow;
5. the manifest registry claim hash matches the full record;
6. payment network and recipient match the manifest payment profiles;
7. revocation state does not revoke the record hash;
8. catalog, quote, and order endpoints stay on the registered domain;
9. validator attestation, when required by an indexer or badge, commits to the
   same `record_id`, `record_hash`, validator, and expiry.

Reference indexers can require attestation for a "verified" badge or default
public listing. Self-verifying buyer agents may rerun the objective checks
directly; validator silence must not become the only way to censor a legitimate
merchant.

## Attestation Invariants

The first contract must make attestation lifecycle rules explicit:

- an attestation commits to `record_id`, `record_hash`, validator, result hash,
  and expiry;
- the contract tracks one current attestation per validator and a configurable
  threshold before `isAttestationCurrent()` returns true;
- aggregate freshness is threshold-based: one short-lived validator cannot
  expire the record while a quorum remains valid, and stale quorum state still
  fails closed;
- identity and status changes increment attestation generation state so prior
  attestations cannot carry over after update, controller rotation, suspension,
  or revocation;
- expired attestations do not satisfy verified listing policy;
- validators are from an explicit set with timelocked changes;
- malicious positive attestations are detectable by rerunning the checks;
- malicious validator silence is handled operationally through multiple
  independent validators, SLA, and appeal path, not through hidden ranking.

## Revocation And Recovery

Revocation is monotonic per record hash. Any valid revocation path can revoke a
record hash; no path can un-revoke it. Recovery is always through a new record
hash.

Authority matrix:

| Scenario | Working lever |
| --- | --- |
| Web server or domain is hostile, controller key is safe | Onchain revoke or suspend by controller |
| Controller key is lost, domain is held | Merchant-hosted revocation document, then domain-proof supersession to re-key |
| Both domain and key are lost, or fraud is detected | Validator-quorum suspension with public evidence |

The contract needs an atomic `setController` for routine key rotation. It also
commits the replacement full-record hash and URI so the controller-bound domain
proof cannot continue to describe the old controller after rotation. The stable
record id remains the identity being rotated; its original deterministic
derivation is not recomputed. Public production
also needs a domain-proof-driven supersession path for lost keys and
registration squatting: a new controller publishes fresh domain proof, enters a
pending request, emits events for monitoring, and becomes active only after
validator or owner approval plus the post-approval activation delay.

The v1 prototype implements this as a supersession request keyed by the
deterministic `record_id` for the new controller. The contract cannot verify the
HTTPS proof by itself, so the request emits `recordURI` and `evidenceURI` for
validators, indexers, and self-verifying agents to inspect. The request is
non-destructive until a validator or owner approves it and the post-approval
activation delay passes. Only then can activation revoke the previous record
hash, free the occupied domain hash, and create the new active record. A
separate owner-only `forceRevoke` exists only as a trusted-operator emergency
escape hatch for pilot registries; it is not a neutrality primitive.

## Fairness

Registration bond, validator stake, or challenge bonds must not affect ranking.
If a merchant registration bond is introduced after the pilot, it must be fixed
size, uniform, refundable, and not exposed as a sortable amount. There is no
merchant slashing in v1.

The onchain registry returns an eligible set, not a leaderboard. Buyer agents
rank merchants only after private final quote requests using local policy,
price, delivery, payment readiness, stock, and trust evidence.

Small merchants should have a low-friction path:

- no required stake for supervised pilots;
- bounded refundable bond only if permissionless registration opens;
- no paid placement fields;
- deterministic or neutral indexer ordering;
- optional sponsored transaction path operated by a neutral registry service.

Fairness also applies to the reference indexer/search layer. Since product
search happens offchain, the reference implementation must be open, replayable,
deterministic where possible, and clear about where filtering ends and
buyer-side ranking begins.

There is also a pre-quote candidate-selection layer between the eligible set and
private RFQs. If thousands of merchants are eligible, an agent will select a
bounded candidate set before asking for quotes. That selection is market-shaping
ranking even though final price ranking happens after quotes. The reference
buyer agent and indexer must therefore make candidate selection explicit,
auditable, and user-configurable. Validator attestation should be advisory by
default; self-verification of the full record, manifest, proof, payment binding,
and revocation state should be the default path for buyers who do not want a
validator-operated gate.

Default candidate selection should avoid fixed positional advantage. Prefer a
buyer-query-seeded randomized sample among self-verified eligible merchants,
then apply user-owned constraints such as country, payment rail, delivery
window, budget, preferred/blocked merchants, and local policy before sending
private RFQs. Registration bond size, validator stake, and sponsored placement
must never be ranking inputs.

## Challenge Scope

The first contract should not include challenge status, challenger payouts, or
slashing. Objective failures are mostly HTTPS and DNS facts that the contract
cannot fetch by itself, so onchain challenge resolution would reintroduce the
same trust assumption as the validator set while adding denial-of-service risk.

For v1, permissionless challenges are event-only flags:

- they do not change merchant eligibility by themselves;
- they do not lock a bond;
- they are cooldown-limited per flagger and record;
- their evidence URI is untrusted input and must not be fetched by indexers
  without the same URL-safety controls used for merchant endpoints;
- they trigger validator re-verification and public monitoring;
- suspension requires controller action, validator quorum, or timelocked
  governance with public reason.

Future challenge economics require real operational data about false positives,
transient outages, and malicious reports before they are allowed to affect
merchant status.

## Governance

Production default should prefer simple and conservative:

- immutable v1 contract where feasible;
- migration through event replay into a successor registry;
- writes-only pause, never read blocking;
- timelocked validator set changes;
- delayed emergency recovery and attestation-threshold changes, with scheduled
  actions expiring after a bounded execution window;
- two-step ownership transfer, with the production owner set to a timelocked
  multisig or equivalent public governance process;
- admin can suspend with public reason, and cannot update merchant controller,
  record hash, or record URI;
- no admin ability to delete history;
- no admin ability to rank merchants.

Pause remains an immediate trusted-operator emergency brake in the prototype.
Until ownership, pause, validator changes, and emergency recovery are controlled
by a timelocked multisig or equivalent public governance process, the deployment
must be described as a trusted-operator pilot, not a neutral public registry.

## Consequences

- The hosted registry becomes an indexer, monitor, and convenience API.
- Smart contract work can start from the existing onchain projection fixture,
  but the fixture is a projection/event shape, not the contract storage model.
- Controller-bound proof changes must ship before public onchain registration.
- The first contract must be paired with an indexer adapter and replayable
  fixtures before a production deployment.
- Staking, bonded challenges, slashing, and ERC-8183-style dispute flows are
  explicitly later work.
