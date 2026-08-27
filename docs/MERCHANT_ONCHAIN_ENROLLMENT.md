# Merchant Onchain Enrollment

Status: supervised Tempo Moderato pilot only. This is not a production or
mainnet enrollment flow.

This runbook registers a ShopBridge merchant in the onchain registry without
putting a wallet secret in WordPress. The merchant uses WordPress admin and an
external controller wallet. A pilot observer runs the repository-local
preparation and verification commands.

## Authority Boundaries

- **WordPress / ShopBridge** publishes the merchant metadata, public onchain
  identity, and content-addressed Registry Record snapshots.
- **Registry Controller** is the public wallet address authorized to register,
  update, and revoke the merchant record and publish its coarse on-chain
  categories. Its external wallet approves and signs those transactions.
- **Pilot observer** prepares a secret-free transaction plan, records evidence,
  and verifies exact state at an RPC `finalized` block.
- **Compatibility services** may cache and monitor registry data. They do not
  supply membership or category routing to the normal buyer path.

The Registry Controller, merchant payment recipient, and buyer payment wallet
are different roles. They may be controlled by the same person during a pilot,
but they must not be treated as the same credential or authority.

Never paste a private key, seed phrase, wallet session, or signature into
WordPress, the Registry connection token field, a support bundle, an enrollment
plan, or a chat. The plugin stores public addresses and identifiers only.

## Pilot Prerequisites

The merchant needs:

- the pilot ShopBridge ZIP installed on a public HTTPS staging shop;
- `manage_woocommerce` access to `WooCommerce -> AgentCart`;
- stable merchant, support, product, shipping, and testnet payment settings;
- a compatible external EVM wallet whose public controller address the
  merchant controls; and
- enough Tempo Moderato testnet gas for the registry transaction.

The observer needs a checkout of this repository with the `gateway` JavaScript
dependencies installed. The normal merchant journey does not require the
merchant to clone the repository, run Node.js, calculate hashes, or handle
calldata.

The only supported deployment descriptor in this flow is `tempo-moderato`:

- chain: `eip155:42431`;
- registry contract: `0x0965961617c5b0898167aa4034c5511db0efca07`;
- discovery facets contract: `0x693de216d208ADC933365bD6F4FCbC062BB8Afe5`;
- network class: testnet.

Ethereum mainnet, Gnosis mainnet, and Tempo production enrollment remain
blocked pending the production-network governance, verifier, archive, and
independent-review gates. The operator intentionally exposes no free-form
register, update, or revoke command and accepts only pinned deployment
descriptors.

## Phase 1: Derive The Public WordPress Identity

First, the merchant completes the normal ShopBridge settings, refreshes
registry metadata, and checks the public endpoints in `WooCommerce ->
AgentCart`. The observer then runs:

```sh
cd gateway
node scripts/onchain-registry-operator.mjs prepare \
  --deployment tempo-moderato \
  --bundle-url https://shop.example/.well-known/agentcart-registry-bundle.json \
  --controller 0xPUBLIC_CONTROLLER_ADDRESS
```

This first call is read-only. It verifies the pinned deployment and finalized
RPC view, derives the domain hash and deterministic record id, and should return
`state: store_identity_required` plus four `wordpress_settings` values:

| CLI field | WordPress field |
| --- | --- |
| `controller` | Public controller address |
| `chain_id` | Onchain registry chain |
| `registry_address` | Onchain registry contract |
| `record_id` | Onchain registry record id |

The merchant copies those four public values into `WooCommerce -> AgentCart`
and saves the settings. If deployment constants lock a field, the deployment
owner must set the corresponding public `AGENTCART_REGISTRY_ONCHAIN_*` constant
instead. Constants and WordPress options must never contain wallet secrets.

Saving the public identity intentionally changes the canonical Registry Record
hash. The merchant then selects **Refresh registry metadata** and **Check public
registry endpoints** again. The refreshed bundle must expose a
content-addressed record URI in this form:

```text
https://shop.example/.well-known/agentcart-registry-records/<sha256>.json
```

ShopBridge keeps each generated record under its hash rather than rewriting an
old URI when merchant metadata changes. That archive lives in WordPress plugin
storage: disabling the plugin makes the route unavailable and uninstalling the
plugin removes the archive. A separately operated append-only archive is still
required before production.

## Phase 2: Prepare And Retain The Transaction Plan

The observer reruns the same preparation against the refreshed bundle and saves
the result to a new file:

```sh
cd gateway
node scripts/onchain-registry-operator.mjs prepare \
  --deployment tempo-moderato \
  --bundle-url https://shop.example/.well-known/agentcart-registry-bundle.json \
  --controller 0xPUBLIC_CONTROLLER_ADDRESS \
  --output merchant-enrollment-plan.json
```

Preparation fetches and re-hashes the immutable merchant record, checks the
four public identity values, reads contract state at `finalized`, chooses
`register` or `update`, and simulates the write. A new registration returns
`state: ready_to_register`; a changed active record returns
`state: ready_to_update`. If the exact record is already current, it returns
`state: finalized_current` and no transaction is needed.

The saved plan contains public identity, record, chain snapshot, state
precondition, calldata, `intent_hash`, `wallet_request`, and `required_ack`
fields. It contains no private key or signature. The plan expires after 30
minutes. Its acknowledgement commits to the exact deployment, operation,
controller, domain, record hash and URI, calldata, finalized precondition, and
expiry. Prepare a new plan instead of extending or editing it. Retain every
plan in the pilot evidence store: it is the review record for the write and can
be used to prepare an onchain revocation even if the shop later becomes
unavailable. The command creates output files without overwriting an existing
file, so use a new filename for every attempt.

## Review And Sign In The External Wallet

External-wallet approval is the primary path. Before signing, the merchant and
observer compare the plan against the intended:

- operation (`register` or `update`);
- Tempo Moderato chain and pinned registry contract;
- merchant domain and controller address;
- deterministic record id;
- exact record hash and merchant-hosted immutable record URI; and
- zero transaction value.

The merchant sends the plan's exact `wallet_request` using a compatible wallet
or supervised wallet adapter and approves it from the controller account. Do
not submit after `expires_at`, and do not manually reconstruct or edit the
calldata. A generic wallet cannot enforce the offchain expiry or precondition;
the observer must refresh the plan immediately before handoff. If the selected wallet cannot
accept or faithfully display the request, record that as pilot friction and use
the isolated fallback only with the merchant's explicit agreement. Record the
merchant's exact `required_ack` string and the wallet transaction hash next to
the retained plan; a generic "yes" is not sufficient transaction evidence.
Reject the request if the wallet shows a different chain, sender, contract,
value, or calldata.

For a supervised pilot only, an operator may use the isolated signer fallback:

1. inject `AGENTCART_ONCHAIN_PRIVATE_KEY` into a short-lived operator shell from
   an approved secret manager, never as a command-line argument or WordPress
   value;
2. set `AGENTCART_ONCHAIN_ACK` to the plan's exact `required_ack`; and
3. from `gateway`, run `node scripts/onchain-registry-operator.mjs execute
   --plan merchant-enrollment-plan.json`.

`execute` rejects an expired or changed plan and a signer that is not the
controller. Immediately before signing it re-verifies the pinned deployment
runtime and creation boundary, freshness of the finalized head, current domain
mapping/status/hash precondition, deterministic record id, and the immutable
merchant record. It then re-simulates the exact transaction. Immediately after
broadcast it writes a mode-0600 submission journal next to the plan, preserving
the transaction hash even if receipt/finality verification later fails. Never
blindly retry `submitted_unverified`; use the retained plan and hash with
`verify`. This fallback is not a general custodial service or the production
merchant path. Remove the injected secret from the isolated environment when
the supervised action is complete.

Run only one pending write per controller. The current testnet contract does
not expose an atomic `expectedCurrentHash` mutation, so the finalized
precondition plus last-moment simulation closes ordinary supervised-pilot
staleness but cannot eliminate a transaction-ordering race between concurrent
writes. A production successor contract must provide an atomic expected-state
guard.

## Verify Finalized Inclusion

A transaction hash or one mined confirmation is not sufficient. After an
external-wallet submission, the observer runs:

```sh
cd gateway
node scripts/onchain-registry-operator.mjs verify \
  --plan merchant-enrollment-plan.json \
  --transaction-hash 0xWALLET_TRANSACTION_HASH \
  --expected-state active
```

The enrollment passes only when verification returns `ready: true` and
`state: finalized_current`. Verification pins the deployment and checks the
transaction sender, target, zero value, exact calldata, canonical receipt,
controller, domain hash, record id, current record hash, active status,
revocation state, and finalized block identity. A state-only check is not
transaction evidence. A mismatch exits non-zero and must not be described as
registered or discoverable.

The merchant then selects **Check registry health** in WordPress. The admin page
may show **Finalized** only when the plugin captures a fresh finalized block
hash through its pinned, read-only Tempo RPC and pins every state read to it
with EIP-1898 `requireCanonical`. The check verifies the registry runtime and
creation boundary, Ethereum Keccak of the normalized shop hostname, the exact
active controller, controller-bound deterministic record id, domain mapping,
record hash, and non-revoked state. This removes dependence on the Hosted
Registry but still trusts the named Tempo RPC. Hosted health and event
documents are labeled operator snapshots; they can help diagnose the registry
but cannot confer canonical chain readiness. Local HTTPS proof or a successful
hosted bundle submission alone must remain **Not finalized**.

## Publish The On-chain Categories

Registration makes the merchant eligible; it does not yet make category lookup
efficient. Prepare the controller-bound category publication from the exact
retained enrollment plan and immutable Registry Record:

```sh
cd gateway
node scripts/onchain-discovery-facets-operator.mjs prepare \
  --enrollment-plan merchant-enrollment-plan.json \
  --output merchant-facets-plan.json
```

The operator reads the current record's canonical `discovery_facets.categories`,
hashes and sorts them for the contract, verifies the Facets contract is pinned
to the expected Merchant Registry, and simulates one `publish` transaction. It
returns `finalized_current` without a transaction when the same record and
category-set commitment are already current.

Review and submit the plan's exact `wallet_request` from the same Registry
Controller. The supervised signer fallback uses the same isolated-key and exact
acknowledgement rules as enrollment:

```sh
export AGENTCART_ONCHAIN_ACK='the exact required_ack from merchant-facets-plan.json'
node scripts/onchain-discovery-facets-operator.mjs execute \
  --plan merchant-facets-plan.json
```

For an external-wallet transaction, verify exact calldata and finalized state:

```sh
node scripts/onchain-discovery-facets-operator.mjs verify \
  --plan merchant-facets-plan.json \
  --transaction-hash 0xWALLET_TRANSACTION_HASH
```

The merchant is category-discoverable only after this returns
`state: finalized_current`. Every Registry Record update invalidates the prior
category generation, so repeat category publication after each update.

Finally, run fresh buyer discovery with no cached record and confirm that the
merchant appears through `onchain_discovery_facets.used=true` while
`hosted_discovery_index.configured=false`. This is discovery evidence, not
permission to create a paid order.

## Update A Merchant Record

Any stable merchant identity, payment, shipping, endpoint, or policy change can
produce a new record hash. To update safely:

1. review the change in WordPress, refresh registry metadata, and check the
   public endpoints;
2. run `prepare` again with the same controller and deployment, writing a new
   plan file;
3. require `state: ready_to_update`, review the new hash/URI and exact
   `required_ack`, then approve the external-wallet request;
4. run `verify --transaction-hash 0x... --expected-state active`; and
5. publish and verify the replacement on-chain categories; and
6. refresh WordPress registry health and fresh buyer discovery.

Do not remove the old content-addressed snapshot. Historical onchain events
commit to it, and discovery/audit reconstruction may still need it.

## Revoke From A Retained Plan

The WordPress **Send revocation request** action updates the merchant-hosted
revocation document and may notify a hosted registry. It does not revoke the
onchain contract record.

To prepare an onchain revocation from the last active retained plan:

```sh
cd gateway
node scripts/onchain-registry-operator.mjs prepare-revoke \
  --plan merchant-enrollment-plan.json \
  --reason merchant_admin_revoke \
  --output merchant-revoke-plan.json
```

Allowed pilot reasons are `merchant_admin_revoke`, `compromised_store`, and
`pilot_complete`. Review and submit the new plan's external `wallet_request`,
or use the same isolated `execute` fallback with its exact `required_ack`.
Because the retained plan contains the identity and committed record, revoke
preparation can continue even when the shop is offline.

Verify the result:

```sh
cd gateway
node scripts/onchain-registry-operator.mjs verify \
  --plan merchant-revoke-plan.json \
  --transaction-hash 0xWALLET_TRANSACTION_HASH \
  --expected-state revoked
```

The revoke drill passes only with `ready: true` and
`state: finalized_revoked`, followed by fresh buyer discovery that excludes the
merchant.

## Pilot Acceptance Criteria

- The merchant completed installation and configuration from WordPress admin;
  the observer, not the merchant, ran repository-local commands.
- WordPress contains exactly the four public onchain identity values and no
  wallet secret.
- Phase 1 returned `store_identity_required`; phase 2 returned an exact
  simulated plan or `finalized_current` for an already-current record.
- The saved plan and immutable record re-hash to the advertised value.
- The controller approved the reviewed external-wallet transaction, or the
  isolated supervised fallback used the exact acknowledgement.
- CLI verification proves the exact wallet transaction and WordPress's direct
  RPC health check reports the exact current record at finalized state.
- Fresh buyer discovery includes the merchant only after finality.
- The plan and all historical content-addressed snapshots are retained for the
  update/revoke and incident drills.
- Any request for a private key in WordPress, a support message, or an
  enrollment plan is recorded as a P0 blocker.
