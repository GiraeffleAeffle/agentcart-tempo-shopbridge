# Multi-Shop On-Chain Ranking Test

Date: 2026-08-27

Rerun: 2026-10-11 with five shops; see the last section.

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

## 2026-10-11: Five-Shop Rerun

All five shops ran release 1.25.2 on the same Talos cluster: chart, plugin and
verifier image
`sha256:03811e569f3a6678972859ef8b38bb5f6b9cae01ff97bd09b908983243739159`.
The scope is the same as above: a read-only buyer comparison, with no payment
or order.

### Shops

| Shop | Seed profile | Currency | Verifier rails | Declared categories |
| --- | --- | --- | --- | --- |
| `value-shop.staging.agentcart.eu` | `ranking-value-usd` | USD | Tempo MPP, x402 | coffee, household, personal-care, tea |
| `premium-shop.staging.agentcart.eu` | `ranking-premium-usd` | USD | Tempo MPP | coffee, household, personal-care, tea |
| `coffee-shop.staging.agentcart.eu` | `ranking-coffee-usd` | USD | Tempo MPP | coffee |
| `restricted-shop.staging.agentcart.eu` | `restricted-stock-policy` | USD | Tempo MPP | coffee, household, tea |
| `eur-shop.staging.agentcart.eu` | `baseline-eu-tax-shipping` | EUR | Stripe/card MPP (sandbox) | coffee, household, personal-care, tea |

The value and premium records were unchanged by the 1.25.1 and 1.25.2
upgrades, so they needed no new transactions. The three new shops were
registered and their categories published by the registry controller through
the supervised isolated-signer fallback. Every write was verified at finality:

| Shop | Transaction | Block |
| --- | --- | ---: |
| coffee-shop register | `0xb71337c2c1d74e1c2b8ebbf6a0977d9d486d6bfc7ee70a558116928799c7439d` | 39,111,411 |
| coffee-shop categories | `0x48cf5ca5a84764ea4ddc3fe99059c2a74155b7d73555b4ff17dc2e260070cc9d` | 39,111,422 |
| restricted-shop register | `0xf68c9d1d41ea190684c4bbda8e0b50b0674f296350da36437af7306c14bbb258` | 39,111,435 |
| restricted-shop categories | `0xe45a4582a7f3b1c7b6344e1226d8be1648610201043ae6029893aac73b34d4a0` | 39,111,446 |
| eur-shop register | `0x2f4dc71f0cd00d64ad2c411c5b4e31cf83707472436fcfd3146056a2a112fe69` | 39,111,460 |
| eur-shop categories | `0x4a94d194193c81d7c2c77d730ed7f5c969dde9096bdf30145f8663cc62ea8b2a` | 39,111,471 |
| eur-shop update (adds its Stripe profile) | `0x0cbd6c695b54031bee302d6d03e90a56ec787f640fb133e4933ad613ff642880` | 39,116,661 |
| eur-shop categories | `0xd4f6132c6bec94c9eeba840290a3c6c3a508cccac5bb94e1a949bff59bc2fe0e` | 39,116,672 |

### Buyer results

Every run used the public Direct Skill with its defaults: no base URL, no
hosted registry, quantity 1, ranked by final total. Each run contacted all five
registered shops before catalog access.

| Query | Ship to | Rail | Ranked offers | Rejected |
| --- | --- | --- | --- | --- |
| tea | US 10001 | Tempo MPP | Value $12.17, Premium $16.07 | restricted, EUR: merchant does not ship to US |
| coffee | US 10001 | Tempo MPP | Coffee $15.98, Premium $17.70, Value $18.70, Restricted $19.70 | EUR: merchant does not ship to US |
| tea | DE 10115 | Stripe/card MPP | EUR Tea Shop €14.80 | value, premium: merchant does not ship to DE; restricted: quote request failed |
| tea | US 10001 | x402 | Value $12.17 | premium: payment_rail_unavailable; restricted, EUR: merchant does not ship to US |

### Findings

1. **Stripe/card on chart-deployed shops (fixed in 1.25.2).** The chart gave
   `STRIPE_PROFILE_ID` to the verifier but not to WordPress. The EUR shop's
   quotes therefore listed `stripe-card-mpp` as unavailable, without a reason.
   Release 1.25.2 passes the key to the storefront seed, and the same query
   then ranked the EUR shop.
2. **Categories order candidates; they exclude shops only in larger
   registries.** The skill contacts up to 12 shops by default
   (`SHOPBRIDGE_ONCHAIN_RECORD_CANDIDATE_LIMIT`, maximum 50):
   - category matches first;
   - then one reserved slot for a non-matching shop, so self-declared
     categories cannot hide a merchant;
   - then the remaining shops, up to the limit.

   With five registered shops, every query contacted all five. The coffee
   shop received the tea queries through the reserved slot and returned no tea
   offer. Category routing reduces requests only once more shops are
   registered than the limit.
3. **Delivery time cannot break ties.** Ranking sorts by final total, then
   latest delivery. However, the plugin quotes a fixed "2-4 business days" for
   every shop, so merchants cannot state their own delivery time and the tie
   break never distinguishes shops.
4. **Generic error for a contradictory shop setup.** The restricted shop allows
   tea to DE and AT at product level, but its USD store ships only to the US. A
   DE quote therefore fails, and the skill reports "quote request failed"
   instead of a shipping reason.
