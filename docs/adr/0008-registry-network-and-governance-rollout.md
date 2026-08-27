# ADR 0008: Registry Network And Governance Rollout

## Status

Accepted for the testnet pilot; production network selection remains open.

## Context

ADR 0007 defines what the onchain merchant registry is allowed to prove. It
does not choose a production chain, owner, validator set, RPC provider, or
emergency authority. Combining those choices with the registry data model
would make a reversible pilot deployment look like an endorsement of one
production network and one permanent governance arrangement.

The project needs a real-chain drill now, but it does not yet have external
merchant evidence, an audited contract, independent validators, production
RPC/indexer redundancy, or an agreed multisig. Ethereum mainnet, Gnosis
mainnet, and Tempo mainnet therefore have materially different costs and
operational trade-offs that cannot be decided from the prototype alone.

## Decision

Use Tempo Moderato (`eip155:42431`) for the first reversible registry drill.
The testnet contract is a trusted-operator pilot, not a neutral or production
registry.

The pilot uses three separate disposable identities:

- an owner/deployer for delayed administrative actions;
- a merchant controller that never runs on the WordPress server;
- a validator identity for later attestation drills.

The owner is temporarily a dedicated EOA. Contract writes, validator-set
changes, threshold changes, and force revocation remain visibly operator
controlled. Existing contract timelocks and two-step ownership transfer are
exercised locally and on testnet where their wall-clock delays permit, but they
do not turn an EOA-owned deployment into decentralized governance.

The reference write operator reads keys only from the environment, requires an
explicit command/chain/contract acknowledgement, and blocks Ethereum, Gnosis,
and Tempo mainnet mutations unless a separate production override is set.

The reference indexer must read only logs at the RPC `finalized` block tag,
record the indexed range and finalized block hash, fetch full records through
SSRF-resistant HTTPS handling, verify their hash commitment, and fail closed on
decode or record-fetch errors. The hosted registry remains a replaceable cache
and monitor over that output.

For the pilot deployment, finalized snapshots are refreshed by a sidecar in
each read-only registry pod. The sidecar has no Kubernetes API credentials,
selects the contract address and expected chain id from the declared deployment,
uses only public HTTPS egress, and atomically publishes only complete output.
During a transient RPC error it retains the last complete snapshot; the shared
buyer trust contract rejects that snapshot after ten minutes, so an extended
outage cannot silently preserve eligibility. A static snapshot remains a
fixture/drill mode, not the live operating mode.

No Ethereum mainnet, Gnosis mainnet, Tempo mainnet, or other production
deployment is approved by this ADR. The record and proof formats continue to
use CAIP-style chain ids and explicit registry addresses so a later network
decision is a deployment choice rather than a commerce-model rewrite.

## Buyer RPC And Verified Light-Client Option

The production chain decision is separate from how a buyer obtains chain data.
The Direct Skill now reconstructs merchant eligibility itself through standard
EVM JSON-RPC rather than accepting the hosted `/records` list as authority.
For Ethereum or Gnosis, Myotis is a promising optional buyer-side transport:
its Rust engine supports the required address/topic-filtered `eth_getLogs`,
receipt-root verification, `eth_getCode`, `eth_call`, and loopback JSON-RPC
ports `8545` and `8546` respectively. Its contract-scoped index refuses
unwatched or incompletely covered ranges instead of returning a false empty
result.

Myotis does not currently support Tempo. It also does not remove every local
cost: the buyer runs a P2P light client and builds a registry-specific log index
from the deployment block. That index must be built locally for the trustless
path; an imported snapshot is not independent provenance. The base light-client
disk footprint is small, but the optional index grows with contract activity
and its production resource profile still needs measurement.

Myotis merge commit `f639a7a7253aab2941400ba9c3827fbc23be429e`
resolved the blocking adapter defect by mapping the Rust engine's finalized
execution block into `beaconStatus`. ShopBridge no longer has a known upstream
compatibility blocker, but it still requires a pinned-revision end-to-end sync,
log-index backfill, finalized-height, registry replay, and restart drill. Until
that evidence is recorded, Myotis is an integration candidate, not a satisfied
production RPC or witness gate.

## Testnet Deployment Evidence

The empty trusted-operator contract was deployed on 2026-08-21:

| Field | Value |
| --- | --- |
| Network | Tempo Moderato (`eip155:42431`) |
| Contract | `0x0965961617c5B0898167AA4034C5511dB0EfcA07` |
| Deployment transaction | `0xad99d0e1f877af983fd372657fdac9bfd4f6b467b3f9bfbdd024ecd5bc831481` |
| Deployment block | `30731101` |
| Owner | `0xdaa1fFf25C08b5AaAAA3D3405Ab8Db7D45F032D4` |
| Prepared pilot controller | `0x015f6aB1b682aEa664A1E4896f363ca3093e4591` |
| Prepared pilot record id | `0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b` |

The deployed runtime bytecode hash matches the locally compiled contract.
Contract source publication has not been authorized, so source verification
remains an operational evidence item and must not be conflated with the
runtime-bytecode match. A manual GitHub workflow pins the original compiler,
optimizer, EVM target, source paths, and creation transaction; it requires a
typed acknowledgement and accepts only `exact_match`. The workflow has not
been triggered. Ethereum mainnet, Gnosis mainnet, and Tempo production remain
untouched.

On 2026-08-21, the reference indexer replayed deployment block `30731101`
through finalized block `31831769` (`0x8efe988fa5c66ebf7786c18d42833398e35e67de4a49e388ce0462313c179d78`).
The envelope was complete with no errors and projected one constructor
ownership event, zero merchant records, and zero revocations.

Chart version 0.3.0 and the recurring feed were activated on the public Talos
registry on 2026-08-23. Helm revision 13 reports `deployed`; both registry pods
are Ready with zero container restarts and use the pinned runtime:

`ghcr.io/giraeffleaeffle/agentcart-shopbridge-verifier@sha256:689e62705ec34112b053fbfc0461e26477055678cb3eb00ccfa1437c79de75e8`

The first live lifecycle was completed on 2026-08-23 for record id
`0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b`:

| Transition | Record hash | Transaction | Block |
| --- | --- | --- | ---: |
| Register | `460a16a43eb69734cd21b0554d4521ee59fb551bb305880dd7aeaf7742c26bef` | `0x13f10d4a46c16b67709c7aea409faef3a3b666811e063b7c8ff6f760d92e0769` | 32136514 |
| Revoke | same, now monotonically revoked | `0x785cd582d7c77b025e284ed104b103f987a00519f6c8918215d7a8470d1f325a` | 32137027 |
| Recover | `c8236a74b9d936065e3283c719f421312f4681e6d5015294f268526c6f702a66` | `0x995de9a5b0f0c3774e164917d01287fb32e95499c8f6c50614637dc91eb3c060` | 32137803 |

The old and recovered full records remain publicly content-addressed. The
merchant revocation document retains the old hash, while its current
controller-bound proof binds the recovered hash. The Direct Skill followed
the finalized feed through eligible, ineligible, and recovered states without
an onchain-feed override.

The hosted indexer, dRPC, and Tenderly each replayed from deployment block
`30731101` to a public `finalized` block. Every output was complete and
zero-error and contained the same four-event history. Canonical `.events` JSON
had SHA-256
`f5322c1cd41d6e1bf34c28604b10fc97f6801ae4793d575a3ef4c343170440c0`
on all three paths. Conduit could identify chain 42431 but correctly failed
closed because its retained history began after the deployment block. The
manual independent-reconstruction part of promotion gate 4 is therefore
complete. The registry chart now packages automatic cross-RPC comparison that
publishes only the common matched finalized range, rejects mismatched chain,
contract, event hash, equal-height block hash, or excessive finality-time lag,
and emits throttled firing/resolved webhook events. Promotion gate 4 remains
open until an independently operated full-history witness and real receiver are
enabled on the pilot and the matched/divergence/recovery evidence is retained.

The complete redacted lifecycle record is
`pilot-evidence/woo-usd-staging/attachments/tempo-registry-lifecycle-2026-08-23.md`.

Kubernetes mounts ConfigMap files through symlinks. The recurring wrapper now
canonicalizes both its ESM module URL and invocation path before running, and a
regression test reproduces the ConfigMap-style symlink layout. The sidecar has
no Kubernetes credentials and the NetworkPolicy permits only cluster DNS and
public HTTPS egress.

## Production Promotion Gates

A production-network ADR may be accepted only after:

1. at least one external merchant and one non-maintainer buyer-agent pilot have
   produced install, discovery, quote, payment, refund, and recovery evidence;
2. the contract and controller-bound proof flow have had an independent
   security review;
3. owner, pause, validator, threshold, and emergency paths are held by a
   timelocked multisig or an equally public process with named operators and a
   tested ownership-transfer runbook;
4. at least two independent RPC/indexer paths reproduce the same finalized
   state and alert on divergence;
5. controller loss, domain loss, revocation, supersession, and migration to a
   successor contract have been drilled;
6. network fees, finality, explorer/tooling support, stablecoin/payment fit,
   and merchant transaction sponsorship are measured with pilot traffic;
7. the chosen deployment has a public rollback/migration plan and does not
   claim neutrality beyond its actual governance.

Ethereum, Gnosis, and Tempo should be evaluated against those gates. The
evaluation must include whether ordinary buyers can self-verify discovery
without a full node, but Myotis availability alone must not select the chain.
Registration bond, validator stake, slashing, paid placement, and ranking
remain out of scope for the network decision.

## Consequences

- The team can exercise real finalized logs, controller proofs, revocation, and
  recovery without implying mainnet readiness.
- Pilot addresses and receipts are evidence, not stable production identifiers.
- A future production choice requires a new ADR and cannot silently reuse the
  pilot owner EOA.
- A verified light-client buyer path can reduce dependence on hosted RPCs on
  supported networks, but it does not replace operator monitoring, deployment
  evidence, or independent witness requirements until separately evidenced.
- Merchant and buyer clients must display the chain, registry address, record
  status, and governance mode instead of reducing trust to a generic
  "onchain" badge.
