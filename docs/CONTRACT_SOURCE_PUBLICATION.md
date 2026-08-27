# Tempo Contract Source Publication

Date checked: 2026-08-27

Tempo's Sourcify-compatible verifier publicly returns the complete source set
for both Moderato pilot contracts:

| Contract | Address | Verifier result | Published files |
| --- | --- | --- | --- |
| Merchant Registry | `0x0965961617c5B0898167AA4034C5511dB0EfcA07` | `exact_match`; runtime `exact_match` | `AgentCartMerchantRegistry.sol`, `IAgentCartMerchantRegistry.sol` |
| Discovery Facets | `0x693de216d208ADC933365bD6F4FCbC062BB8Afe5` | `exact_match`; runtime `exact_match` | `AgentCartMerchantDiscoveryFacets.sol`, `IAgentCartMerchantDiscoveryFacets.sol`, `IAgentCartMerchantRegistry.sol` |

The guarded GitHub workflow pins chain id 42431, both addresses and creation
transactions, compiler `0.8.28+commit.7893614a`, optimizer 200, Prague EVM,
metadata settings, identifiers, and complete import sets. A rerun accepts HTTP
409 only when the verifier says `already_verified`, then independently retrieves
the contract and requires its overall and runtime results to be `exact_match`.
The retrieved source maps must match the checked-out files byte-for-byte, and
the compiler version/settings, fully qualified identifier, and creation
transaction must match the pinned publication payload. Thus an older unrelated
verification cannot make an idempotent workflow rerun pass.

Public verifier records:

- `https://contracts.tempo.xyz/v2/contract/42431/0x0965961617c5B0898167AA4034C5511dB0EfcA07?fields=all`
- `https://contracts.tempo.xyz/v2/contract/42431/0x693de216d208ADC933365bD6F4FCbC062BB8Afe5?fields=all`

The sanitized machine-readable capture, including SHA-256 values for every
published source file, is
`docs/examples/pilot-evidence/tempo-source-verification-2026-08-27.json`.
Guarded workflow run `33108166297` passed on the reviewed PR branch.

Source publication makes review possible; it is not a security audit or a
production endorsement.
