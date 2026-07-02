# Onchain Merchant Registry Concept

> Status: design brief for external security/economics review. This document
> turns the current hosted registry alpha into a concrete onchain registry
> direction without writing contract code yet.

## Goal

Create a public merchant discovery source that is:

- resistant to fake shops;
- discoverable by buyer agents and indexers;
- fair to small merchants;
- compatible with ERC-8004-style identity, validation, and reputation;
- privacy-preserving by keeping buyer demand and commerce details off-chain.

The onchain registry is not a marketplace and not a product catalog.

## Existing Groundwork

The repo already has:

- `agentcart.registry_trust_contract.v1` verifier fixtures for domain proof,
  manifest claim hash, endpoint scope, payment binding, freshness, revocation,
  and optional ERC-8004-style metadata;
- `docs/fixtures/registry/onchain-adapter-contract.json`, the compact
  contract-facing projection;
- `gateway/scripts/registry_record.py build --format onchain`,
  `project-onchain`, `append-onchain`, and `index-onchain`;
- hosted registry transparency logs and feed proofs;
- registry signer governance and alert delivery state/history.

That means the next step is not inventing a record shape. The next step is
deciding which parts become authoritative onchain state, which parts remain
offchain, and how validation/challenges work.

## Contract Model

The first contract should be small. It should commit to a merchant record, not
store the full merchant record.

```solidity
enum RecordStatus {
    None,
    Active,
    Revoked,
    Challenged,
    Suspended
}

struct MerchantRecord {
    address controller;
    bytes32 recordId;
    bytes32 recordHash;
    string recordURI;
    bytes32 domainHash;
    bytes32 merchantIdHash;
    bytes32 registryClaimHash;
    bytes32 paymentBindingHash;
    bytes32 revocationURIHash;
    uint64 updatedAt;
    RecordStatus status;
    uint256 bond;
    bytes32 latestAttestationHash;
}
```

`recordId` should be deterministic, for example:

```text
keccak256(chain_id, registry_address, lower(domain), merchant_id)
```

The contract emits full lifecycle events so any indexer can rebuild discovery
state:

- `MerchantRegistered(recordId, controller, recordHash, recordURI, domainHash,
  merchantIdHash, registryClaimHash, paymentBindingHash, revocationURIHash,
  updatedAt, bond)`;
- `MerchantUpdated(recordId, recordHash, recordURI, registryClaimHash,
  paymentBindingHash, revocationURIHash, updatedAt)`;
- `MerchantRevoked(recordId, reasonHash)`;
- `MerchantAttested(recordId, validator, attestationHash, evidenceURI)`;
- `MerchantChallenged(recordId, challenger, challengeType, evidenceHash,
  evidenceURI)`;
- `MerchantChallengeResolved(recordId, accepted, resolver, resolutionHash)`.

## Offchain Record

The full registry record remains the existing canonical JSON shape:

- merchant id;
- domain;
- manifest URL;
- registry claim hash;
- payment network and recipient;
- revocation URL;
- supported protocol profile ids;
- shipping countries;
- optional ERC-8004-style mapping fields.

Agents fetch the offchain record from `recordURI`, compute the canonical
`recordHash`, and compare it to onchain state before doing any private quote
request.

## Eligibility Flow

A buyer agent or indexer treats a merchant as eligible only when all checks pass:

1. read active onchain record;
2. fetch full record from `recordURI`;
3. verify full record hash equals `recordHash`;
4. verify `domainHash`, `merchantIdHash`, `registryClaimHash`,
   `paymentBindingHash`, and `revocationURIHash` match the full record;
5. fetch `manifest_url`;
6. verify manifest host matches the registered domain;
7. verify manifest registry claim hash;
8. verify `/.well-known/agentcart-registry-proof.json`;
9. verify revocation document;
10. verify payment recipient/network in the manifest;
11. verify catalog/quote/order endpoints stay on the registered domain;
12. require an accepted validator attestation for public discovery;
13. request private quotes and rank buyer-side only.

## Validation

Validation should be a separate adapter behind the same registry trust contract.

Pilot mode:

- one or more permissioned validators;
- validators run the same checks as `gateway/scripts/registry_record.py verify`;
- validators publish an `attestationHash` over the canonical verification
  result and optionally an `evidenceURI`;
- the hosted AgentCart registry can be one validator, but not the only long-term
  path.

Later permissionless mode:

- validators stake before attesting;
- invalid attestations can be challenged with evidence;
- slashing is limited to objective mismatches, not subjective quality.

## Fake-Shop Resistance

Fake shops are blocked by layered checks, not by one expensive stake:

- domain ownership: HTTPS well-known proof on the merchant domain;
- controller ownership: only the onchain controller can update/revoke;
- manifest integrity: registry claim hash must match;
- payment binding: payment destination must match manifest and record;
- revocation: merchant-hosted revocation document remains authoritative for
  emergency record invalidation;
- validator attestation: public eligibility requires an attested verification;
- challenge path: anyone can challenge objective failures.

The merchant bond exists to make spam and objective fraud expensive. It should
be refundable and capped so it does not become paid placement.

## Challenge Types

Initial challenge types should be objective:

| Challenge | Evidence |
| --- | --- |
| `domain_proof_missing` | proof URL response or timeout evidence |
| `domain_proof_mismatch` | proof document hash and expected record hash |
| `manifest_claim_mismatch` | manifest registry claim hash mismatch |
| `payment_binding_mismatch` | manifest payment profile mismatch |
| `revoked_by_merchant` | revocation document listing record hash |
| `endpoint_scope_violation` | endpoint URL outside registered domain |
| `stale_record` | updated timestamp older than freshness window |

Do not include subjective challenges such as "bad price", "slow support", or
"poor product quality" in the base registry. Those belong in reputation or
buyer-side policy.

## Fair Discovery

The registry must not recreate Google-style SEO/ad dominance.

Rules:

- no sponsored ranking field;
- no stake-weighted ranking;
- no product keywords or SEO metadata onchain;
- indexers should expose eligible merchants with deterministic neutral ordering;
- buyer agents choose who to request quotes from using local policy;
- final ranking happens after private final quotes;
- registry UIs may filter by protocol, country, freshness, and verification
  state, but must label this as filtering, not ranking.

Fairness mechanisms:

- low pilot onboarding cost;
- refundable anti-spam bond only after permissionless listing opens;
- open-source indexer so no single registry frontend controls discovery;
- exportable event stream so competing indexers can mirror state;
- challenge/resolution logs are public.

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

ERC-8183 is not the base merchant discovery registry. It is a later fit for
custom jobs, escrowed services, evaluator attestations, and disputes.

## Governance

Before mainnet deployment, decide:

- immutable contract vs upgradeable proxy;
- if upgradeable, timelock and multisig owner;
- whether emergency pause blocks writes only, never reads;
- validator add/remove process;
- challenge resolver role and appeals;
- slashing destination;
- bond size and maximum;
- data retention for evidence URIs;
- migration path to a new registry.

Production default should prefer simple and conservative:

- pause writes only;
- no admin ability to delete history;
- no admin ability to rank merchants;
- all state changes emitted as events;
- public runbook for validator key rotation and registry migration.

## Execution Plan

1. **External review**: send `docs/prompts/onchain-registry-security-review.md`
   to an independent reviewer/agent.
2. **Contract interface fixture**: add a Solidity interface and JSON fixtures
   that mirror this concept without deploy logic.
3. **Local contract prototype**: implement register, update, revoke, attest,
   challenge, and resolve with unit tests.
4. **Indexer adapter**: read contract events into existing Registry Record
   verifier flow.
5. **ShopBridge/admin integration**: generate registration transaction payloads
   or a CLI script from the merchant bundle.
6. **Testnet drill**: deploy to a testnet, register the staging USD shop,
   verify through the indexer, revoke, challenge, and recover.
7. **Pilot gate**: require recorded evidence before any production claim.

## Open Questions For Review

- Should the first contract store `recordURI` as a string, or only emit it in
  events while storing `recordHash` and `recordURIHash`?
- Is a permissioned validator set acceptable for the first public pilot?
- What objective challenge rules are slashable without harming honest small
  merchants?
- Should merchant bonds be required at all before permissionless registration?
- Which chain is the first testnet target?
- How should multiple registries interoperate if communities run their own
  merchant registries?
