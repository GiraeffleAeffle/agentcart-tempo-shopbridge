# Tempo registry lifecycle and buyer discovery drill

- Recorded at: 2026-08-23T15:08Z
- Network: Tempo Moderato (`eip155:42431`)
- Contract: `0x0965961617c5B0898167AA4034C5511dB0EfcA07`
- Scope: trusted-operator testnet pilot; no production or mainnet write

## Identity and immutable records

- Domain: `woo-usd.agentcart.eu`
- Domain hash:
  `0x757e5cf2ae5081568a752174c129d18722f97677953263f5b3e908c0407ec9d6`
- Controller: `0x015f6aB1b682aEa664A1E4896f363ca3093e4591`
- Record id:
  `0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b`
- First record hash:
  `460a16a43eb69734cd21b0554d4521ee59fb551bb305880dd7aeaf7742c26bef`
- Recovered record hash:
  `c8236a74b9d936065e3283c719f421312f4681e6d5015294f268526c6f702a66`

Both content-addressed records remain available under
`https://registry.agentcart.eu/v1/registry/onchain/records/<hash>`, and each
document independently hashes to its URL hash. The merchant revocation
document permanently lists the first hash; its current controller-bound domain
proof and bundle bind the recovered hash.

## Finalized lifecycle

| Transition | Transaction | Block | Block hash |
| --- | --- | ---: | --- |
| Register first hash | `0x13f10d4a46c16b67709c7aea409faef3a3b666811e063b7c8ff6f760d92e0769` | 32136514 | `0x2cf1af3911624c0a21514901d55c1891c8ecf1affe5dae3579b00f29ecaa1eb5` |
| Revoke first hash | `0x785cd582d7c77b025e284ed104b103f987a00519f6c8918215d7a8470d1f325a` | 32137027 | `0x44e13cefba3ab22216bccba253eb30902f765e9ef0af1d81eb97b880ad0a75f2` |
| Register recovered hash | `0x995de9a5b0f0c3774e164917d01287fb32e95499c8f6c50614637dc91eb3c060` | 32137803 | `0x0b880d00c7d8eccb7e28438196bab2d7adea2e9db38034145a6c861886463e09` |

The revoke reason hash is
`0xbbbbf62c8c3ec5672ced163e4ba0783bb5d0ab9661f88fef3c51861d8564d87f`.
Final state is active on the recovered hash. The contract is unpaused.

## Direct Skill behavior

The packaged `shopbridge-direct` skill was exercised with no registry
environment variables:

```json
{"command":"doctor","args":{"verify_merchants":true}}
{"command":"resolve_merchant","args":{"merchant_id":"woocommerce-demo-shop-usd"}}
```

After the first registration finalized, `doctor` returned two records and the
USD merchant verified. After onchain revocation finalized, the same merchant
was absent from the eligible set even before its HTTPS revocation document was
updated, isolating onchain enforcement. After recovery finalized, `doctor`
again returned two verified records, and `resolve_merchant` returned
`registry_record_hash=c8236a74...f702a66`, the exact merchant origin, and the
ShopBridge, MPP, signed-request, and registry profiles with `ok=true`.

The final live run at 2026-08-23T15:07Z reported `record_count=2`, checked both
merchant proofs with zero errors, and resolved the USD merchant as `verified`.

## Independent reconstruction

The hosted feed, dRPC, and Tenderly were each indexed independently from
deployment block `30731101` through their respective public RPC `finalized`
block. All three outputs were complete, had zero errors, and contained the
same four-event sequence:

`OwnershipTransferred`, `MerchantRegistered`, `MerchantRevoked`,
`MerchantRegistered`.

| Path | Finalized block captured | Complete | Errors |
| --- | ---: | --- | ---: |
| Hosted registry | 32138528 | yes | 0 |
| dRPC | 32138688 | yes | 0 |
| Tenderly | 32138796 | yes | 0 |

Canonicalizing only `.events` with `jq -cS` produced the same SHA-256 on every
path:

`f5322c1cd41d6e1bf34c28604b10fc97f6801ae4793d575a3ef4c343170440c0`

The Conduit public RPC reported chain id 42431 but could not replay from the
deployment block because its retained history began at block 32100000. The
indexer failed closed rather than publishing a partial reconstruction. dRPC
and Tenderly supplied the required independent full-history results; Conduit's
pruning remains a provider-selection constraint, not a lifecycle divergence.

## Remaining promotion gates

This completes the reversible testnet lifecycle and independent manual
reconstruction. A follow-up chart change packages automatic fail-closed
cross-RPC comparison and throttled firing/resolved webhook events, but this
evidence does not claim live witness or alert delivery. It also does not provide
a contract security review, production governance, a non-maintainer buyer
session, an external merchant session, or approval for Ethereum/Tempo mainnet.
