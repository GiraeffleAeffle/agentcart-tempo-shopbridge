# Technical Pilot Status

> Snapshot: 2026-08-21. This is a testnet engineering status, not a production
> or mainnet-readiness claim.

## Outcome

The remaining registry design questions have been converted into implemented
interfaces and a reversible testnet deployment. The buyer-facing Direct Skill,
hosted registry adapter, and onchain indexer now share the same trust and
lifecycle semantics. The external verifier has a production-shaped,
Tempo-capable deployment package with persistent replay protection.

The next work is operational evidence, not another registry redesign.

## Package Status

| Package | State | Evidence or remaining gate |
| --- | --- | --- |
| Shared registry trust contract | Implemented and covered by gateway, helper, fixture, and Direct Skill tests | Keep the portable-skill package contract test mandatory |
| Buyer discovery HTTP boundary | Implemented as a portable redirect-free, size-bounded, DNS-pinned transport | Private/local targets require explicit opt-in |
| Finalized onchain projection | Implemented and fail-closed | Covers registration, update, controller rotation, suspension, attestation, revoke, and supersession/recovery |
| Immutable full-record archive | Implemented in the public-registry chart | Old content hashes remain fetchable after revoke/recovery |
| Reference RPC indexer | Implemented, including recurring chart runtime | Reads no newer than `finalized`, records block identity/range, validates record hash/controller binding, atomically publishes only complete snapshots, and preserves the last good snapshot until buyer freshness enforcement expires it |
| Buyer auto-discovery | Implemented | Direct Skill discovers a same-origin `onchain_events_url` and rejects invalid or non-finalized feeds |
| Registry contract | Deployed empty on Tempo Moderato | First live record lifecycle is intentionally pending |
| Registry write operator | Implemented with explicit command/chain/contract acknowledgement | Ethereum and Tempo mainnet writes remain blocked by default |
| External verifier | Implemented and packaged as a pinned, non-root OCI image | Publish to a writable registry, deploy by digest, then record live USD evidence |
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

The public HTTPS registry was checked and upgraded on 2026-08-21. Health and
records return HTTP 200 with the two curated staging entries; Helm revision 2
has two ready replicas and reports the real Tempo contract as `testnet_only`.
Ethereum remains `not_deployed`, OCI `/v2/` remains available, and registry
mutations remain HTTP 405. The finalized-events route stays disabled in Helm
revision 2. Its automatic, least-privilege refresh path is now implemented in
chart version 0.3.0, but activation still requires publishing the pinned
runtime image and completing the first merchant lifecycle drill.

The reference indexer also replayed the real contract from deployment through
finalized block `31831769`. It returned a complete, error-free envelope with
the constructor ownership event and no merchant records or revocations. Remote
buyers reject finalized snapshots older than 600 seconds, so enabling the feed
requires a recurring refresher. The chart's sidecar supplies it without
Kubernetes API credentials. It checks the selected deployment's chain id and
address, writes
only complete snapshots atomically, permits egress only to DNS and public
HTTPS, and leaves stale-feed rejection to the shared ten-minute buyer trust
window. It is configured but deliberately disabled in `values.pilot.yaml`
until the image digest is available.

The exact recurring wrapper was then exercised against the public Moderato RPC
through finalized block `31833475`
(`0x1c866d3afc58b44e5d8495c2bb1c64ce368b4ff3f22d86a74a97a7d68058b823`).
It enforced `eip155:42431` and the deployed registry address and atomically
wrote a complete snapshot with one ownership event and zero errors.

After the buyer HTTP boundary was hardened, the packaged Direct Skill `doctor`
was run against the live public registry. It loaded both entries through the
DNS-pinned HTTPS transport, then fetched and verified each merchant's manifest,
domain proof, payment binding, and revocation document with zero trust errors.

## Ordered Completion Gate

1. Merge or manually run `.github/workflows/verifier-image.yml`. Its GitHub
   runner smoke-tests the verifier, publishes it to GHCR with provenance and an
   SBOM, and records the immutable digest without building on a developer
   machine. Deploy that digest and activate the recurring finalized feed.
2. Deploy the hardened USD ShopBridge profile to Talos and capture a real
   quote-bound payment, real verifier-backed refund, replay rejection, and PVC
   restart/recovery result.
3. Register the prepared Moderato merchant record and index it only after
   finality.
4. Prove Direct Skill discovery from the finalized feed, revoke the first hash,
   and recover through a new immutable record hash.
5. Reproduce the same finalized state through an independent RPC/indexer path.
6. Hand the packaged skill to a non-maintainer buyer agent. After that succeeds,
   begin external merchant installability sessions.

## Current External Gate

Local GitHub CLI or registry authentication is no longer required for the
image build. `.github/workflows/verifier-image.yml` uses the repository's
short-lived `GITHUB_TOKEN` with job-scoped `packages: write` permission. Pull
requests build and smoke-test without package-write permission; pushes to
`main` and manual runs publish an amd64 GHCR image, SBOM, provenance, and
GitHub attestation. The workflow must first be pushed and merged, and the
resulting package must either be public or have a Talos image-pull secret
before deployment. Kubernetes security controls remain intact, no production
chain was touched, and no temporary in-cluster uploader is part of the
deployment.
