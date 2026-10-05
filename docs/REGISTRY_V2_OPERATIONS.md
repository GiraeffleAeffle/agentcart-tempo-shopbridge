# Registry v2 operator workflow

The v2 tool prepares **unsigned** wallet requests. It does not hold a key,
broadcast, deploy, decide whether a business is honest, or declare a dispute
proven. Each operator reviews the typed operation and submits it through their
own wallet or Safe. A successful vote simulation does not mean quorum exists.

Start with `gateway/config/registry-v2-deployment.template.json`. Its empty
addresses, zero chain ID, and disabled mutation policy intentionally fail
validation. Populate a separate deployment file from independently reviewed
chain ID, contract address, creation block/hash, and runtime code hash. Supply
a finalized-state-capable RPC. The descriptor uses the existing v1 *deployment
document schema* and explicitly selects `registry_version: 2`; this does not
relabel a v1 contract. Use `pilot_enabled` for a testnet deployment; a mainnet
descriptor requires the release decision and `mutation_policy: approved`.
V2 direct buyers additionally require both independent providers to support
JSON-RPC batches and [EIP-1898](https://eips.ethereum.org/EIPS/eip-1898)
canonical block-hash selectors for storage/code
reads. Unsupported providers fail closed without a history or number-only fallback.
Buyer batches default to eight calls; `SHOPBRIDGE_ONCHAIN_RPC_BATCH_SIZE=1..8`
can lower the limit. HTTP 413/request-too-large and HTTP 429 split in halves
down to single requests; 429 first honors the bounded Retry-After cooldown.
Every split uses the same general HTTP request budget.

Run from `gateway`, after installing its pinned dependencies:

```sh
node scripts/registry-v2-operator.mjs --help
node scripts/registry-v2-operator.mjs prepare \
  --deployment-file /path/to/reviewed-v2-deployment.json \
  --request-file /path/to/operation.json \
  --output /path/to/new-wallet-plan.json
```

The output file must not already exist. Every request has an `operation`, an
`actor` address, and a `parameters` object. Unknown operations and fields are
rejected. Hashes are 0x-prefixed bytes32 values; integer parameters, including
token amounts, are **decimal strings** in base units. There is no arbitrary
calldata, recipient, or native-token value parameter.

The tool verifies chain ID, contract creation boundary, pinned bytecode, and
fresh finalized state. It simulates the exact operation from the named actor
at that boundary. Plans contain the decoded request, relevant evidence, exact
wallet request, a 30-minute review window, and an intent hash/acknowledgement.
The contract does not enforce the offchain review expiry. Prepare again before
signing an expired plan and after any prerequisite transaction. Compare the
wallet's chain, target, method, amount, and recipient with the plan. Track the
submitted transaction hash in the operator's case record and wait for finality.
This tool does not replace a wallet's transaction journal or receipt verifier.

## Admission and registration

1. The registry's named Safe schedules each validator with `scheduleValidator`
   (`validator`, `enabled`). After the contract's 48-hour delay, prepare
   `setValidator` with those same parameters. Bootstrap at least two independent
   validators. `scheduleThreshold` / `setAttestationThreshold` change the quorum
   using `threshold`; the contract rejects a threshold below two. Separate
   addresses alone do not establish independence.
2. The merchant prepares `identity` with its controller as `actor` and
   `parameters: {"domain":"shop.example"}`. Store the returned public
   `wordpress_settings` in WooCommerce. This is a read operation with no wallet
   request. An occupied domain controlled by another address returns a successor
   identity and `supersession_required`, not permission to overwrite that shop.
3. Publish WooCommerce's updated immutable registry bundle. Supply its exact
   `domain_hash`, `record_hash`, and content-addressed `record_uri` to validators.
   Validators independently complete the published domain, controller, payout,
   business, and common-ownership checks. Agree on an accountable `entity_id`,
   an `expires_at` timestamp no more than 90 days ahead, and the same
   `evidence_hash`. Keep sensitive verification documents in the case system;
   do not publish them onchain.
4. Each validator prepares `voteAdmission` with its own address as `actor` and
   these parameters: `domain_hash`, `controller`, `record_hash`, `entity_id`,
   `expires_at`, `evidence_hash`, `record_uri`. The tool verifies the document's
   hash, merchant-domain URI and embedded onchain identity. The contract checks
   validator membership; quorum must agree on every binding field. These checks
   cannot substitute for the validator's actual business verification.
5. The merchant prepares `approveBond` with an empty parameters object. The
   tool reads the registry's actual collateral token and minimum, checks the
   merchant's balance, and proposes only that exact allowance. A smaller
   existing nonzero allowance produces a reset to zero first; finalize it, then
   prepare again. No unlimited allowance is generated. If allowance is already
   sufficient, the tool stops without another approval.
6. After the votes and allowance finalize, the merchant prepares `register`
   using `domain_hash`, `record_hash`, and `record_uri`. Preparation requires
   current quorum approval and a valid immutable document. Contract simulation
   also checks domain availability and the actual bond transfer. Finalize the
   registration, then prepare `status` with `record_id`. Check `admission.eligible`,
   entity, expiry and the deposited bond. A finalized Active v1-style record
   alone is insufficient.

Record changes use `update` (`record_id`, `record_hash`, `record_uri`) after
fresh votes for the new hash. A controller rotation uses `setController`
(`record_id`, `new_controller`, `record_hash`, `record_uri`), with the current
controller as actor and new approval bound to the next controller. The record
identity and accountable entity are preserved.

For renewal, validators vote for the same domain, controller and hash with a
new expiry/evidence commitment. The merchant then prepares `renewAdmission`
with `record_id`. This binds the new approval without modifying the document
or moving collateral. An expired admission remains ineligible until renewal
finalizes. Enrollment approval votes must still be fresh when bound.

## WooCommerce deployment configuration and health

The `identity` operation also returns `wordpress_deployment`, with the reviewed
creation block/hash, a SHA-256 pin calculated locally from the runtime bytecode
already checked against the deployment's Keccak pin, finality limits, and both
RPC endpoints. Set `rpc_url` and `witness_rpc_url` to public HTTPS endpoints on
distinct hosts before preparing identity. Use independently operated providers;
different hostnames alone do not establish independence.

The operator installs this object in `store.registryOnchain.v2Deployment` in
Helm values, or defines `AGENTCART_REGISTRY_V2_DEPLOYMENT` as that JSON string
(or PHP array) in `wp-config.php`. Save only `wordpress_settings` in the four
merchant identity fields. Keep RPC configuration out of public merchant bundles.
An absent v2 setting retains the Moderato v1 pilot; an explicitly invalid v2
setting fails verification and never falls back to v1. The export is unsigned
configuration for operator review, not evidence that its witness has agreed.

After registration, WooCommerce's **Check registry health** verifies both
providers' chain and deployment history, bytecode, domain mapping, exact record,
revocation and `eligibility(recordId)` at the same block hash with
`requireCanonical`. It selects the lower common finalized height when heads
differ, rejects stale or divergent responses, and requires current contract
eligibility, a nonzero accountable entity and bond, and unexpired admission.
This is two-provider agreement, not a light-client proof. Public HTTPS URL
validation and WordPress's unsafe-address checks apply to both RPC requests.

The merchant panel shows the accountable entity and admission expiry. Its
cached ready state expires with admission, even within the ordinary ten-minute
health window; changing any deployment configuration requires a fresh check.
The onboarding bundle selects v2 instructions for admission, bond, registration,
updates and renewal. Signing remains in the external wallet. Collateral is a
registration bond and must not be presented as insurance for every order.

## Cases, sanctions and exit

Use a unique `case_hash` for each adjudicated case, not a generic offense label.
The beneficiary and amount must reflect the adjudication and outstanding
compensation. Registration collateral has no automatic knowledge of refunds,
chargebacks, delivery, or obligations at other shops. Reconcile those before
voting; duplicate-recovery accounting remains a launch requirement.

- `proposeSlash`: each validator supplies `record_id`, `amount_base_units`,
  `beneficiary`, `case_hash`, and public `evidence_uri`. Quorum schedules the
  bounded sanction; one vote does not freeze a bond.
- `appealSlash`: the controller supplies `record_id` and `evidence_hash` before
  the initial delay ends. This starts a fresh review and seven-day wait.
- `reviewAppeal`: validators supply `record_id` after reviewing the appeal.
  Silence cannot execute a sanction. The contract enforces quorum and expiry.
- `executeSlash`: supply `record_id` after the applicable delay. The contract
  rechecks quorum and transfers the actual bounded collateral, revokes the
  record, and blocks the accountable entity. `status` exposes pending case and
  bond state; use finalized transaction receipts for the transfer evidence.
- `revoke`: the merchant supplies `record_id` and `reason_hash` to exit.
  `withdrawBond` takes `record_id` after the 30-day exit delay and any live
  sanction hold. It pays the controller; no alternate withdrawal address is
  accepted by the planner.
- `suspend` / `unsuspend` require quorum and delay; `suspend` also takes
  `reason_hash`. `restoreEntity` takes `entity_id` and `reason_hash` and requires
  another delayed quorum decision. Price competition is not sanction evidence.

The CLI also prepares `requestSupersession`, `approveSupersession`,
`cancelSupersession`, and `activateSupersession`; `--help` lists exact fields.
A successor supplies a verified immutable record, admission, quorum review,
delay and its own bond. Previous history and collateral are retained.
Scheduled pause/ownership changes have typed preparation operations as well;
the Safe must preserve the published governance and conflict rules.

## Enumerable discovery and facets V2

New V2 deployments expose `indexedRecordCount()`, `indexedRecordIdAt(uint256)`
and `recordURI(bytes32)`. The existing `record(bytes32)` tuple and lifecycle
events remain compatible. Membership uses constant-time add/swap-remove; indices
are snapshot-local and must not be treated as stable merchant identifiers.
The index is **eligible-or-pending-prune**, not an eligibility certificate:
admission expiry and entity/bond changes can invalidate an Active record.
`status` returns `indexed_record_count`, `record.record_uri` and
`record_specific_eligible` from `hasRecordEligibility(recordId)` (excluding
global pause and admission quorum). Unsigned prune plans use this predicate.

Deploy the separate `AgentCartMerchantDiscoveryFacetsV2` bound to this RegistryV2,
not the deployed V1 facets. Keeping category routing separate preserves the
immutable V1 contract and lifecycle interface and avoids putting optional
category maintenance on the registry's governance/payment lifecycle. The V2
facets retain `publish`, `clear`, `facetState` and `isCurrent`, and add
`categoryRecordCount(bytes32)`, `categoryRecordAt(bytes32,uint256)` (record ID
and declaration generation), and permissionless `prune(bytes32)`. Publish and
clear replace at most eight memberships. Buyers verify indexed generation,
current facet state, record-hash commitment, and `isCurrent` at the same
finalized block as Active status and admission. Stale entries are routing hints
only and can never establish eligibility.

Add `discovery_facets` to the reviewed deployment descriptor with `address`,
`deployment_block`, `deployment_block_hash`, and `runtime_code_hash` for the
new V2 facets. Prepare pruning with any actor:

```json
{"operation":"prune","actor":"0x...","parameters":{"record_id":"0x..."}}
```

The unsigned plan targets only that descriptor's facets address after verifying
its creation boundary, bytecode and registry binding, then simulates pruning
at the finalized snapshot. Facet pruning removes stale/inactive/ineligible memberships without
altering registry status or admission. It does not require validator authority.
Do not point a V2 buyer or prune descriptor at the old V1 facets. No migration,
deployment, signing, or broadcasting is performed by this tool.

### Keeping the index available

Someone must maintain routing freshness: a merchant, operator or permissionless
keeper calls `pruneIneligible(recordId)` on RegistryV2 and `prune(recordId)` on
FacetsV2. Registry pruning emits an event and removes only record-specific
ineligibility (expired admission, blocked entity, insufficient bond, non-Active
status or supersession). It rejects an otherwise-eligible record during a
global pause or unsatisfied validator/quorum condition, preventing mass-prune
griefing during governance transitions. It never revokes the record.
Facets use the same public `hasRecordEligibility(recordId)` predicate for current
sets, so pause-only and quorum-only failures cannot clear categories. Stale
sets may still be removed immediately. Cleared facets do not remove merchants
from neutral buyer fallback discovery.

`renewAdmission`, `update`, controller rotation and unsuspension synchronize
their touched record. After record-specific recovery such as restoring a blocked
entity, a merchant or keeper calls permissionless `refreshIndexedRecord(recordId)`
to re-add an eligible record; this is idempotent and rejects unknown/ineligible
records. Entity restoration remains bounded rather than looping over shops.
There is no bond-top-up operation in this contract. If facets were pruned,
the controller republishes categories after recovery.
Unsuspension re-indexes every record satisfying record-specific eligibility,
even during admission quorum shortfall; once quorum recovers no manual refresh
is needed for that record.

Both registry maintenance operations have unsigned plans:

```json
{"operation":"pruneIneligible","actor":"0x...","parameters":{"record_id":"0x..."}}
{"operation":"refreshIndexedRecord","actor":"0x...","parameters":{"record_id":"0x..."}}
```

The buyer excludes every ineligible draw and backfills only within its bounded
reserve/budget, never accepting stale entries or scanning further history.
Without maintenance, sufficiently polluted indices can return no merchants.

For a uniform no-category run targeting 12 merchants with 36 reserve draws,
if `S` of `N` indexed records are ineligible, the probability of drawing at
least one eligible record is `1 - C(S,36)/C(N,36)` (use `min(N,36)` draws).
For a large pool with stale fraction `s`, the conservative approximation is
`1-s^36`: 90% stale gives 97.75% success; at most 87.99% stale gives at least
99% success. These are sampling calculations, not live availability guarantees:
documents can still fail, and finding one does not mean filling all 12 slots.
With category routing, 12 neutral reserve slots are retained; if category
entries contribute nothing, `1-s^12` applies to the remaining neutral pool:
90% stale gives only 71.76%, and 99% requires at most 68.12% stale. Keepers
must prune both sets rather than relying on those probabilities.

### Witness boundary agreement

V2 direct buyers default to exact number/hash/timestamp agreement between both
providers' concurrently acquired `finalized` heads. Six acquisitions, spaced
by 200 ms after disagreement and bounded by the discovery deadline, fail closed
with `registry_v2_witness_finality_mismatch` if providers never converge.
Persistent honest-provider lag is an availability risk, not permission to rewind.
Only explicit `SHOPBRIDGE_ONCHAIN_WITNESS_FINALITY_POLICY=bounded_lag` permits
the lower boundary, confirmed by both providers, within
`SHOPBRIDGE_ONCHAIN_WITNESS_MAX_HEAD_SKEW_SECONDS` (default 12, bounds 1..60).
Doctor labels this `bounded_lag_noncanonical`: it weakens revocation freshness
by up to the configured skew. Header comparisons ignore non-consensus provider
metadata. The RegistryV2 invariant campaign is bounded inline to 64 runs ×
64 calls per run; deterministic lifecycle and gas-bound tests remain separate.


## Integration evidence still required

Exercise this flow with independent wallets on the selected test network,
then exercise the merchant health/UI integration and connect the case system. Test
token semantics, admission expiry, quorum changes, rejected transactions,
appeals, recovery and migration. Review the new contract independently before
any production deployment. The existing v1 operator and deployed Moderato
registry remain the pilot workflow. No production v2 address, independent
validator roster, or public business-verification service is supplied here.
