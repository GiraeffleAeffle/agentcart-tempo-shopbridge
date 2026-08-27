# ADR 0010: Onchain-Committed Discovery Facets

## Status

Superseded by ADR 0011 for new registry deployments. Retained as the historical
decision behind the first Tempo pilot contract.

## Context

The Merchant Registry is the source of truth for candidate membership and
Registry Record lifecycle, but resolving every active record and querying every
merchant catalog does not scale. Putting a catalog, free-form keywords, or
ranking data in the contract would violate ADR 0003 and create stale,
merchant-controlled search claims.

The contract already commits the SHA-256 of a full offchain Registry Record.
That record can therefore carry bounded public routing metadata without adding
contract fields or making an index authoritative.

## Decision

Add optional `agentcart.discovery_facets.v1` metadata to the Registry Record and
its Manifest claim. The ShopBridge Plugin derives it from the products already
exposed in its catalog snapshot. Version 1 uses canonical WooCommerce product
category slugs, publishes at most eight categories, and records whether that
set is complete or truncated.

Discovery Facets are coarse routing hints only. They do not prove that a
merchant is eligible, that a product exists or is in stock, or that one
merchant should rank above another. Buyer agents must still:

1. reconstruct active candidate membership from the contract;
2. fetch the selected Registry Record and verify its committed hash and
   onchain identity;
3. verify the merchant domain proof, Manifest, payment binding, freshness, and
   revocation state; and
4. query the merchant's current catalog to confirm the requested product.

A replaceable `agentcart.registry_discovery_index.v1` may project category
facets to chain-, registry-, and record-bound onchain identities. The index has
`authority: routing_hint_only` and
is never an eligibility input. Direct-RPC discovery verifies every hinted ID
against the contract and reserves a deterministic neutral fallback candidate
when the configured candidate limit permits it.
If the index is missing, invalid, incomplete, or has no match, discovery falls
back to the bounded query-seeded candidate sample.

Version 1 does not include free-form SEO keywords, product titles, prices,
stock, shipping destinations, buyer queries, sponsored placement, or category
weights. A new taxonomy or a change to the bound requires a versioned schema.

## Consequences

- Large registries can avoid fetching and querying every merchant for common
  category searches.
- The contract remains an identity and integrity module; no migration or new
  storage fields are required.
- Facets are hash-committed and tamper-evident, but may be stale until a
  merchant publishes and enrolls an updated Registry Record.
- Incorrect facets can waste a candidate slot but cannot create eligibility or
  product truth, and the neutral fallback reduces false-negative censorship.
- Merchants without facets remain discoverable through fallback sampling.
- Current Tempo records must be regenerated, re-enrolled, and finalized before
  the public index can honestly advertise their categories.
