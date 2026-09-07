# Production hardening: implementation and rollout

The September 6 changes repair the refund and comparison defects and add a
new registry contract with admission and financial sanctions. They do not
authorize public mainnet use. The v1 deployment is unchanged. V2 is compiled
and tested locally, with no production address, external audit, or custody
provider selected.

The 1.23.0 follow-up adds native WooCommerce stock holds, durable checkout
recovery and manager compensation, a buyer-server writer lock, and synchronized
release packages. See [1.23.0 release notes](RELEASE_1.23.0.md). The checkout
drill now runs against a real local InnoDB database with fixture payments.

## Refund operations

Real Stripe and Tempo refunds now require
`AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite` and a persistent
`AGENTCART_VERIFIER_REPLAY_STORE_PATH`. Payment verification can still use the
older JSON store for demos. Refund execution fails closed on that driver.

`refund_operations` and `refund_events` live in the same database as verified
payment replay claims. A request is bound to its original reference, amount,
currency, quote, payment, and destination. The payment's stored verification
supplies the refundable ceiling; caller-supplied payment totals cannot raise it.
One SQLite immediate transaction reserves capacity across all refund request
IDs for that payment. Reserved, prepared, pending, and uncertain operations
retain capacity. Only a confirmed failure/cancellation releases it.

Stripe creates with a stable provider idempotency key, then polls the saved
refund ID on subsequent requests. Only `succeeded` sets
`real_refund_verified=true`. Pending, required-action, unknown, failed, and
canceled results do not. Stripe's documented
[refund statuses](https://docs.stripe.com/api/refunds/object) distinguish these
outcomes. Provider success is not proof of bank posting. If submission is
unknown and 23 hours have elapsed, automatic creation stops: Stripe may prune
[idempotency keys after 24 hours](https://docs.stripe.com/api/idempotent_requests).

Tempo prepares and signs a transaction locally, persists its exact signed
bytes and hash, and then broadcasts. Each request uses a permanent 2D nonce
lane at nonce zero. Concurrent workers can prepare, but only the persisted
winner is broadcast. After a lost acknowledgement or restart, a retry checks
the saved hash and can rebroadcast only the same bytes. Completion requires
the configured confirmation depth and the exact token Transfer event, including
sender, recipient, and amount. A successful receipt without that transfer
requires operator review and retains the reservation. The signing approach
follows viem's
[prepare/sign/broadcast interface](https://viem.sh/docs/actions/wallet/prepareTransactionRequest.html)
and is tested against the pinned viem 2.52.2 serializer.

WooCommerce locks by order using a MySQL connection lock, rereads order state,
and saves pending requests before contacting the verifier. Pending amounts
reduce availability for other requests. Successful local refund creation and
its replay metadata use one database transaction; a lost lock or failed commit
returns an error. Use InnoDB and a WooCommerce datastore that participates in
the same connection/transaction. Additional plugin hooks can have external
side effects; exercise the actual installed plugin set in the rollout drill.
The core refund hook sequence is documented in
[WooCommerce's source](https://raw.githubusercontent.com/woocommerce/woocommerce/trunk/plugins/woocommerce/includes/wc-order-functions.php).

### Retry and recovery rules

1. Back up the entire SQLite database using its online backup mechanism. Include
   refund operations and events, not just an exported replay-claim JSON file.
2. Retry an unresolved refund with the **same original reference and parameters**.
   The existing authenticated refund endpoint advances/polls that operation.
   Pending verifier responses use HTTP 202; WooCommerce returns a reconciliation
   error without creating a completed refund. Order aftercare exposes reserved
   pending amounts separately from completed refunds.
3. Monitor `health.refund_ledger.counts` and
   `oldest_unresolved_age_seconds`. These expose aggregate state, not signed
   transactions. Add paging and a reconciliation schedule to the deployment's
   operational setup; this change does not create a background worker or webhook.
4. For a Stripe operation outside its safe retry window, a Tempo
   `review_required` operation, or an ambiguous legacy replay-only refund,
   reconcile provider/chain evidence before changing capacity. No automatic
   migration guesses whether old money movements succeeded.
5. Keep refunds disabled after a point-in-time database restore until provider
   and chain activity since that backup is reconciled. Never discard a live
   operation database to make a retry work.

Use one durable verifier authority per payment/refund wallet. Two independent
database copies do not share a capacity ceiling. Stripe also enforces its charge
limit. Manual Tempo transfers cannot be inferred to belong to a particular
order; require all refund signing through this authority or reconcile manual
transfers before resuming. Retain the original network, token, destination, and
signing configuration until its operations are resolved.

## Registry v2

`contracts/AgentCartMerchantRegistryV2.sol` is a new deployment target. It keeps
the v1 lifecycle read/event interface for compatibility and adds
`eligibility(recordId)`. Record IDs use a v2 domain separator; obtain them with
the contract's `computeRecordId`. Never relabel the deployed Moderato contract.

- At least two active validators must agree on an admission binding the domain,
  controller, exact record hash, accountable entity, expiry, and evidence hash.
  Registration requires that approval and an actual ERC-20 bond transfer.
  Failed payment of the bond leaves the domain unclaimed. Domain and payout
  checks, business verification, and entity independence are validator duties;
  the contract cannot perform them from hashes.
- Updates and controller rotation need fresh admission and preserve the entity.
  `renewAdmission` binds fresh votes without changing the record or bond.
  Admission expires after at most 90 days. Removing/re-enabling a validator
  cannot revive its old votes. The active set is capped at 16 and removes old
  entries, so historical validator churn does not grow quorum work.
- Suspension and restoration require quorum and a 48-hour delay. Validator,
  threshold, owner-transfer initiation, and pause changes retain owner authority
  but require the 48-hour governance schedule. Production ownership must be the
  named Safe/timelock arrangement in ADR 0012; the constructor cannot establish
  that different addresses belong to different people.
- A verified successor needs admission, quorum approval, a delay, and its own
  bond. Revocation and supersession retain the previous bond/history. A record
  ID cannot be overwritten by registering it again.
- A quorum can schedule a bounded slash with evidence and a compensation
  beneficiary. The `reason` hash must identify a unique adjudicated case, not
  merely a reusable category such as “non-delivery.” The controller can appeal
  during the initial 48 hours. An appeal requires fresh quorum review and a
  seven-day waiting period; silence lets the proposal expire. A single validator
  cannot freeze withdrawals or execute a slash.
- Execution transfers actual collateral to the beneficiary, revokes the record,
  and blocks the attested entity from re-entering. Reinstatement requires another
  delayed quorum decision. A public flag is an allegation, never an automatic
  fine. Cheap prices and losing bids are not fraud offenses.
- Bonds can be withdrawn only after revocation and a 30-day exit window, with
  an additional hold for a live quorum-approved sanction. These are explicit
  protocol constants needing economic/legal review before deployment. No token
  or minimum bond amount is invented for production; the deployment constructor
  requires both.

The registration bond is **not order escrow, insurance, or an unsettled-exposure
limit**. It cannot cover unlimited obligations or prevent duplicate recovery
through chargebacks and collateral. The next financial implementation depends
on choosing direct payouts with provider-backed reserves/underwriting versus
escrow with delivery and dispute release rules. Existing direct payments have
not silently been redirected into custody.

### Buyer integration and migration

For a reviewed v2 deployment, configure its RPC, chain, address, deployment block
and block hash, plus `SHOPBRIDGE_ONCHAIN_REGISTRY_VERSION=2`,
`SHOPBRIDGE_ONCHAIN_RUNTIME_CODE_HASH`, and `SHOPBRIDGE_REQUIRE_ADMISSION=1`.
The runtime hash must come from independently reviewed deployment evidence.
Direct RPC discovery checks it and reads eligibility at the same finalized
block before fetching candidate documents. A mainnet marketplace request cannot
fall back to v1 identity-only eligibility.

Also set `SHOPBRIDGE_ONCHAIN_ADMISSION_WITNESS_RPC_URL` to an independently
operated second RPC. V2 rejects a missing witness or the same hostname, verifies
its chain, finalized boundary, creation evidence and runtime code, and compares
all lifecycle logs and every admission result before fetching shop documents.
Disagreement fails closed. This is two-provider agreement, not a cryptographic
state proof; different hostnames cannot establish operational independence or
protect against collusion. Review the actual providers in release evidence.

The current Myotis adapter reads storage at a newer verified head. V2 rejects
that mode until it can prove admission at the required finalized boundary.
Use a finalized-state-capable RPC plus the required independent witness for the
v2 integration drill. Hosted admission projections and the optional AgentCart
service's production admission path still need integration; the service fixes
in this change concern quote collection and comparison, not v2 authorization.

The new [v2 operator workflow](REGISTRY_V2_OPERATIONS.md) prepares pinned,
simulated unsigned wallet requests for identity, admission, exact bond allowance,
registration, renewal, governance, supersession, slashing, appeals and exit. It
also reads finalized eligibility and case state. It never signs or broadcasts.
Its deployment template is deliberately invalid until reviewed evidence exists.
The merchant UI now accepts operator-pinned v2 configuration, verifies bonded
admission against two finalized RPC views, and invalidates expired admission or
changed configuration. Identity preparation exports its WordPress/Helm pins.
Connect independent case operators and complete the migration drill before
deploying v2. Supply
the public admission criteria, named independent validators, conflict rules,
case evidence/appeal process, bond sponsorship policy, and independent audit.
Token transfer semantics, governance operations, expiry, recovery, and actual
registration gas must be tested on the selected network. V1 remains a testnet
pilot path with identity-only assurance.

## Fair comparison

The buyer now separates currencies with no implicit FX conversion. With mixed
currencies and no buyer selection, there is no winner. Set
`comparison_currency` to rank one currency and retain other offers separately.
Unit comparison also requires a common `comparison_unit` (`g`, `ml`, or `unit`),
uses delivered totals including quoted tax/shipping, and compares unrounded
ratios. Partial baskets remain alternatives requiring another buyer choice.
Product equivalence still depends on exact requirements and permitted
substitutions; a query such as “tea” does not establish interchangeable goods.

Direct discovery draws a nonce after fixing the eligible snapshot. Only fresh
v2 admission data can establish common ownership. Sampling gives an entity one
opportunity; registering many brands does not improve its random priority.
Failed documents, proofs, catalogs, and quotes use bounded reserve candidates.
The shared HTTP budget covers 90 seconds, 256 requests and 64 MiB of response
bodies. Exhaustion can leave an incomplete comparison and never proves a global
best price. Save the nonce, snapshot, selection and failures in the buyer's
private evidence, not a public bid feed.

The optional service schedules at most two products per selected merchant before
quoting, ranks all eligible collected offers, and applies the display limit
afterward. Display names do not decide ties. A merchant's catalog order or
number of products cannot fill every quote slot.

Shops can compete with lower binding offers. The protocol does not disclose
competitors' bids, automatically match rivals, guarantee a minimum shop income,
or establish that a low price is predatory. Admission/bond size must not buy
ranking priority. Long-term competition needs transparent access and buyer
choice; preventing large firms from excluding competitors is not solved by a
minimum-price rule in the comparator.

## Remaining launch gates

Source-level fixes do not replace these requirements:

- A chosen and implemented per-order liability/exposure mechanism, including
  fulfillment disputes, refunds, chargebacks and compensation accounting.
- End-to-end v2 enrollment and buyer authorization on all production paths,
  audited contracts, real multisig operators, pinned deployment evidence, and
  two independent finalized-data paths.
- A live InnoDB/WooCommerce failure drill: simultaneous partial refunds,
  provider pending-to-terminal transitions, process death at every persistence
  boundary, manual refunds, and restoration from backup. Local legacy/HPOS
  drills now cover native stock contention, lost verifier replies, failed
  promotion, rollback, and pending-to-successful compensation. External plugin
  effects and real provider/restore evidence remain outstanding.
- Enable the implemented hard holds and checkout recovery on the actual
  merchant installation, schedule WordPress cron, and monitor its manager queue.
  External inventory systems must supply their own compatible reservation
  adapter. Payments first presented after quote expiry require provider/support
  reconciliation, even if the buyer already sent funds independently.
- A transactional persistence/failover design before scaling the optional
  JSON-backed buyer service to multiple writers, and tested verifier backup,
  restore, reconciliation, metrics, and paging.
- Independent merchant/buyer drills, fresh Astra buyer evals, provider/legal
  operating arrangements, and a regenerated release-evidence decision.

The local gate covers 612 tests (386 gateway Python, 115 WooCommerce, 13
household, 35 Solidity, 49 registry Node, and 14 refund Node). PHPCS/WPCS,
endpoint and adapter contracts, packaged skills, and Helm rendering are also
checked. Official WordPress Plugin Check passed in the isolated shop. Additional
database drills cover WooCommerce 10.8.1 and 11.0.0, legacy tables and HPOS,
including separate workers racing for the last unit. Payment/refund responses
are fixtures; these results do not establish real provider or restore behavior.

No cluster rollout, container image build, live payment/refund, or mainnet
contract deployment is part of this change.
