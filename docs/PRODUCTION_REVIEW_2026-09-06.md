# Production and marketplace review — 2026-09-06

ShopBridge is ready for further supervised testnet pilots. It is not ready for
an open marketplace handling public customers' money. The remaining launch gaps include
per-order liability, v2 deployment and complete enrollment, independent
operators, and live provider/restore evidence. The 1.23.0 follow-up implements
native stock reservations and checkout recovery; see the [release notes](RELEASE_1.23.0.md).

This review covers checkout `235a9c7`, the Solidity registry, Direct Skill,
buyer service, WooCommerce refund/stock paths, verifier, Helm charts, tests,
and recorded pilot evidence. It is an internal source review with local tests
and offline reproductions, not an external audit or a new inspection of the
running Talos cluster. A subsequent implementation pass repairs the refund,
comparison and selection defects and adds a tested v2 admission/bond/governance
contract. The numbered findings preserve their original baseline evidence;
line numbers in that evidence refer to the reviewed checkout, not the revised
files. See the status below and [implementation and rollout notes](PRODUCTION_HARDENING.md).

## Astra migration

The selected runtime is **Codex with the ShopBridge Direct Skill**.

- `.codex/config.toml` sets `gpt-6-astra` and explicit `medium` reasoning.
- `.agents/skills/shopbridge-direct` links the existing skill into Codex's
  repository discovery location.
- The current Codex adapter example and buyer setup instructions describe the
  configuration, session overrides, and remaining model evaluation.

There was no application model default or OpenAI API client to replace.
ShopBridge services and payment rules remain deterministic. Existing Codex
tasks can retain their selected model; use a fresh session or select Astra in
the task's model picker. Project defaults require a trusted repository.
The portable skill ZIP does not select a model in other workspaces.

The exact model and supported reasoning settings are documented in the
[Astra model page](https://developers.openai.com/api/docs/models/gpt-6-astra).
The [migration guide](https://developers.openai.com/api/docs/guides/latest-model#gpt-6-astra-update-api-and-model-parameters)
requires Responses for a custom Astra API tool loop. This repository uses
Codex's tool loop, so no API migration is needed here. See
[Codex configuration](https://learn.chatgpt.com/docs/config-file/config-basic)
and [skill discovery](https://learn.chatgpt.com/docs/build-skills#where-to-save-skills).

## What already works

The code has useful foundations: opt-in merchant discovery, immutable record
hashes, controller/domain/payment binding, live proof and revocation checks,
finalized chain reconstruction, category commitments, private comparison
quotes, selected-merchant Final Quotes, explicit quote-bound approval, payment
replay protection, and structured aftercare. Registry membership, ranking,
buyer approval, and settlement are already separate responsibilities.

Recorded Talos evidence includes a testnet payment/refund, replay rejection,
SQLite backup, and pod restart. The recorded multi-shop test compares three
maintainer-operated shops. These are meaningful integration results; they do
not establish independent merchant honesty, open-market fairness, or mainnet
payment readiness. See [technical pilot status](TECHNICAL_PILOT_STATUS.md).

## Remediation status

| Finding | Current source status | What remains |
| --- | --- | --- |
| R1: premature refund completion | Status-aware durable operations; Stripe polling; PHP and buyer completion checks | Provider transition and real WooCommerce rollout drills; reconciliation scheduling |
| R2: cumulative refund race | Atomic SQLite payment capacity; order-wide MySQL lock; pending reservations and local transaction | Actual InnoDB/plugin-hook concurrency drill; manual-transfer reconciliation policy |
| R3: interrupted Tempo refunds | Signed bytes/hash persisted before broadcast; same-operation receipt recovery and rebroadcast | Live fault injection, operational reconciliation, restore drill; ambiguous legacy operations stay blocked |
| R4: incomparable prices | Currency/unit separation, delivered unit cost, no partial-basket winner | Exact product equivalence and buyer-approved substitution coverage |
| R5: fake shops and accountability | New v2 quorum admission, real bond, entity binding, slashing/appeals/renewal, typed unsigned operator workflow; Direct admission with agreement from two RPCs | Independent verifiers/providers, merchant UI and complete buyer integration, order liability/exposure mechanism |
| R6: biased/exhausted sampling | Snapshot-bound random nonce, common-owner grouping before sampling, bounded backfill and HTTP budgets | Independent ownership verification; large-registry performance and adversarial deployment drills |
| R7: unilateral validator removal | V2 quorum/delay for suspension, removable active set capped at 16, delayed administration | Independent audit, named Safe/governance, migration to a new deployment |
| R8: early tournament cutoff | Diverse bounded collection before ranking; display limit applied afterward; nonce-based ties | Broader buyer-service production admission and persistence work |

These are source changes, not a production release or a claim that scams are
impossible. V1 on Talos/testnet retains its original rules. V2 is not deployed.
The registration bond does not cover unlimited order obligations. The choice
between direct payouts with provider-backed reserves and delivery/dispute
escrow remains a separate financial design decision.

## Findings, ordered for remediation

### R1 — P1: refunds can be reported as executed before success

`gateway/scripts/stripe-mpp-verifier.mjs:2257` returns
`real_refund_verified: true` for any returned Stripe refund status. The
WooCommerce verifier client, at
`woocommerce-shopbridge/agentcart-shopbridge/includes/trait-agentcart-shopbridge-verifier-client.php:234`,
accepts that boolean and records `rail_refund_verified` without requiring a
successful provider status. Buyer aftercare derives money-returned claims from
that flag.

**Reproduction:** ran the existing `verifyRefund` function in an isolated Node
VM with the Stripe SDK and replay store stubbed. Both `pending` and `failed`
returned HTTP 200, `ok: true`, and `real_refund_verified: true`. No network or
money movement was involved. Stripe explicitly distinguishes these states in
its [Refund object](https://docs.stripe.com/api/refunds/object).

**Required change:** persist requested, pending, succeeded, failed, and canceled
states; reconcile through authenticated provider events or polling; mark
execution verified only on confirmed success. Preserve provider status in all
adapters and buyer messages. Provider success must not be presented as proof
that a bank has already posted the credit.

### R2 — P1: separate refund requests can exceed one order's balance

`woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php:6342`
locks by refund idempotency key. Two requests with different keys can both read
the same remaining order balance at line 6356 and call the external verifier
at line 6370 before either writes the WooCommerce refund. The Tempo verifier
sends a transfer per distinct request; it does not atomically reserve a
cumulative refundable balance for the original payment.

**Impact:** two concurrent 60-unit refunds against a 100-unit payment can send
120 units on Tempo if the merchant wallet has enough funds. A later WooCommerce
rejection cannot undo an already sent transfer. Stripe's own charge refund
limit does not protect the Tempo path. This is a source-level concurrency
finding, not a live double-refund test.

**Required change:** enforce an atomic remaining-balance reservation keyed to
the original payment/order, across all request IDs; use per-order locking and
fresh state; account for pending refunds and manual/provider-side refunds.
Test simultaneous distinct requests and crashes between reservation, transfer,
and WooCommerce persistence against real database behavior.

### R3 — P1: Tempo refund retries cannot reconcile an interrupted transfer

`gateway/scripts/stripe-mpp-verifier.mjs:2064` reserves a refund request before
submitting its transfer. At line 2077, every replay of that request returns 409.
The transaction hash is held in memory after line 2098 and is only entered into
the refund replay store after receipt success.

**Impact:** a crash after reservation but before broadcast leaves an operation
that cannot resume automatically; a crash after broadcast can leave money sent
without a durable request-to-transaction record. Switching to a new request ID
can duplicate the transfer. Current behavior requires operator reconciliation.

**Required change:** a durable refund operation ledger with reserved funds,
persisted transaction intent/nonce, broadcast identity, receipt state, and
restart reconciliation. Retries must return or advance the same operation.
Use a prepare/persist/broadcast design that also handles a crash before the RPC
acknowledges submission. Drill each boundary, including loss of the HTTP reply
after success and failure to persist the WooCommerce refund.

### R4 — P1: cross-shop prices can be incomparable

`gateway/shopbridge-direct-skill/scripts/shopbridge-command.py:4203` and
`:4493` sort by raw cents, without a shared-currency check. Unit ranking also
sorts `cents_per_basis` without requiring the same physical basis; product
price per 100 g and price per item can be compared. The service tournament has
the same raw-cents ranking at `gateway/agentcart.py:5499`.

**Reproduction:** reused the Direct Skill's two-merchant discovery fixture,
changing the Beta quote and its tax metadata to GBP. The complete discovery
function ranked `13.80 GBP` ahead of `15.80 EUR` and returned one winner without
an exchange-rate input. This establishes invalid comparison, not a claim about
the current GBP/EUR rate.

**Required change:** initially restrict each comparison to a buyer-selected
currency and equivalent product/package units. Return other offers separately.
If FX is added, record rate source, timestamp, fees, rounding, and conversion
risk while preserving the actual settlement currency. Match exact products or
buyer-approved substitutes before ranking; shipping, tax, required fees,
quantity, delivery, and returns must remain visible.

### R5 — P1: registration and domain proof do not establish an honest shop

`contracts/AgentCartMerchantRegistry.sol:79` lets any wallet register nonzero
hashes and a URI and sets `Status.Active`. It neither proves domain control
on-chain nor requires a bond or admission decision. Direct Skill verification
in `shopbridge_registry_trust.py:564` checks identity/integrity; a scammer who
controls their own HTTPS domain, manifest, and payment address can satisfy
those checks. No independent fulfillment or legal-entity assertion is required
by that trust policy.

An arbitrary registration cannot automatically pass buyer verification for
someone else's domain, but it can occupy that domain's mapping and require
governance-assisted recovery. `flag()` at registry line 362 only emits an event;
there is no collateral, adjudication, compensation, or slashing implementation.
Its cooldown is per wallet, so it is not an entity-level spam limit.

**Required change:** distinguish registration, verified control, admission,
probation, and transaction reputation. Gate purchase eligibility on an
explicit admission policy. Bind controller authorization to fresh domain proof
before granting an eligible listing, preserve identity history through key
rotation and re-enrollment, and add an enforceable dispute/liability system.
Do not label HTTPS control as proof of stock, authenticity, or delivery.

### R6 — P1: predictable sampling and missing backfill enable exclusion

`shopbridge-command.py:1552` derives the default sample seed from predictable
request fields. `shopbridge_onchain_rpc.py:1366` orders identities by its hash
and truncates before resolving records. Failed records consume slots without
backfill at line 1430. The second sampler at `shopbridge-command.py:3971`
also favors declared category hints and uses merchant-controlled identity
material. These weaknesses were already identified in the August review.

**Impact:** many identities, category spam, or deliberately unavailable records
can reduce honest merchants' opportunity to quote. A blockchain records these
identities; it does not establish that their owners are independent. See
[Douceur's Sybil analysis](https://www.microsoft.com/en-us/research/publication/the-sybil-attack/).

**Required change:** admission and ownership grouping; a buyer-generated
unpredictable selection nonce after fixing the eligible snapshot; bounded
backfill across record, proof, catalog, and quote failures; budgets for total
requests, time, and bytes. Persist enough selection evidence for a buyer to
replay the decision privately. Randomness alone does not solve many identities.

### R7 — P1 for open admission: one validator can remove competitors

`contracts/AgentCartMerchantRegistry.sol:335` and `:351` allow any validator to
suspend or restore a listing immediately, independently of the attestation
threshold. A compromised or conflicted validator can exclude a shop. The
ever-growing validator list at `:569` and quadratic expiry sorting at `:597`
also leave unbounded work as validators churn.

**Required change:** implement and review the v2 bounded validator set and the
named governance in [ADR 0012](adr/0012-production-registry-network-and-governance.md).
Define distinct emergency quarantine and final sanction powers, automatic
expiry/review of emergency action, conflicts of interest, appeals, and public
reason codes. Increasing the attestation threshold alone does not constrain
the current suspension functions. Keep the immutable Moderato deployment as
testnet evidence; production requires a new contract and migration drill.

### R8 — P2: the service tournament can stop before seeing a cheaper shop

`gateway/agentcart.py:5497` stops collecting as soon as `max_candidates` quotes
exist, then sorts them. Catalog traversal order can decide which merchants
compete, and one merchant's products can fill the available slots. This differs
from the Direct Skill's merchant sampling.

**Required change:** select a bounded, diverse set of eligible merchants before
requesting quotes, then rank all valid responses received within the declared
deadline. Separate merchant-contact limits from displayed-result limits. Test
catalog permutations and a cheapest merchant appearing late. Use an explicit
tie rule; a merchant's alphabetically early display name should not confer an
advantage.

## Proposed marketplace rules

These rules include product recommendations beyond the implemented primitives.
The remediation table and rollout notes define the current implementation scope.

### Merchant admission and accountability

Use staged access: verified domain/controller/payment binding, independent
merchant verification, low-exposure probation, then higher limits as fulfilled
orders establish evidence. Verify the business or accountable operator through
appropriate providers and check control of the payout destination. Verification
and sponsorship should have public criteria and an appeal path, so incumbent
shops cannot veto new entrants.

Group shops by attested common ownership for exposure and sampling limits.
Domains, wallets, and ordinary payment transactions alone do not prove that two
businesses or buyers are independent. Support legitimate multiple brands and
ownership changes explicitly; do not publish private identity documents.
Reputation should weight verified outcomes, dispute history, evidence quality,
and recency, while resisting related-party/wash purchases. A raw order count or
star average would create another manipulable ranking signal.

Separate an affordable anti-spam registration bond from transaction liability.
A small fixed bond cannot protect against a large unpaid delivery obligation.
Enforce maximum unsettled exposure through escrow, provider reserves,
underwriting, or an equivalent collateral-backed mechanism. A declaration of
an exposure limit in a merchant manifest cannot enforce it across independent
buyer agents. Withdrawal and identity exit must remain constrained by open
obligations and dispute windows. Sponsorship and low initial limits can keep
entry affordable; additional collateral must not buy better ranking.

### Slashing with evidence and due process

The deployed v1 registry still has nothing to slash. The new, undeployed v2
contract holds a registration bond and implements quorum-approved sanctions,
an appeal window, delayed exit, and a compensation transfer. Production still
needs named adjudicators, agreed offenses, independent evidence review, and
coordination with per-order refunds, chargebacks and liability limits.

| Situation | Proposed response |
| --- | --- |
| Invalid control proof, revoked identity, or repeated unreachability | Exclude or quarantine; allow correction and bounded rechecking. An outage alone is not proof of fraud. |
| Cryptographically provable violation of a precisely defined signed commitment | Bounded sanction after evidence verification and the defined challenge/appeal process. Define the commitment and authorized amendments first. |
| Counterfeit goods, non-delivery, or contested quality | Human/provider dispute resolution using private order and delivery evidence. A smart contract cannot observe physical delivery quality by itself. |
| Cheap prices, losing bids, buyer rejection, or good-faith stock changes before acceptance | No fraud slashing. Apply clear quote/availability rules and reliability consequences where appropriate. |
| Malicious challenges or validator misconduct | Separate accountability rules and conflict-free review; do not pay challengers automatically for accusations. |

Compensate proven buyer loss before paying any bounded challenger reward, and
prevent duplicate recovery across refunds, chargebacks, and collateral. Keep
personal data and private bids off-chain; public commitments need unpredictable
salts where low-entropy values could otherwise be guessed. Astra may organize
evidence and explain decisions, but should not be the sole slashing authority.

### Price competition

Shops can already undercut each other by returning lower valid WooCommerce
quotes. There is no protocol for seeing a rival's offer, bidding again,
committing/revealing bids, or enforcing an auction deadline. The current
mechanism is a private request for quotes followed by local sorting.

Start with one private, sealed offer round: send the same product requirements
and coarse destination to selected eligible shops, give a common response
window, and disclose no rival bids or buyer maximum budget. Rank complete,
comparable responses using the buyer's policy. The winner supplies a fresh
Final Quote for the full address; any material change returns to the buyer for
approval. A bounded improvement round can be added later, with versioned rules
and without distributing competitors' confidential offers.

Retain the request specification, deadline, snapshot, contacted identities,
responses, timeouts, ranking-policy version, and tie rule in the buyer's audit
packet. A single agent withholding responses cannot be made honest merely by
putting the registry on-chain. Stronger independently auditable auctions would
need authenticated submission receipts or a separate commitment mechanism,
with its extra privacy, liveness, and cost tradeoffs.

### Protecting competition and small shops

Low prices benefit buyers; sustained exclusion followed by higher prices is
the concern. The FTC's
[pricing explanation](https://www.ftc.gov/advice-guidance/competition-guidance/guide-antitrust-laws/single-firm-conduct/predatory-or-below-cost-pricing)
distinguishes these economic situations. That US guidance is not a substitute
for advice on the marketplace's actual jurisdictions.

Use equal admission rules, no paid placement or stake-weighted ranking,
ownership-aware shortlist limits, modest exploration of eligible newcomers,
portable reputation, and buyer choice of agents and registries. Keep discovery
opportunity distinct from the purchase decision: a newcomer can get a chance
to quote without being awarded an order over the buyer's preferred offer.

Let buyers explicitly choose local/independent-shop preferences, delivery
quality, or a disclosed willingness to pay more. Show the cheapest eligible
comparable offer alongside those alternatives. Avoid hidden price floors or
automatic punishment for discounts. Do not promise that a cheapest-price
objective can also guarantee every small merchant's survival; scale advantages
and different costs remain. Measure candidate exposure, ownership
concentration, conversion, quote drift, non-delivery, and successful dispute
resolution, with privacy-preserving reporting.

## Remaining production gates and implementation order

| Stage | Deliverable and acceptance evidence |
| --- | --- |
| 1. Money correctness | Fix R1–R3; demonstrate concurrent refunds, pending/failed provider states, interrupted broadcasts, callback replays, and success followed by local persistence failure. Add a paid-but-no-order recovery path. |
| 2. Quote correctness | Fix R4 and R8; establish product equivalence, all-in costs, buyer constraints, deterministic versioned ranking, and neutral ties. |
| 3. Controlled merchant pilot | Independent merchant and buyer onboarding, identity checks, limits, support, returns/disputes, and fresh Astra buyer-session evidence. |
| 4. Public marketplace controls | Fix R5–R7; implement admission, ownership grouping, unpredictable bounded sampling/backfill, sustainable liability coverage, and governance/appeals. Simulate identity flooding, false categories, colluding validators, wash reputation, and malicious complaints. |
| 5. Mainnet operations | External review of v2 contracts and payment paths, exact source/runtime verification, named multisig/timelock operators, independent chain-data paths, secondary paging, outage drills, restore drills, key rotation, and successor migration. |

The original soft-hold design at `agentcart-shopbridge.php:9838` used a
read/modify/write WordPress option. The 1.23.0 native adapter now uses actual
WooCommerce reservations shared with ordinary checkout and a durable checkout
draft/payment checkpoint/compensation workflow. Both datastores and concurrent
reservation are exercised against InnoDB. External stock adapters, carrier
callbacks, cancellation/fulfillment races, plugin side effects and provider
restoration still need installation-specific evidence.

The optional AgentCart service persists JSON under a process-local lock
(`gateway/agentcart.py:2320`). Version 1.23.0 prevents a second server from
opening the same state path using a process-lifetime file lock. It still cannot
scale as multiple independent writers. The verifier chart uses one replica and
SQLite persistence. Preserve that constraint for a small pilot; a production
availability target needs a tested failover/restore design or a transactional
shared store. Merely increasing Kubernetes replicas is not that design.

The committed evidence report dated **2026-08-23** records failed pilot-readiness
and buyer-runtime gates, with 35 invalid evidence entries. Later technical
notes record additional maintainer progress, but do not supply a fresh passing
external release decision. Regenerate the evidence report after real sessions;
do not turn templates into approvals. Confirm support ownership, privacy/data
retention, consumer terms, payment-provider operations, and the actual
production rail for the chosen jurisdictions.

## Validation of the original review

**554 existing tests passed:** 368 gateway Python, 113 WooCommerce adapter/
contract tests, 13 household tests, 22 Solidity tests, and 38 Node registry tests.
Loopback-dependent tests were rerun with the required local socket access after
the sandbox blocked their mock servers.

Both Helm validation scripts passed. Buyer adapter and Direct Skill package
checks passed. TOML/JSON consistency and the relative skill symlink were
verified. No container images were built and no cluster state or payments were
changed. The full Docker/WordPress live verification pipeline and a fresh
Astra-driven buyer session were not run. The installed CLI did not support
`--strict-config` for `features list`; model configuration was checked directly,
not misreported as a successful CLI strict-config check.

The two offline reproductions above demonstrate missing coverage despite the
passing suite. They are not assertions that provider-side or distributed
production behavior has been tested. The existing untracked pilot handoff and
merchant brief were left unchanged.

## Validation of the implementation pass

The current suites pass **608 tests**: 382 gateway Python, 115 WooCommerce
contract/runtime, 13 household, 35 Solidity, 49 Node registry, and 14 Node
refund-ledger tests. The new tests cover real SQLite concurrency and restarts,
provider-state handling at the PHP boundary, permanent Tempo nonce serialization,
currency/unit comparison, backfill, owner grouping, admission, governance,
slashing, appeal, renewal, exit, unsigned operator plans, and rejected RPC
witness disagreements before document loading. The shared registry
ABI now matches the contract's uint64 attestation generation. V2 runtime size is 22,152 bytes with the pinned
compiler/optimizer. These are local tests; provider/RPC effects are fixtures.

Both Helm chart checks pass after synchronizing the bundled plugin copies.
PHP syntax, endpoint contracts, buyer adapter and portable skill package checks
pass, including PHPCS/WPCS. The separate external WordPress Plugin Check is not
configured and has not run. No container build or cluster write was performed. Live WordPress/InnoDB,
real-provider fault injection, independent contract review and a fresh Astra
buyer evaluation remain release gates. The pre-existing untracked pilot
handoff and merchant brief were preserved.
