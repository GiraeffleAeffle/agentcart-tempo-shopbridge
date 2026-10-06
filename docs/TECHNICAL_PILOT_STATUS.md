# Technical Pilot Status

> Baseline snapshot: 2026-08-27; deployment state updated 2026-10-06. This is a
> testnet engineering status, not a production or mainnet-readiness claim.

## Outcome

The technical testnet baseline is implemented and exercised end to end. The
Talos verifier accepted a quote-bound pathUSD payment, executed the
verifier-backed refund, rejected a conflicting replay, and retained its SQLite
claims across a pod restart. The Tempo registry then completed a finalized
register, revoke, and recovery lifecycle that the packaged Direct Skill
enforced without buyer configuration.

Two independent full-history RPC paths reproduced the hosted finalized event
sequence. The recurring indexer now also has a packaged fail-closed witness
mode: it compares canonical histories through the common finalized boundary,
rejects divergence or excessive finality lag, and can send throttled firing and
resolved webhook events. The supervised merchant package is now implemented in
source: WordPress publishes public controller-bound identity and immutable
record snapshots, while a two-phase operator plan hands the exact transaction
to an external wallet and verifies exact state only at finality. The recurring
witness and authenticated receiver were active until the hosted deployment
was retired on 2026-10-06. Both contracts are publicly source-verified, and a
Daybreak Blue model-assisted review is recorded. What
remains is production-v2 hardening, named governance, external human review,
secondary alerting, and non-maintainer buyer and merchant evidence.
No production chain or real-money rail was used.

## Package Status

| Package | State | Evidence or remaining gate |
| --- | --- | --- |
| Shared registry trust contract | Implemented and covered by gateway, helper, fixture, and Direct Skill tests | Keep the portable-skill package contract test mandatory |
| Buyer discovery HTTP boundary | Implemented as a portable redirect-free, size-bounded, DNS-pinned transport | Private/local targets require explicit opt-in |
| Finalized onchain projection | Implemented and fail-closed | Covers registration, update, controller rotation, suspension, attestation, revoke, and supersession/recovery |
| Immutable full-record archive | Implemented in the public-registry chart and as merchant-hosted content-addressed WordPress snapshots | Old content hashes remain fetchable after revoke/recovery while the plugin remains installed. Production still needs a separately operated append-only copy because disablement makes the merchant route unavailable and uninstall removes the plugin archive |
| Reference RPC indexer | Implemented; was live with an independent Tenderly witness until 2026-10-06; hosted deployment retired | Reads no newer than `finalized`, records block identity/range/time, validates record hash/controller binding, and publishes only the common range after both RPC paths agree. Matched public snapshots declared `independently_verified`; a failure preserves the last good snapshot until buyer freshness enforcement expires it |
| Buyer auto-discovery | Implemented and live | Direct Skill queries Tempo JSON-RPC itself, replays finalized eligibility events, verifies committed record documents, and checks projected records against contract storage; buyer discovery never depended on the retired hosted feeds |
| Category-routed discovery | Implemented, finalized, and live-tested across three USD shops | The controller-bound Discovery Facets contract stores current record hash, category-set commitment, count, generation, and indexed category declarations. A live `tea` query matched all three on-chain declarations before catalog access; buyer discovery keeps a neutral fallback and still confirms products in each current merchant catalog. |
| Buyer quote and payment readiness | Implemented in source after the first workstation-agent run exposed the ambiguity | Discovery explicitly requires no wallet; payment readiness is reported separately without invoking payment tools; country/postcode quotes are comparison-only; approval, payment, and checkout require a refreshed financially consistent quote with a complete buyer-supplied delivery address. Publish the updated skill/plugin and repeat the external run |
| Buyer verified-light-client transport | Implemented fail-closed profile; upstream fix merged | Myotis merge `f639a7a7253aab2941400ba9c3827fbc23be429e` now exports the finalized execution height. Pin that revision or later and complete the ShopBridge sync, log-index, registry replay, restart, and weak-subjectivity freshness drill before production use |
| Registry contracts | Merchant Registry and Discovery Facets live on Tempo Moderato with public exact-match source | As of 2026-10-06, the two staging shop records are active and category-current at generation 3; the USD pilot record is revoked with reason `pilot_complete`. The Daybreak Blue model-assisted review found no critical issue and drove buyer-trust, rotation, WordPress SSRF, completeness-label, and publication fixes; production v2 and an external human review remain open |
| Merchant onchain enrollment | Implemented for a supervised Tempo Moderato pilot | Two-phase `prepare` derives four public WordPress identity values, validates the immutable merchant record, selects and simulates register/update, and emits a secret-free external-wallet request. Retained plans support revoke preparation even when the shop is unavailable |
| Registry write operator | Implemented with 30-minute intent-hash-bound plans, runtime/creation-boundary and finalized-state preflight, immutable-record revalidation, signer/controller matching, immediate post-broadcast journaling, exact transaction-inclusion verification, canonical receipt finality, and post-write state verification | External wallet is primary; the environment-key `execute` path is an isolated supervised fallback. Free-form mutations are not exposed. Pilot writes must be serialized per controller because the current contract lacks an atomic expected-current-hash mutation; Ethereum, Gnosis, and Tempo mainnet writes remain blocked by default |
| WordPress registry readiness | Implemented fail-closed with a pinned direct Tempo RPC verifier | Hosted submission, hosted event/health snapshots, and local HTTPS proof do not count as canonical inclusion. `finalized_current` requires one fresh finalized block hash, EIP-1898 canonical state reads, the pinned deployment block/creation boundary/runtime, Ethereum Keccak of the normalized shop hostname, and the exact active chain, contract, current controller, stable domain-mapped record id, record hash, status, and non-revocation. The result trusts the named pinned RPC; hosted data is retained only as labeled operator compatibility evidence |
| External verifier | Implemented and live on Talos from the pinned GHCR digest | Payment, refund, replay-conflict, backup, and restart evidence pass; alert-webhook delivery remains open |
| Helm operations | Implemented and exercised; hosted registry deployment retired 2026-10-06 | Verifier-only external mode, Bound PVC-backed SQLite replay state, and restricted network policy remain implemented. The independent registry witness and Secret-backed authenticated alert receiver are no longer running. Payment-verifier alert delivery remains separate and open |
| Independent reconstruction | Implemented; recurring Tenderly comparison retired 2026-10-06; matched and firing/resolved delivery evidence retained | Before a future deployment, add a durable secondary pager and perform a real controlled witness outage/divergence exercise. Conduit's pruned history cannot replay from deployment |
| Ethereum/Gnosis/Tempo production | Not approved | Requires the promotion gates in ADR 0008 and a new production-network ADR |

## Testnet Deployment

- Network: Tempo Moderato (`eip155:42431`)
- Contract: `0x0965961617c5B0898167AA4034C5511dB0EfcA07`
- Discovery Facets contract: `0x693de216d208ADC933365bD6F4FCbC062BB8Afe5`
- Discovery Facets deployment block: `32721088`
- Deployment transaction:
  `0xad99d0e1f877af983fd372657fdac9bfd4f6b467b3f9bfbdd024ecd5bc831481`
- Deployment block: `30731101`
- Governance: dedicated EOA, trusted-operator testnet pilot
- State: two staging shop records active with generation 3 categories as of
  2026-10-06; original USD pilot record revoked with reason `pilot_complete`

Tempo's public verifier now reports `exact_match` and runtime `exact_match` for
both pilot contracts and exposes their complete source sets. The guarded
`tempo-contract-verification.yml` workflow checks both deployments and accepts
an already-published result only after retrieving the authoritative exact
match. See `docs/CONTRACT_SOURCE_PUBLICATION.md`.

### 2026-10-06: hosted registry retired and registry re-anchored

Helm release `shopbridge-registry` (`charts/agentcart-shopbridge-registry/`),
its indexer/witness sidecar configuration, and `registry-alert-receiver` with
its Secret were removed from Talos after already being scaled to zero. The
recurring indexer, independent Tenderly witness comparison, and authenticated
alert receiver are no longer running. The chart remains for self-hosting.
`https://registry.agentcart.eu/` now serves only OCI container images at
`/v2/`; the former `/`, `/registry`, and `/v1/registry/...` routes return 404.

The `woo-usd.agentcart.eu` pilot record was revoked with reason
`pilot_complete` in transaction
`0x233e040d598a5e2077b5060fe1573884a31157fd3c314534a705e8b09c9f4677`.
That shop and the EUR demo `woo-staging.agentcart.eu`, whose storage had
already been deleted, were removed from the cluster together with their DNS
records. Their earlier evidence remains historical.

The two active staging shops were updated to their current immutable records
and their categories republished at Discovery Facets generation 3:

| Shop | Record update | Record hash | Finalized block | Categories tx |
| --- | --- | --- | --- | --- |
| `value-shop.staging.agentcart.eu` | `0xe2fa99dfe91414dc15f0fa9e9f09b9601243bd9e2e3aae4011c3e515a3d69c7c` | `0xce60157a10b71093563f6bce51b267e2ab6006755e46ebf80965ad5305c4832d` | 38400918 | `0xbb07f00e02aad779a1fff9953ea4d398a52c471c355fbdd2ca6ece3d7417fb63` |
| `premium-shop.staging.agentcart.eu` | `0x4bee1e693ab76b9e2d1e922a08046ccde5fbbd7206972f36d4b2bb28d544bcce` | `0x4b6f07c796e923f3dce37548a31a0b1c91a2034679256ea78744c5c8b4b41de0` | 38400944 | `0x1803faf60e97188a8d337b11b048c59560f996fc01802eab568e6719a84ea285` |

All three record writes were made by the registry controller through the
supervised isolated-signer fallback of
`gateway/scripts/onchain-registry-operator.mjs`; categories used
`onchain-discovery-facets-operator.mjs`. The writes were verified at finality.
Before the updates, all three registered records failed with
`registry_record_fetch_failed`: the reinstalled staging shops no longer served
the committed hashes, and woo-usd was gone. A fresh default `discover_quotes`
run of the public Direct Skill, with no hosted registry or base URL, found
AgentCart Value Tea Shop at 1217 cents and AgentCart Premium Tea Shop at 1607
cents. Skill `doctor` reported zero record-resolution errors. Buyer discovery
never depended on the hosted registry; the skill reads both contracts over
JSON-RPC.

### Historical deployment and lifecycle evidence (2026-08-23–2026-08-27)

The public HTTPS registry was upgraded to chart 0.3.0 on 2026-08-23. Helm
revision 13 was deployed with two ready replicas and two ready service
endpoints. Health and records returned HTTP 200 with the active USD staging
entry and advertised the real Tempo contract as `testnet_only`. Ethereum was
`not_deployed`, OCI `/v2/` remained available, registry mutations returned HTTP
405, and the same-origin finalized-events route was live. Each pod ran the
least-privilege recurring indexer without a Kubernetes service-account token.

The lifecycle used record id
`0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b`.
Registration of hash `460a16a4...c26bef` finalized in transaction
`0x13f10d4a46c16b67709c7aea409faef3a3b666811e063b7c8ff6f760d92e0769`;
revocation finalized in
`0x785cd582d7c77b025e284ed104b103f987a00519f6c8918215d7a8470d1f325a`;
and recovery to hash `c8236a74...f702a66` finalized in
`0x995de9a5b0f0c3774e164917d01287fb32e95499c8f6c50614637dc91eb3c060`.
Both immutable documents remained fetchable at that time, and the merchant's
HTTPS revocation document retained the first hash.

The hosted snapshot through finalized block `32138528` and independent dRPC
and Tenderly snapshots through blocks `32138688` and `32138796` were complete,
zero-error outputs with the same four events. Canonical `.events` JSON had
SHA-256 `f5322c1cd41d6e1bf34c28604b10fc97f6801ae4793d575a3ef4c343170440c0`
on every path. Conduit correctly failed closed because its available history
started after the deployment block. The sidecars checked chain and contract
identity, published only complete snapshots atomically, and relied on the
shared ten-minute snapshot and finalized-block freshness boundary to expire an
extended outage or frozen RPC response.

The chart mounts the indexer program from a ConfigMap. A deployment regression
test now covers that symlinked entrypoint explicitly: the loop resolves both
the ESM module URL and invocation path before deciding whether to run. This
prevents a clean exit without indexing when Kubernetes presents the script
through its `..data` symlink layout.

The packaged sidecar can now read a witness URL from an existing Kubernetes
Secret, compare chain and registry identity, equal-height finalized block
hashes, and SHA-256 of canonical events through the lower finalized head. It
publishes only that matched range. A witness outage, mismatch, or finality-time
lag above the configured bound preserves the previous snapshot and emits a
redacted, throttled `agentcart.onchain_registry_independent_rpc_alert.v1`
webhook event when a receiver is configured. Repeated identical failures are
throttled and recovery produces a resolved event. RPC URLs never enter the
proof or alert payload.

The packaged Direct Skill demonstrated all three externally visible lifecycle
states. It resolved the first registered hash after finality, removed the USD
merchant from eligibility immediately after onchain revocation, and resolved
the recovered hash after re-registration. It now queries the Tempo RPC directly
instead of obtaining candidate membership and lifecycle from the hosted
`/records` or `onchain_events_url` views. A live `doctor` run on 2026-08-23 read
the contract from deployment block `30731101` through finalized block
`32158760`, proved the historical contract-creation boundary, matched the
recovered record against contract storage, and verified the USD merchant's
manifest, domain proof, payment binding, and revocation document with zero
trust errors. A live `discover_quotes` call then discovered Hazel's Chocolate
Tea, correctly rejected delivery to DE, and produced a 15.78 USD Tempo-MPP
testnet quote plus human-approval packet for US delivery. No registry
environment variable was needed. The curated EUR staging entry is therefore no
longer returned by default because it is not registered onchain.

On 2026-08-27 the same unconfigured Direct Skill discovered three active USD
shops from the Merchant Registry at finalized block `32727192`. The hosted
discovery index was unconfigured and unused. A live `tea` request used the
on-chain Discovery Facets module, matched all three eligible records, sent
private quote requests to all three verified shop domains, and ranked the
financially consistent totals at 12.17, 15.78, and 16.07 USD. The 12.17 USD
value shop won. Every candidate advertised a configured Tempo MPP verifier; the
only checkout issue was the deliberately incomplete buyer address, so no
payment or order was attempted. Detailed evidence is in
`docs/MULTISHOP_ONCHAIN_RANKING_TEST.md`.

## Talos USD Verifier

`agentcart-demo/woo-usd-verifier` runs one Ready, zero-restart replica from:

`ghcr.io/giraeffleaeffle/agentcart-shopbridge-verifier@sha256:14c037261ba95c2e92674189dda23eb67f040406461e132e442a983011c37142`

Release `v1.19.0` was deployed to the Talos reference shop on 2026-08-26. A
fresh Direct Skill doctor matched the contract projection and storage at
finalized block `32559333`, verified the committed USD merchant record and
domain, found Hazel's Chocolate Tea, and produced a complete-address 15.78 USD
quote whose subtotal, shipping, and gross-tax metadata reconciled exactly.
Both `approval_packet.approval_ready` and `checkout_preflight.ok` were true. No
buyer checkout was executed during that read-only approval-path test.

The 1,578-cent USD drill bound quote hash `a12ac8ce...f9fd8` to payment
contract hash `aab9c536...9dc80`. Payment transaction
`0x10556e9076df171228c35ea0f0a5378e6a4f0b7dc3446df147ec1e8af04e598c`
and refund transaction
`0xb56ad3fcb63768d20e29ae5486b83122a7c7bdbc95c1678d91da09534bd7d009`
both succeeded on Tempo testnet with the expected 15.78 pathUSD transfer.

A conflicting reuse of the settled payment reference returned HTTP 409 with
`replay_conflict=true`. SQLite counts remained one payment, one refund request,
and one refund before and after the verifier restart and conflict probe. The
Bound PVC retains a verified online backup with SHA-256
`f7f5d083284781f99a32c75748fa3844893d05285326ec56ac71f48855101d2d`.
The warning event was generated, but delivery was skipped because no alert
webhook is configured.

The `v1.19.0` deployment rehearsal added a second quote-bound pathUSD testnet
payment and verifier-backed refund. The durable replay counts were two
payments, two refund requests, and two refunds both before and after the
mandatory verifier restart.

## Ordered Completion Gate

1. **Complete:** deploy the hardened USD ShopBridge profile to Talos and record
   quote-bound payment, verifier-backed refund, replay rejection, and PVC
   restart/recovery evidence.
2. **Complete:** register the Moderato merchant and expose it only after
   finality.
3. **Complete:** prove Direct Skill discovery, revoke the first hash, and
   recover through a new immutable hash.
4. **Complete:** reproduce the finalized lifecycle through two independent
   full-history RPC/indexer paths.
5. **Complete:** package and publish the supervised merchant flow with public
   WordPress identity, immutable merchant records, two-phase external-wallet
   plans, exact finalized verification, and retained-plan revocation.
6. **Complete for the maintainer reference shop:** deploy release `v1.19.0`,
   re-run finalized discovery, and reach an approval-ready, financially
   consistent quote without executing buyer checkout.
7. **Complete for the maintainer multi-shop environment:** deploy two additional
   USD/pathUSD shops, register all three shops and their categories on-chain,
   and prove category-routed buyer-side quote comparison selects the lowest
   final price without a hosted discovery index.
8. **External next step:** hand the released skill to a non-maintainer buyer
   agent, and run a non-maintainer merchant installation and Tempo Moderato
   enrollment session.

## Current External Gate

PRs #60, #61, and #65 are merged. GitHub release `v1.19.0` contains the public
plugin and skill artifacts, and GitHub published the public amd64 verifier
image with provenance, SBOM, and attestation. The Talos pull and live reference
shop rollout succeeded; no developer-machine container build was used.

The remaining gates are explicit:

- implement and externally review the production-v2 validator, admission, and
  candidate-backfill hardening recorded by the security review;
- name and configure the production Safe/timelock operators required by ADR
  0012;
- add secondary durable registry paging and run a controlled real witness
  outage/divergence exercise;
- run the released skill with a non-maintainer buyer agent and complete an
  external merchant installation, controller-wallet, update, and revoke
  session;
- complete merchant-specific external-verifier onboarding against the published
  plugin flow;
- drill the fixed Myotis adapter only if the verified light-client path is part
  of the Ethereum/Gnosis network evaluation, including daily weak-subjectivity
  freshness expectations for intermittently online mobile/desktop harnesses;
- accept a new ADR before any Ethereum, Gnosis, or Tempo production deployment.

Detailed redacted evidence is in
`pilot-evidence/woo-usd-staging/attachments/talos-usd-verifier-live-drill-2026-08-23.md`
and
`pilot-evidence/woo-usd-staging/attachments/tempo-registry-lifecycle-2026-08-23.md`.
