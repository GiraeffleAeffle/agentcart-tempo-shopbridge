# ADR 0011: Onchain Category Declarations Replace Hosted Discovery Routing

## Status

Accepted for the Tempo testnet registry.

## Context

ADR 0010 made Discovery Facets tamper-evident by including them in the full
offchain Registry Record committed by the contract. Efficient category routing
still depended on a hosted Discovery Index, however. That index was not an
eligibility authority, but depending on an AgentCart-operated endpoint to find
category candidates conflicts with the product requirement that public merchant
discovery work from the Merchant Registry itself. Fetching every offchain record
before selecting candidates does not scale and cannot prove that the buyer asked
every relevant shop for a quote.

## Decision

An on-chain Discovery Facets module stores a Category Set Commitment for each
current Registry Record: the current record hash, the hash and size of a bounded
set of canonical category hashes, and a monotonically increasing Category Set
Generation. Before accepting a publication it reads the existing Merchant
Registry and requires the caller to be the active record's controller and the
supplied record hash to equal current contract state. Each category is emitted
as an indexed Onchain Category Declaration containing its category hash, record
id, and generation.

Category slugs remain coarse routing metadata. The module accepts at most eight
non-zero, strictly sorted, unique category hashes and computes the set commitment
itself. When a Registry Record changes, its previous Category Set Commitment no
longer matches the current record hash and therefore cannot route a buyer until
the controller publishes the replacement set. Old declarations remain in chain
history but cannot route a buyer because their generation or record hash no
longer matches current on-chain state.

The Direct Skill hashes the buyer's canonical category query, reads matching
declarations with `eth_getLogs`, checks their generation and set commitment at
the same finalized state as registry membership, and then verifies the full
committed Registry Record and live merchant catalog. It retains a neutral
fallback for uncategorized merchants and ambiguous natural-language queries.
Price, stock, shipping, product text, buyer demand, and ranking remain offchain
and buyer-side under ADR 0003.

Hosted `/records` and `/discovery-index` endpoints may remain as archives,
diagnostics, and compatibility adapters, but they are not configured by default
and are not needed for candidate discovery.

## Consequences

- Category lookup is directly replayable from contract logs through either a
  full RPC or a compatible verified light-client log index.
- The existing immutable Tempo registry and all record ids remain unchanged;
  one controller-authorized on-chain publication is required after each record
  registration or update.
- Registration and metadata updates cost more gas because they publish up to
  eight category declarations.
- Category declarations can still be stale or dishonest, so every selected
  merchant must pass record, domain, manifest, catalog, and quote verification.
- A live multi-shop test must confirm candidate completeness and buyer-side
  quote ranking before merchant outreach begins.

## Validation

The required multi-shop test passed on Tempo Moderato on 2026-08-27. Three
active records declared `tea` through current on-chain category generations.
With no hosted discovery index configured, the Direct Skill matched all three,
verified all three merchant records and domains, obtained three financially
consistent quotes, and selected the lowest final total. See
`docs/MULTISHOP_ONCHAIN_RANKING_TEST.md`.
