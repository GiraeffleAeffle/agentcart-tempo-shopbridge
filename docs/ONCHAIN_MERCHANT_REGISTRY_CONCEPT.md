# Onchain Merchant Registry Concept

> Status: design brief for external security/economics review. This document
> turns the current hosted registry alpha into a concrete onchain registry
> direction without writing contract code yet.

## Goal

Create a public merchant discovery source that is:

- resistant to impersonation, tampering, payment-recipient swaps, stale records,
  and registration spam;
- discoverable by buyer agents and indexers;
- fair to small merchants;
- compatible with ERC-8004-style identity, validation, and reputation;
- privacy-preserving by keeping buyer demand and commerce details off-chain.

The onchain registry is not a marketplace and not a product catalog. It proves
merchant claim authenticity and integrity. It does not prove first-party merchant
honesty; later reputation and dispute evidence handle that.

## Existing Groundwork

The repo already has:

- `agentcart.registry_trust_contract.v1` verifier fixtures for domain proof,
  manifest claim hash, endpoint scope, payment binding, freshness, revocation,
  and optional ERC-8004-style metadata;
- `docs/fixtures/registry/onchain-adapter-contract.json`, the compact
  contract-facing projection and event/indexer shape;
- `gateway/scripts/registry_record.py build --format onchain`,
  `project-onchain`, `append-onchain`, and `index-onchain`;
- hosted registry transparency logs and feed proofs;
- registry signer governance and alert delivery state/history.

The next step is deciding which facts become authoritative onchain state, which
facts remain offchain commitments, and which trust checks must be enforced
before a record can be discovered.

## Threat Model Decisions

The design must specifically cover:

- registration front-running of a public merchant bundle;
- controller key loss or compromise;
- WordPress/domain compromise;
- payment-recipient swaps;
- attestation carry-over after record updates;
- stale record replay;
- subdomain Sybil registration;
- IDN/homograph impersonation;
- validator silence or malicious positive attestations;
- malicious challenge griefing;
- indexer/search centralization;
- reorg and finality windows.

## Contract Model

The first contract should be small. It should commit to a merchant record, not
store the full merchant record or unverifiable sub-hashes.

```solidity
interface IMerchantRegistry {
    enum Status {
        None,
        Active,
        Revoked,
        Suspended
    }

    struct Record {
        address controller;
        bytes32 recordHash;
        bytes32 domainHash;
        uint64 updatedAt;
        uint64 attestedAt;
        uint64 attestationExpiresAt;
        uint16 attestationCount;
        Status status;
    }

    struct Attestation {
        bytes32 recordHash;
        bytes32 resultHash;
        uint64 attestedAt;
        uint64 expiresAt;
    }

    function register(
        bytes32 domainHash,
        bytes32 recordHash,
        string calldata recordURI
    ) external returns (bytes32 recordId);

    function update(
        bytes32 recordId,
        bytes32 recordHash,
        string calldata recordURI
    ) external;

    function setController(
        bytes32 recordId,
        address newController
    ) external;

    function revoke(
        bytes32 recordId,
        bytes32 reasonHash
    ) external;

    function forceRevoke(
        bytes32 recordId,
        bytes32 reasonHash
    ) external;

    function requestSupersession(
        bytes32 domainHash,
        bytes32 recordHash,
        bytes32 reasonHash,
        string calldata recordURI,
        string calldata evidenceURI
    ) external returns (bytes32 pendingRecordId, uint64 availableAt);

    function activateSupersession(
        bytes32 pendingRecordId,
        string calldata recordURI
    ) external;

    function attest(
        bytes32 recordId,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string calldata evidenceURI
    ) external;

    function suspend(
        bytes32 recordId,
        bytes32 reasonHash
    ) external;

    function unsuspend(bytes32 recordId) external;

    function flag(
        bytes32 recordId,
        bytes32 challengeType,
        string calldata evidenceURI
    ) external;

    function attestation(
        bytes32 recordId,
        address validator
    ) external view returns (Attestation memory);

    function setAttestationThreshold(uint16 threshold) external;

    function scheduleGovernanceAction(
        bytes32 actionHash
    ) external returns (uint64 readyAt);

    function acceptOwnership() external;

    event MerchantRegistered(
        bytes32 indexed recordId,
        address indexed controller,
        bytes32 indexed domainHash,
        bytes32 recordHash,
        string recordURI
    );
    event MerchantUpdated(
        bytes32 indexed recordId,
        bytes32 recordHash,
        string recordURI
    );
    event ControllerChanged(
        bytes32 indexed recordId,
        address indexed newController
    );
    event MerchantRevoked(bytes32 indexed recordId, bytes32 reasonHash);
    event MerchantAttested(
        bytes32 indexed recordId,
        address indexed validator,
        bytes32 recordHash,
        bytes32 resultHash,
        uint64 expiresAt,
        string evidenceURI
    );
    event MerchantSuspended(bytes32 indexed recordId, bytes32 reasonHash);
    event MerchantUnsuspended(bytes32 indexed recordId);
    event MerchantFlagged(
        bytes32 indexed recordId,
        address indexed flagger,
        bytes32 challengeType,
        string evidenceURI
    );
    event AttestationThresholdSet(uint16 threshold);
    event GovernanceActionScheduled(
        bytes32 indexed actionHash,
        uint64 readyAt
    );
    event OwnershipTransferStarted(
        address indexed previousOwner,
        address indexed newOwner
    );
}
```

`recordId` should be deterministic from chain, registry, normalized domain, and
merchant identity. The exact formula must be published and included in domain
proof checks.

The contract should not store `recordURI` as mutable state in v1. It emits
`recordURI` in events and stores only the current `recordHash`. Indexers replay
events and fail closed if the URI disappears or no longer serves the committed
record.

## Offchain Record

The full registry record remains the existing canonical JSON shape:

- merchant id;
- normalized domain;
- manifest URL;
- registry claim hash;
- payment network and recipient;
- revocation URL;
- supported protocol profile ids;
- shipping countries;
- optional ERC-8004-style mapping fields.

Agents fetch the offchain record from the latest event URI or merchant bundle,
compute the canonical `recordHash`, and compare it to onchain state before doing
any private quote request.

## Controller-Bound Proof

The current hosted proof validates domain and record consistency. For onchain
eligibility it must also bind the domain to the controller and registry.

Required well-known proof fields for public onchain eligibility:

- `controller`;
- `chain_id`;
- `registry_address`;
- `record_id` or the deterministic inputs needed to derive it;
- `record_hash`.

This prevents a front-runner from copying a public merchant bundle and
registering the canonical slot under the attacker's controller address.

The controller key should be held outside the WordPress server. ShopBridge may
generate transaction payloads, but it should not require the production
controller key to be stored on the web host.

## Eligibility Flow

A buyer agent or indexer treats a merchant as eligible only when all checks pass:

1. read active onchain record after the configured finality depth;
2. fetch the full record from the latest event URI or merchant bundle;
3. verify full record hash equals `recordHash`;
4. normalize domain consistently, including IDN/punycode and public-suffix-list
   handling;
5. verify the full record domain hashes to `domainHash`;
6. fetch `manifest_url`;
7. verify manifest host matches the registered domain;
8. verify manifest registry claim hash;
9. verify `/.well-known/agentcart-registry-proof.json`;
10. verify the proof binds `controller`, `chain_id`, `registry_address`,
    `record_id`, and `record_hash`;
11. verify revocation state does not revoke the record hash;
12. verify payment recipient/network in the manifest;
13. verify catalog/quote/order endpoints stay on the registered domain;
14. verify attestation policy if the indexer/badge requires it;
15. request private quotes and rank buyer-side only.

## Validation

Pilot mode:

- one or more permissioned validators;
- validator set changes are timelocked and public;
- validators run the same checks as `gateway/scripts/registry_record.py verify`;
- validators publish an attestation over `recordId`, `recordHash`, validator,
  result hash, and expiry;
- the contract keeps one current attestation per validator and requires the
  configured attestation threshold before `isAttestationCurrent()` is true;
- aggregate attestation expiry is conservative: if any counted attestation
  expires, the record needs a fresh quorum instead of overstating freshness;
- `update()` clears attestation state;
- expired attestations do not satisfy verified listing policy;
- the hosted AgentCart registry can be one validator, but not the only long-term
  path.

Validator attestations are monitoring and thin-client convenience, not the only
source of truth. Self-verifying buyer agents can rerun the objective checks.
Reference indexers may require attestation for a verified badge or default
public listing, but validator silence needs SLA and appeal handling so it does
not become hidden censorship.

Later permissionless validation should mirror ERC-8004 validation vocabulary
where useful, but stake-backed validation should wait until challenge economics
are backed by operational data.

## Authenticity And Integrity Resistance

The registry blocks impersonation and tampering through layered checks:

- domain control: HTTPS well-known proof on the merchant domain;
- controller binding: proof names the onchain controller, chain, registry, and
  record;
- controller ownership: only the controller can update/revoke/rotate;
- manifest integrity: registry claim hash must match;
- payment binding: payment destination must match manifest and record;
- monotonic revocation: any valid revocation path revokes the record hash;
- validator attestation: public verified listing requires attested verification;
- event-only challenge path: anyone can flag objective failures for monitoring.

The registry does not prove a merchant will ship goods. First-party fraud,
support quality, delivery performance, refund behavior, and product truthfulness
belong in later reputation, delivery/refund evidence, buyer-side policy, and
dispute modules.

Subdomain Sybil protection requires a registrable-domain policy:

- normalize domains before hashing;
- use public-suffix-list/eTLD+1 rules for default uniqueness;
- define an explicit exception path for legitimate multi-tenant subdomain shops;
- handle IDN/punycode and homograph warnings in validators and indexers.

## Revocation And Recovery

Revocation is monotonic per record hash. Any valid path can revoke; no path can
un-revoke. Recovery uses a new record hash.

| Scenario | Working lever |
| --- | --- |
| Web server or domain hostile, controller key safe | Onchain revoke or suspend by controller |
| Controller key lost, domain held | Merchant-hosted revocation document, then domain-proof supersession to re-key |
| Both domain and key lost, or fraud detected | Validator-quorum suspension with public evidence |

`setController` handles routine rotation. Domain-proof-driven supersession is
required before public production: a new controller publishes fresh proof for an
occupied domain hash, enters a pending window, emits monitorable events, and
becomes active only after re-attestation or an explicit challenge window.
Owner-only `forceRevoke` is an emergency pilot recovery path for obvious squats
or broken records. It frees a domain slot with public events, but it is a
trusted-operator power. The prototype requires a delayed governance action for
`forceRevoke`, validator set changes, and threshold changes; production still
needs the owner to be a timelocked multisig or equivalent public governance
process before a neutral public deployment.

## Challenge Scope

The v1 challenge path is event-only.

Initial flags:

| Flag | Evidence |
| --- | --- |
| `domain_proof_missing` | proof URL response metadata |
| `domain_proof_mismatch` | proof document hash and expected record hash |
| `manifest_claim_mismatch` | manifest registry claim hash mismatch |
| `payment_binding_mismatch` | manifest payment profile mismatch |
| `revoked_by_merchant` | revocation document listing record hash |
| `endpoint_scope_violation` | endpoint URL outside registered domain |
| `stale_record` | updated timestamp older than freshness window |
| `homograph_risk` | normalized-domain and display-domain mismatch evidence |

Flags do not change status, lock a bond, or slash anyone in v1. They are
cooldown-limited per flagger and record, and `evidenceURI` must be treated as
untrusted input by indexers and validators. They trigger validator
re-verification and public monitoring. Suspension requires controller action,
validator quorum, or timelocked governance with public reason.

Do not include subjective challenges such as "bad price", "slow support", or
"poor product quality" in the base registry. Those belong in reputation or
buyer-side policy.

## Fair Discovery

The registry must not recreate Google-style SEO/ad dominance.

Rules:

- no sponsored ranking field;
- no stake-weighted ranking;
- no variable bond amount as a visible ranking signal;
- no product keywords or SEO metadata onchain;
- indexers expose eligible merchants with deterministic neutral ordering where
  possible;
- buyer agents choose who to request quotes from using local policy;
- final ranking happens after private final quotes;
- registry UIs may filter by protocol, country, freshness, and verification
  state, but must label this as filtering, not ranking.

The eligible set is not the whole discovery problem. A buyer agent must still
choose which merchants to ask before it has final quotes. That pre-quote
candidate selection is a ranking layer and must be governed explicitly:

- self-verify records by default instead of hard-filtering on a single
  validator badge;
- cap RFQ fan-out and make the cap visible to the owner;
- randomize candidate sampling per buyer query among eligible merchants instead
  of returning a fixed global order;
- let owner policy decide preferred/blocked merchants, payment rails, delivery
  constraints, budget, and local/ethical preferences;
- treat registry/indexer ordering as untrusted input, not as final ranking;
- keep sponsored placement, bond size, and validator stake out of both
  candidate selection and final ranking.

The RFQ layer also needs privacy and abuse controls before broad production:
bounded fan-out, rate limits, optional decoy/crowd batching for sensitive
queries, and merchant-side quote throttles so small shops are not forced to
serve unlimited free quote computation.

Fairness mechanisms:

- low pilot onboarding cost;
- no merchant bond in pilot;
- fixed-size refundable anti-spam bond only if permissionless listing opens;
- open-source reference indexer and search behavior;
- exportable event stream so competing indexers can mirror state;
- public challenge, suspension, and validator logs.

The registry layer returns an eligible set. The search layer decides which
merchants receive quote requests for a buyer task. The reference search/indexer
must be open, replayable, and explicit about the policy it uses; otherwise
monopoly power can move from onchain registry ordering to offchain search.

## Standards Fit

ERC-8004 is the closest standards fit because it defines identity, reputation,
and validation registries for agents. AgentCart should map a merchant shop to an
ERC-8004-style agent/service identity at the edge:

- `agentURI` or registration URI points to the merchant registration file or
  AgentCart registry record;
- onchain metadata can reference the active merchant record id/hash;
- validation registry entries can point to AgentCart validator attestations;
- reputation can later reference objective purchase/refund/delivery evidence
  without changing the base merchant registry.

ERC-8004 should not dictate the first contract storage layout while the standard
is still moving. The edge/indexer mapping should absorb standards drift.

ERC-8183 is not the base merchant discovery registry. It is a later fit for
custom jobs, escrowed services, evaluator attestations, and disputes.

When a merchant publishes both AgentCart metadata and ERC-8004-style metadata,
payment binding and record identity must be consistent or rejected. There should
not be two competing sources of truth for payment destination.

## Governance

Production default should prefer simple and conservative:

- immutable v1 contract where feasible;
- migration through event replay into a successor registry;
- pause writes only, never reads;
- timelocked validator add/remove process;
- admin may suspend with public reason but cannot mutate merchant records;
- no admin ability to delete history;
- no admin ability to rank merchants;
- public runbook for validator key rotation and registry migration.

Buyer agents and indexers must use finalized state before accepting a payment
binding. Reorg/finality policy belongs in the verifier and indexer config.

Validator and indexer fetchers must harden against SSRF because `recordURI`,
manifest URLs, proof URLs, and evidence URIs are attacker-controlled inputs.

## Execution Plan

1. **Review fold-in**: incorporate external review findings into ADR 0007 and
   this concept before implementation.
2. **Controller-bound proof slice**: extend the proof document, trust fixtures,
   plugin output, gateway verifier, and direct skill verifier with controller,
   chain, registry, and record binding.
3. **Contract interface fixture**: add a Solidity interface and event fixtures
   that mirror the minimal v1 surface without deploy logic.
4. **Indexer adapter**: replay contract events into the existing onchain
   adapter index shape and verifier fixtures.
5. **Local contract prototype**: implement register, update, rotate controller,
   revoke, supersession, emergency force-revoke, attest, suspend, unsuspend, and
   event-only flag with invariant tests.
6. **Testnet drill**: deploy to a testnet, register the staging USD shop, verify
   through the indexer, rotate controller, revoke, flag, suspend, and recover.
7. **Pilot gate**: require recorded evidence before any production claim.

## Prototype Invariants

- one active record per normalized domain hash;
- registration cannot rely on a public bundle unless the domain proof binds the
  controller, chain, registry, and record;
- `update()` clears attestation state;
- attestation only satisfies policy for the current `recordHash` and before its
  expiry;
- revoked record hashes are terminal;
- only the controller can update, rotate, or revoke controller-owned fields;
- suspension is reversible only through the defined validator/governance path;
- event replay is sufficient to rebuild the indexer state;
- event-only flags do not change status;
- no contract field can be used for sponsored or stake-weighted ranking.

## Open Questions For Review

- What exact domain normalization and registrable-domain policy should be used
  for `domainHash`?
- What is the minimal supersession flow for squatting and lost-key recovery?
- Is a permissioned validator set acceptable for the first public pilot if
  self-verifying agents can bypass validator silence?
- Which chain is the first testnet target?
- How should multiple registries interoperate if communities run their own
  merchant registries?
