# Merchant Registry Security Review — 2026-08-27

## Scope and assurance

This is an independent-model-assisted internal review performed with OpenAI's
Daybreak Blue defensive-security model. It covered the Merchant Registry,
Discovery Facets, Direct Skill trust path, RPC indexers, supervised enrollment,
WordPress registry verification, source-publication workflow, and witness alert
path at commit `eff6d47`.

It is not a third-party audit and does not satisfy the external-review gate in
ADR 0008 by itself. No critical vulnerability was found. One high-severity and
seven medium/low issues were identified.

## Findings and disposition

| Severity | Finding | Disposition |
| --- | --- | --- |
| High | Uncommitted embedded proof/revocation snapshots could take precedence over the merchant's live well-known documents | Fixed for buyer-authoritative live verification: when a fetch adapter is present, embedded control snapshots are ignored and the current proof/revocation URLs are fetched. Explicit snapshots remain an offline/test input. A regression test proves a stale embedded proof and false revocation cannot override live documents. |
| Medium | Controller rotation preserves the contract record id, while enrollment and WordPress recomputed an id from the new controller | Fixed. Consumers now treat `recordIdForDomain(domainHash)` as the stable identity anchor for an existing domain and verify the current controller against the stored record. Deterministic id derivation is used only for first registration. |
| Medium | A single RPC can omit logs while claiming a complete response | Partially mitigated. Single-path output is now labeled `rpc_asserted_complete`; the hosted pilot uses a second independently operated RPC and publishes `independently_verified` only after canonical-history agreement. Buyer-side Myotis or multi-provider verification remains a production requirement. |
| Medium | Public deterministic candidate sampling is grindable and failed record fetches consume the bounded sample | Open for production v2. Testnet selection remains visible and neutral-fallback based. Production admission needs a fixed anti-spam policy and the buyer needs bounded backfill of failed candidates without unbounded merchant contact. |
| Medium | Validator churn permanently grows `_validatorList`, making validator scans increasingly expensive | Open for production v2. The immutable testnet contract remains trusted-operator pilot infrastructure. A production contract must use a bounded removable active-validator set and cap quorum work. |
| Medium | Merchant-configurable WordPress registry connections could perform SSRF or forward the bearer token to an unsafe target | Fixed. Registry connections require public HTTPS, reject user information, use WordPress safe HTTP transports, disable redirects, and bound POST/GET response size. |
| Medium | The source-publication workflow covered only the Merchant Registry | Fixed. The guarded workflow verifies both the Merchant Registry and Discovery Facets and treats `already_verified` as idempotent only after retrieving an exact runtime match. |
| Low | Witness alert delivery failures were only logged and had no independently evidenced receiver | Operationally mitigated for the pilot by the authenticated receiver and firing/resolved delivery drill described in `docs/REGISTRY_WITNESS_ALERT_EVIDENCE.md`. Durable secondary paging remains a production requirement. |

## Positive observations

The review found no issue in quote/approval intent binding, signer and
production-network guards, post-broadcast journaling, receipt canonicality,
facet current-record-hash binding, safe registry-record HTTP fetching,
WordPress nonce/capability boundaries, or secret-key handling. The principal
residual trust assumptions are governance-key security, validator honesty,
RPC-provider independence, HTTPS/CA integrity, alert-receiver availability,
and migration from the non-upgradeable pilot contract.

## Production release boundary

Mainnet remains blocked until the two production-v2 contract findings are
implemented and reviewed, the governance identities are named and transferred
to the approved timelocked multisig, external merchant/buyer pilots complete,
and an external human review confirms the deployed bytecode and operating
runbooks. This report improves the testnet pilot; it is not a mainnet approval.
