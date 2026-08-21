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
RPC/indexer redundancy, or an agreed multisig. Ethereum mainnet and Tempo
mainnet therefore have materially different costs and operational trade-offs
that cannot be decided from the prototype alone.

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
explicit command/chain/contract acknowledgement, and blocks both Ethereum and
Tempo mainnet mutations unless a separate production override is set.

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

No Ethereum mainnet, Tempo mainnet, or other production deployment is approved
by this ADR. The record and proof formats continue to use CAIP-style chain ids
and explicit registry addresses so a later network decision is a deployment
choice rather than a commerce-model rewrite.

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

The deployed runtime bytecode hash matches the locally compiled contract. The
prepared record is deliberately not registered yet: the first write must be
part of the recorded registration, finalization, revocation, and recovery
drill against the hardened USD pilot shop. Contract source publication was not
completed, so explorer verification remains an operational evidence item.
Ethereum mainnet and Tempo production remain untouched.

On 2026-08-21, the reference indexer replayed deployment block `30731101`
through finalized block `31831769` (`0x8efe988fa5c66ebf7786c18d42833398e35e67de4a49e388ce0462313c179d78`).
The envelope was complete with no errors and projected one constructor
ownership event, zero merchant records, and zero revocations.

Chart version 0.3.0 packages the recurring indexer runtime and its restricted
egress policy. The pilot values select the real Moderato deployment and RPC but
leave the feed disabled until the runtime image is published by digest. This
keeps the live revision truthful: it reports the testnet contract, but does not
advertise a feed that cannot yet refresh.

The exact recurring wrapper was also run once against Moderato and produced a
complete, zero-error snapshot through finalized block `31833475`
(`0x1c866d3afc58b44e5d8495c2bb1c64ce368b4ff3f22d86a74a97a7d68058b823`),
while enforcing the expected chain id and registry address.

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

Ethereum and Tempo should be evaluated against those gates. Registration bond,
validator stake, slashing, paid placement, and ranking remain out of scope for
the network decision.

## Consequences

- The team can exercise real finalized logs, controller proofs, revocation, and
  recovery without implying mainnet readiness.
- Pilot addresses and receipts are evidence, not stable production identifiers.
- A future production choice requires a new ADR and cannot silently reuse the
  pilot owner EOA.
- Merchant and buyer clients must display the chain, registry address, record
  status, and governance mode instead of reducing trust to a generic
  "onchain" badge.
