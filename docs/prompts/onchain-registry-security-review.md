# Prompt: Onchain Merchant Registry Security And Fairness Review

You are reviewing the AgentCart ShopBridge onchain merchant registry concept.
Your job is to find security, incentive, fairness, and production-readiness
problems before any smart contract is deployed.

## Context

AgentCart ShopBridge is a WooCommerce retail bridge for agentic commerce.
Merchants opt in by installing a WooCommerce plugin that publishes:

- `/.well-known/agentcart.json`
- `/.well-known/agentcart-registry-proof.json`
- `/.well-known/agentcart-registry-revocations.json`
- `/.well-known/agentcart-registry-bundle.json`

The current hosted registry verifies merchant domain proof, manifest claim hash,
endpoint domain scope, payment binding, freshness, merchant-hosted revocation,
and optional ERC-8004-style identity metadata. The hosted registry is an alpha
indexer/cache, not the intended final source of truth.

Important repo docs:

- `CONTEXT.md`
- `docs/adr/0003-registry-is-identity-and-integrity-not-ranking.md`
- `docs/adr/0007-onchain-registry-source-of-truth.md`
- `docs/MERCHANT_REGISTRY.md`
- `docs/ONCHAIN_MERCHANT_REGISTRY_ADAPTER.md`
- `docs/ONCHAIN_MERCHANT_REGISTRY_CONCEPT.md`
- `docs/fixtures/registry/onchain-adapter-contract.json`
- `docs/STANDARDS_ALIGNMENT.md`

## Non-Negotiables

- The registry must not publish household demand, buyer addresses, private
  shopping tasks, quotes, orders, payment receipts, or live catalog data.
- The registry is identity and integrity infrastructure, not a ranking or ad
  marketplace.
- Merchant remains merchant of record.
- Fake shops must not become eligible merely by paying gas or staking.
- Small merchants must not be excluded by high stake or paid placement.
- Buyer-side agents rank after private final quotes using local policy, price,
  delivery, stock, payment readiness, and trust evidence.

## Proposed Concept To Review

The proposed v1 contract stores only compact state the contract can enforce:

- controller address;
- canonical record hash;
- normalized domain hash;
- contract-set freshness timestamp;
- active/revoked/suspended status;
- current attestation state for the active record hash.

The full record stays offchain. Agents fetch it, verify the hash, then run the
same trust checks as the hosted registry. Public onchain eligibility also
requires the well-known domain proof to bind the merchant domain to the onchain
controller, `chain_id`, registry address, expected record id, and record hash.
Reference indexers may require validator attestations for a verified badge or
default public listing; self-verifying buyer agents can rerun objective checks.
Challenges are v1 event-only flags that trigger monitoring and re-verification,
not status changes, slashing, or challenger payouts.

## Review Tasks

1. Threat-model fake shop registration, registration front-running of public
   merchant bundles, domain takeover, controller key loss, controller key
   compromise, payment-recipient swap, stale record replay, attestation
   carry-over after update, subdomain Sybil registration, IDN/homograph
   impersonation, validator compromise, validator silence, malicious challenger,
   indexer/search censorship, admin key compromise, reorg/finality failure, SSRF
   in validators/indexers, and migration failure.
2. Identify which fields must be stored onchain vs emitted only in events vs
   kept offchain.
3. Evaluate the validator/attestation model. Is permissioned validation safe for
   pilot? What is the minimal path to permissionless validation?
4. Evaluate the bond/challenge/slashing model. Should v1 remain event-only with
   no slashing? If not, which objective failures are safely slashable and which
   should never be slashable?
5. Evaluate fairness. Does any mechanism create paid placement, stake-weighted
   ranking, SEO-style dominance, or a gatekeeping monopoly?
6. Evaluate privacy. Could record fields, events, evidence URIs, or indexer
   behavior leak buyer demand or merchant-sensitive operations?
7. Check standards fit with ERC-8004 identity/validation/reputation and explain
   what should not be mapped to ERC-8183 yet.
8. Propose a minimal first contract interface and event set.
9. Propose test cases and invariants for the contract, indexer, and buyer-agent
   verifier.
10. Recommend go/no-go criteria before testnet deployment and before production.

## Desired Output

Return:

- executive summary;
- top 10 risks ordered by severity;
- concrete contract/interface changes;
- concrete validation/challenge changes;
- fairness recommendations;
- privacy recommendations;
- test plan;
- numbered invariant list that must hold before Solidity implementation;
- production rollout gates;
- any open questions that block implementation.
