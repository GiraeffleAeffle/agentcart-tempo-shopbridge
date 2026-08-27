# ADR 0012: Production Registry Network And Governance

## Status

Proposed. The technical topology and acceptance policy are decided here;
production deployment remains blocked on the named-governance and external
evidence gates below.

## Context

The testnet pilot proved that agents can reconstruct merchant membership and
lifecycle directly from a contract, verify the full merchant record and live
domain documents, route by bounded onchain category commitments, and compare
quotes without trusting the Hosted Registry. It also showed that one registry
network cannot be selected only from payment preference: Tempo-native MPP and
Ethereum x402 buyers have different wallets, verification paths, fees, and
light-client support.

ADR 0008 deliberately left production-network selection open. The project now
has enough technical evidence to define the topology, but not enough social or
operational evidence to deploy it: the pilot owner is an EOA, operator names
and Safe addresses are not agreed, the production-v2 anti-spam/validator design
is not implemented, and no external merchant has completed the enrollment and
recovery drills.

## Decision

Use payment-profile-local registries rather than pretending one chain is a
neutral global registry:

- a Tempo Mainnet registry is the canonical membership path for Tempo-native
  MPP profiles;
- an Ethereum Mainnet registry is the canonical membership path for Ethereum
  x402 profiles and the Myotis-verified buyer mode;
- Gnosis Mainnet is not an initial production registry. If later added, Myotis
  must refresh within the documented weak-subjectivity window and the
  ShopBridge operating profile requires at least one successful sync every 24
  hours;
- every buyer result must display the chain id, registry address, governance
  mode, finalized boundary, and verification authority. A shop appearing on
  one chain is not silently treated as registered on another;
- the current `registry_claim_hash` is network-specific because its claim
  includes payment and `onchain_identity` fields. Both the claim hash and the
  full Registry Record hash therefore differ across networks. Each onchain
  membership and controller lifecycle is independently verified. The buyer UI
  may group records only by the same normalized domain after each network's
  fresh HTTPS domain-control proof passes; it must preserve both identities and
  must not imply one registration covers the other. No unimplemented
  network-neutral claim hash or Hosted Registry list is used for deduplication.

The first production contracts are new v2 deployments. The immutable Moderato
contracts remain public testnet evidence and are never relabeled as production.
Before v2 deployment, the contract must add a bounded removable active-validator
set, bounded quorum expiry work, and a fixed public anti-spam admission policy.
Buyer candidate resolution must backfill failed records within a declared total
request/time budget. These changes receive a fresh security review and exact
source verification before ownership transfer.

Production administration uses one Safe per network with a minimum 2-of-3
threshold and a minimum 48-hour timelock for owner, pause, validator, threshold,
and migration actions. The three roles must be held by distinct people:
product/operator, security/operations, and an independent merchant/ecosystem
representative. The final ADR acceptance commit must name the people, Safe
addresses, signer addresses, recovery contacts, and conflict-of-interest rule;
placeholders are not deployable configuration. Emergency pause may be faster
only through a separately named guardian, can never mutate merchant records,
and must automatically expire or be confirmed through the timelock.

Each production network requires two independently operated finalized-data
paths. Hosted projections may become eligible input only when labeled
`independently_verified`; a single path is `rpc_asserted_complete`. Ethereum
buyers may use a pinned, recently synced Myotis revision as their independent
verification path. Tempo buyers use direct RPC plus the independent hosted
witness until a Tempo-compatible verified light client exists.

## Acceptance gates

This ADR changes from Proposed to Accepted only when all are attached:

1. named 2-of-3 Safe and timelock configuration for each selected network;
2. production-v2 source, tests, threat-model delta, external review, exact
   explorer verification, and deployment/runtime hashes;
3. one external merchant and one non-maintainer buyer completing install,
   enrollment, discovery, quote, payment, refund, controller recovery,
   revocation, and successor-migration drills;
4. measured registration/update cost and sponsorship policy on both networks;
5. matched independent-RPC evidence plus firing, delivery, and resolved alert
   evidence, with a secondary paging destination;
6. a public migration notice format, minimum overlap period, and tested
   successor-contract discovery behavior.

## Consequences

- Tempo users do not need Myotis merely to use the Tempo deployment.
- Ethereum/x402 users can use Myotis without forcing Tempo merchants onto
  Ethereum for payment.
- Dual registration adds merchant work and must be hidden behind the supervised
  enrollment UI, while remaining explicit in approval and audit artifacts.
- The production decision is technically clear, but mainnet writes remain
  blocked until governance becomes a real named arrangement and the v2 and
  external-evidence gates pass.
