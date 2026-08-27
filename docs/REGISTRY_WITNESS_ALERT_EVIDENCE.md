# Registry Independent-Witness And Alert Evidence

Date: 2026-08-27

## Live matched reconstruction

The Talos `shopbridge-registry` release was upgraded atomically with:

- primary: Tempo's public Moderato RPC;
- witness: independently operated Tenderly public Moderato RPC;
- registry: `0x0965961617c5B0898167AA4034C5511dB0EfcA07`;
- deployment block: `30731101`;
- maximum finalized-time lag: 300 seconds.

The public snapshot at
`https://registry.agentcart.eu/v1/registry/onchain/events` reported:

| Field | Value |
| --- | --- |
| Completeness authority | `independently_verified` |
| Status | `matched` |
| Common finalized block | `32732792` |
| Common event count | 9 |
| Canonical events SHA-256 | `ae32e72caab65941ed7da29bbab33f84916991aae7fadf9ecb9faea07c738cdd` |
| Primary finalized block | `32732792` |
| Witness finalized block | `32732849` |
| Finalized-time lag | 35 seconds |
| Checked at | `2026-08-27T18:48:04Z` |

Both paths agreed on chain, registry, and canonical event history. The hosted
snapshot contains no RPC URL and publishes only through the common matched
finalized block.

## Authenticated delivery drill

An authenticated receiver was deployed at
`registry-alerts.staging.agentcart.eu`. It runs without a service-account token,
with a read-only root filesystem, no Linux capabilities, a default-deny egress
policy, an exact ingress path, a Secret-backed bearer token, a 64 KiB body
limit, and strict schema/chain/registry validation.

The controlled drill invoked the exported alert sender inside the live
`finalized-registry-indexer` container. This used the actual mounted webhook URL
and token and traversed the pod NetworkPolicy, public TLS ingress, receiver
authentication, schema validation, and receiver logging. It did not fabricate a
chain divergence and is therefore delivery evidence, not divergence-detection
evidence.

At `2026-08-27T18:49:21Z` the sender received HTTP 204 for both:

- `firing`, critical, code `registry_witness_delivery_drill`;
- `resolved`, info, code `registry_witness_delivery_drill`.

The receiver logged both events with chain `eip155:42431`, the exact registry
address, and witness `tenderly-public-moderato`. No RPC URL, bearer token, or
other secret appeared in either payload or retained evidence.

## Remaining production boundary

The pilot now has matched reconstruction and end-to-end firing/resolved delivery
evidence. Production still requires a durable external paging/incident system,
a secondary delivery route, an actual controlled divergence/outage exercise,
and an operator response-time record. A synthetic delivery drill does not prove
that humans will act on a real incident.
