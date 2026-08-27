# Multi-Shop On-Chain Ranking Test

Date: 2026-08-27

Network: Tempo Moderato (`eip155:42431`)

Scope: read-only buyer comparison after supervised testnet enrollment; no
payment or order was attempted.

## Purpose

Prove that a buyer agent can discover several relevant shops from contracts,
ask every eligible shop for a quote, and choose the best result without using
the AgentCart-hosted registry API as its discovery source.

The on-chain Merchant Registry stores active merchant identity and the hash of
the current immutable merchant record. The on-chain Discovery Facets contract
stores bounded category commitments and indexed category declarations. Product
images, descriptions, prices, stock, tax, and shipping remain off-chain at the
merchant because they are mutable commerce data, not registry data.

## Contracts

| Role | Address | Deployment block |
| --- | --- | ---: |
| Merchant membership and record lifecycle | `0x0965961617c5B0898167AA4034C5511dB0EfcA07` | 30,731,101 |
| Category routing declarations | `0x693de216d208ADC933365bD6F4FCbC062BB8Afe5` | 32,721,088 |

`registry.agentcart.eu` was not configured or called by the Direct Skill. That
hostname serves an OCI container-image registry and legacy compatibility and
diagnostic routes; it is not either smart contract.

## Test Merchants

| Shop | Record id | Current record hash | Category generation |
| --- | --- | --- | ---: |
| Value Tea Shop | `0xd0e6751a8cf024b48a1700e9e512b1f493e9749689a4f42b813316a25c1c8088` | `0x3266cbb441dbd2fab38cff8b98641718fe1ee496bccc12be64d8da6f4c9a4652` | 2 |
| USD Tempo Demo Shop | `0xc6a2be430634e0d8fa335a15bf2b0696573c83c5d218c0bad8831be7d9b85a5b` | `0x6947c68eb613692d1fcb096ae8c330c27683aeacc79d674d2c3d7e9e75930690` | 1 |
| Premium Tea Shop | `0x3abb01f3136a807d7e1792e01ab1dcc2ffcfa597804884a78ec2f859d5dd46e3` | `0x70e5df326ba6f2bf85de51f4ec852120d227bf3c4e365e7a1296a7a3f5ce2ac8` | 2 |

The value and premium record updates finalized in transactions
`0x6b6471dc3a0dbb459cd66d0b9a916c1075381078f795f186dc21b59f0ff55492`
at block 32,727,088 and
`0xe74226f7ad2e106c76da76d99b9b4a6b8ca68e9bb69d374db2de814b91cda14c`
at block 32,727,099.

Their replacement category generations finalized in transactions
`0x5128c785fdd25bb1a53bbf43c11431f880189091da7035f3675bf643d334b8e0`
at block 32,727,151 and
`0xeaa79a3eba8eeab8f594eb8a9f8e4ece4de6a88d487f62c13c752aa54b2cfae3`
at block 32,727,157. Both declared four categories with category-set hash
`0xe648d43ccd9092bb0c2bf1e272fd07c0b0c962179d596f58155d7070597eb408`.

## Live Buyer Result

Input: `tea`, quantity 1, ship to US 10001, Tempo MPP, rank by final total.

| Rank | Shop | Item total | Shipping | Final total |
| ---: | --- | ---: | ---: | ---: |
| 1 | AgentCart Value Tea Shop | $8.17 | $4.00 | **$12.17** |
| 2 | AgentCart USD Tempo Demo Shop | $10.78 | $5.00 | $15.78 |
| 3 | AgentCart Premium Tea Shop | $13.07 | $3.00 | $16.07 |

The candidate-selection evidence reported:

- eligible on-chain pool: 3;
- on-chain `tea` facet matches: 3;
- selected merchants: 3;
- neutral fallbacks: 0;
- rejected merchants: 0;
- paid-placement signal: false.

All record commitments matched contract storage, all three domain proofs passed,
all quotes reconciled subtotal, shipping, tax, and total, and all candidates
advertised an external Tempo MPP verifier. The winner was selected locally by
the buyer skill. The comparison used only country and postal code, so the skill
correctly stopped with `incomplete_delivery_address` before approval, payment,
or checkout.

## Merchant Installation Finding

Deploying the two fresh shops exposed a Helm packaging omission: the
Discovery Facets plugin file existed in chart files but was absent from the
generated ConfigMap and rollout checksum. The chart and regression check now
include it. This was an installation defect, not an on-chain discovery defect,
and the multi-shop rehearsal caught it before external merchant testing.
