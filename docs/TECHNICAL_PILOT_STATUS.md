# Technical Pilot Status

> Snapshot: 2026-08-26. This is a testnet engineering status, not a production
> or mainnet-readiness claim.

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
to an external wallet and verifies exact state only at finality. This package
has not yet passed a non-maintainer merchant session. What remains is operator
activation and delivery evidence, source publication, external verifier and
security/governance evidence, and non-maintainer buyer and merchant evidence.
No production chain or real-money rail was used.

## Package Status

| Package | State | Evidence or remaining gate |
| --- | --- | --- |
| Shared registry trust contract | Implemented and covered by gateway, helper, fixture, and Direct Skill tests | Keep the portable-skill package contract test mandatory |
| Buyer discovery HTTP boundary | Implemented as a portable redirect-free, size-bounded, DNS-pinned transport | Private/local targets require explicit opt-in |
| Finalized onchain projection | Implemented and fail-closed | Covers registration, update, controller rotation, suspension, attestation, revoke, and supersession/recovery |
| Immutable full-record archive | Implemented in the public-registry chart and as merchant-hosted content-addressed WordPress snapshots | Old content hashes remain fetchable after revoke/recovery while the plugin remains installed. Production still needs a separately operated append-only copy because disablement makes the merchant route unavailable and uninstall removes the plugin archive |
| Reference RPC indexer | Implemented and live on the public testnet registry; independent witness mode is packaged | Reads no newer than `finalized`, records block identity/range/time, validates record hash/controller binding, atomically publishes only complete snapshots, and preserves the last good snapshot until buyer freshness enforcement expires it. Optional witness mode publishes only the common matched range and rejects stalled or divergent paths |
| Buyer auto-discovery | Implemented and live | Direct Skill queries Tempo JSON-RPC itself, replays finalized eligibility events, verifies committed record documents, and checks projected records against contract storage; hosted event feeds remain compatibility inputs |
| Category-routed discovery | Implemented in source; live record refresh pending | Optional bounded facets are derived from the merchant's exposed catalog, hash-committed by the Registry Record, and projected through an untrusted record-id index. Buyer discovery keeps a neutral fallback and still confirms products in the current merchant catalog. Re-enroll the Tempo merchant with a facet-bearing record before the public index can advertise categories |
| Buyer quote and payment readiness | Implemented in source after the first workstation-agent run exposed the ambiguity | Discovery explicitly requires no wallet; payment readiness is reported separately without invoking payment tools; country/postcode quotes are comparison-only; approval, payment, and checkout require a refreshed financially consistent quote with a complete buyer-supplied delivery address. Publish the updated skill/plugin and repeat the external run |
| Buyer verified-light-client transport | Implemented fail-closed profile; upstream fix merged | Myotis merge `f639a7a7253aab2941400ba9c3827fbc23be429e` now exports the finalized execution height. Pin that revision or later and complete the ShopBridge sync, log-index, registry replay, restart, and weak-subjectivity freshness drill before production use |
| Registry contract | Live on Tempo Moderato with a finalized register/revoke/recover drill | The recovered USD record is active; source publication and independent security review remain open |
| Merchant onchain enrollment | Implemented for a supervised Tempo Moderato pilot | Two-phase `prepare` derives four public WordPress identity values, validates the immutable merchant record, selects and simulates register/update, and emits a secret-free external-wallet request. Retained plans support revoke preparation even when the shop is unavailable |
| Registry write operator | Implemented with 30-minute intent-hash-bound plans, runtime/creation-boundary and finalized-state preflight, immutable-record revalidation, signer/controller matching, immediate post-broadcast journaling, exact transaction-inclusion verification, canonical receipt finality, and post-write state verification | External wallet is primary; the environment-key `execute` path is an isolated supervised fallback. Free-form mutations are not exposed. Pilot writes must be serialized per controller because the current contract lacks an atomic expected-current-hash mutation; Ethereum, Gnosis, and Tempo mainnet writes remain blocked by default |
| WordPress registry readiness | Implemented fail-closed with a pinned direct Tempo RPC verifier | Hosted submission, hosted event/health snapshots, and local HTTPS proof do not count as canonical inclusion. `finalized_current` requires one fresh finalized block hash, EIP-1898 canonical state reads, the pinned deployment block/creation boundary/runtime, Ethereum Keccak of the normalized shop hostname, and the exact active chain, contract, controller, controller-bound deterministic record id, record hash, domain mapping, and non-revocation. The result trusts the named pinned RPC; hosted data is retained only as labeled operator compatibility evidence |
| External verifier | Implemented and live on Talos from the pinned GHCR digest | Payment, refund, replay-conflict, backup, and restart evidence pass; alert-webhook delivery remains open |
| Helm operations | Implemented and exercised | Verifier-only external mode, Bound PVC-backed SQLite replay state, restricted network policy, and opt-in Secret-backed alert delivery are packaged; the live receiver is still unconfigured |
| Independent reconstruction | Passed manually with dRPC and Tenderly; automatic comparison and webhook alerting implemented | Activate it with an independently operated full-history RPC and real receiver, then retain matched, firing, and resolved delivery evidence. Conduit's pruned history cannot replay from deployment |
| Ethereum/Gnosis/Tempo production | Not approved | Requires the promotion gates in ADR 0008 and a new production-network ADR |

## Testnet Deployment

- Network: Tempo Moderato (`eip155:42431`)
- Contract: `0x0965961617c5B0898167AA4034C5511dB0EfcA07`
- Deployment transaction:
  `0xad99d0e1f877af983fd372657fdac9bfd4f6b467b3f9bfbdd024ecd5bc831481`
- Deployment block: `30731101`
- Governance: dedicated EOA, trusted-operator testnet pilot
- State: recovered USD merchant record active after finalized revoke/re-register

The deployment receipt records a local/runtime bytecode hash match. Explorer
source publication remains outstanding and must not be confused with bytecode
matching. Publishing the full source to `contracts.tempo.xyz` requires a
separate explicit external-publication approval. The manual
`tempo-contract-verification.yml` workflow performs that publication in GitHub,
requires a typed acknowledgement, and fails unless the service reports
`exact_match`; it has not been triggered.

The public HTTPS registry was upgraded to chart 0.3.0 on 2026-08-23. Helm
revision 13 is deployed with two ready replicas and two ready service endpoints.
Health and records return HTTP 200 with the two curated staging entries and
advertise the real Tempo contract as `testnet_only`. Ethereum remains
`not_deployed`, OCI `/v2/` remains available, registry mutations remain HTTP
405, and the same-origin finalized-events route is live. Each pod runs the
least-privilege recurring indexer without a Kubernetes service-account token.

The lifecycle used record id
`0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b`.
Registration of hash `460a16a4...c26bef` finalized in transaction
`0x13f10d4a46c16b67709c7aea409faef3a3b666811e063b7c8ff6f760d92e0769`;
revocation finalized in
`0x785cd582d7c77b025e284ed104b103f987a00519f6c8918215d7a8470d1f325a`;
and recovery to hash `c8236a74...f702a66` finalized in
`0x995de9a5b0f0c3774e164917d01287fb32e95499c8f6c50614637dc91eb3c060`.
Both immutable documents remain fetchable, and the merchant's HTTPS revocation
document retains the first hash.

The hosted snapshot through finalized block `32138528` and independent dRPC
and Tenderly snapshots through blocks `32138688` and `32138796` were complete,
zero-error outputs with the same four events. Canonical `.events` JSON had
SHA-256 `f5322c1cd41d6e1bf34c28604b10fc97f6801ae4793d575a3ef4c343170440c0`
on every path. Conduit correctly failed closed because its available history
started after the deployment block. The sidecars continue to check chain and
contract identity, publish only complete snapshots atomically, and rely on the
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
7. **External next step:** hand the released skill to a non-maintainer buyer
   agent, and run a non-maintainer merchant installation and Tempo Moderato
   enrollment session.

## Current External Gate

PRs #60, #61, and #65 are merged. GitHub release `v1.19.0` contains the public
plugin and skill artifacts, and GitHub published the public amd64 verifier
image with provenance, SBOM, and attestation. The Talos pull and live reference
shop rollout succeeded; no developer-machine container build was used.

The remaining gates are explicit:

- provision an independently operated full-history witness RPC, activate the
  packaged comparison mode, and retain matched/divergence/resolution evidence;
- configure a real verifier alert receiver and observe delivery;
- explicitly authorize contract-source publication, then record the verification
  result;
- obtain an independent contract/security review and production governance
  decision;
- run the released skill with a non-maintainer buyer agent and complete an
  external merchant installation, controller-wallet, update, and revoke
  session;
- complete merchant-specific external-verifier onboarding against the published
  plugin flow;
- drill the fixed Myotis adapter only if the verified light-client path is part
  of the Ethereum/Gnosis network evaluation, including daily weak-subjectivity
  freshness expectations for intermittently online mobile/desktop harnesses;
- regenerate and finalize the Tempo merchant's facet-bearing Registry Record,
  publish the resulting discovery-index entry, and repeat cross-shop discovery;
- accept a new ADR before any Ethereum, Gnosis, or Tempo production deployment.

Detailed redacted evidence is in
`pilot-evidence/woo-usd-staging/attachments/talos-usd-verifier-live-drill-2026-08-23.md`
and
`pilot-evidence/woo-usd-staging/attachments/tempo-registry-lifecycle-2026-08-23.md`.
