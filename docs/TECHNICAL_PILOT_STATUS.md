# Technical Pilot Status

> Snapshot: 2026-08-23. This is a testnet engineering status, not a production
> or mainnet-readiness claim.

## Outcome

The remaining registry design questions have been converted into implemented
interfaces and a reversible testnet deployment. The buyer-facing Direct Skill,
hosted registry adapter, and onchain indexer now share the same trust and
lifecycle semantics. The external verifier has a production-shaped,
Tempo-capable deployment package with persistent replay protection.

The recurring finalized feed is now live on the public testnet registry. The
next work is the recorded merchant lifecycle, payment/refund evidence, and
non-maintainer usability sessions, not another registry redesign.

## Package Status

| Package | State | Evidence or remaining gate |
| --- | --- | --- |
| Shared registry trust contract | Implemented and covered by gateway, helper, fixture, and Direct Skill tests | Keep the portable-skill package contract test mandatory |
| Buyer discovery HTTP boundary | Implemented as a portable redirect-free, size-bounded, DNS-pinned transport | Private/local targets require explicit opt-in |
| Finalized onchain projection | Implemented and fail-closed | Covers registration, update, controller rotation, suspension, attestation, revoke, and supersession/recovery |
| Immutable full-record archive | Implemented in the public-registry chart | Old content hashes remain fetchable after revoke/recovery |
| Reference RPC indexer | Implemented and live on the public testnet registry | Reads no newer than `finalized`, records block identity/range, validates record hash/controller binding, atomically publishes only complete snapshots, and preserves the last good snapshot until buyer freshness enforcement expires it |
| Buyer auto-discovery | Implemented and live | Direct Skill discovers the public same-origin `onchain_events_url` and rejects invalid, incomplete, stale, or non-finalized feeds |
| Registry contract | Deployed empty on Tempo Moderato | First live record lifecycle is intentionally pending |
| Registry write operator | Implemented with explicit command/chain/contract acknowledgement | Ethereum and Tempo mainnet writes remain blocked by default |
| External verifier | Implemented; pinned non-root image published to GHCR with provenance and SBOM | Deploy the USD verifier profile by digest, then record live payment, refund, replay, and restart evidence |
| Helm operations | Implemented | Verifier-only external mode, secret references, PVC-backed SQLite replay state, and restricted network policy |
| Ethereum/Tempo production | Not approved | Requires the promotion gates in ADR 0008 and a new production-network ADR |

## Testnet Deployment

- Network: Tempo Moderato (`eip155:42431`)
- Contract: `0x0965961617c5B0898167AA4034C5511dB0EfcA07`
- Deployment transaction:
  `0xad99d0e1f877af983fd372657fdac9bfd4f6b467b3f9bfbdd024ecd5bc831481`
- Deployment block: `30731101`
- Governance: dedicated EOA, trusted-operator testnet pilot
- State: deployed and empty; no merchant is represented as onchain yet

The deployment receipt records a local/runtime bytecode hash match. Explorer
source verification remains outstanding and must not be confused with bytecode
matching.

The public HTTPS registry was upgraded to chart 0.3.0 on 2026-08-23. Helm
revision 11 is deployed with two ready replicas and two ready service endpoints.
Health and records return HTTP 200 with the two curated staging entries and
advertise the real Tempo contract as `testnet_only`. Ethereum remains
`not_deployed`, OCI `/v2/` remains available, registry mutations remain HTTP
405, and the same-origin finalized-events route is live. Each pod runs the
least-privilege recurring indexer without a Kubernetes service-account token.

The final deployment receipt records a complete, zero-error replay through
finalized block `32131761`; an earlier independent public check observed the
same recurring feed advancing normally.
Both snapshots contain the constructor ownership event and no merchant record,
because the prepared pilot merchant is still deliberately unregistered. The
sidecar checks the selected chain id and contract address, writes only complete
snapshots atomically, permits egress only to DNS and public HTTPS, and leaves
stale-feed rejection to the shared ten-minute buyer trust window.

The chart mounts the indexer program from a ConfigMap. A deployment regression
test now covers that symlinked entrypoint explicitly: the loop resolves both
the ESM module URL and invocation path before deciding whether to run. This
prevents a clean exit without indexing when Kubernetes presents the script
through its `..data` symlink layout.

After the buyer HTTP boundary was hardened, the packaged Direct Skill `doctor`
was run against the live public registry. It loaded both entries through the
DNS-pinned HTTPS transport, then fetched and verified each merchant's manifest,
domain proof, payment binding, and revocation document with zero trust errors.

## Ordered Completion Gate

1. Deploy the hardened USD ShopBridge profile to Talos and capture a real
   quote-bound payment, real verifier-backed refund, replay rejection, and PVC
   restart/recovery result.
2. Register the prepared Moderato merchant record and index it only after
   finality.
3. Prove Direct Skill discovery from the finalized feed, revoke the first hash,
   and recover through a new immutable record hash.
4. Reproduce the same finalized state through an independent RPC/indexer path.
5. Hand the packaged skill to a non-maintainer buyer agent. After that succeeds,
   begin external merchant installability sessions.

## Current External Gate

PR #60 is merged and `.github/workflows/verifier-image.yml` published the
public amd64 image with provenance, SBOM, and GitHub attestation. The immutable
runtime used by both registry pods is
`ghcr.io/giraeffleaeffle/agentcart-shopbridge-verifier@sha256:689e62705ec34112b053fbfc0461e26477055678cb3eb00ccfa1437c79de75e8`.
Anonymous manifest access and the Talos pull both succeeded; no developer-machine
container build or temporary in-cluster uploader was used. The remaining
external gate is operational evidence from the USD verifier deployment and the
merchant registration/revocation/recovery drill. No production chain was
touched.
