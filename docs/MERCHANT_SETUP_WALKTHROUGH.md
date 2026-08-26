# Non-Maintainer Merchant Setup Walkthrough

Status: required human-in-the-loop evidence for external beta.

This walkthrough is the evidence protocol for GitHub issue #20. It must be run
by a merchant operator who is not the repo maintainer. The merchant path uses
WordPress admin and, for onchain enrollment, the merchant's external controller
wallet. The observer owns every repository-local smoke and enrollment command.
Every place where the merchant needs undocumented maintainer help must be
written down as a setup blocker.

Expected pilot evidence file:

```text
pilot/pilot-merchant-onboarding/non_maintainer_setup_walkthrough_notes.md
```

## Roles

- Merchant operator: non-maintainer installing and configuring ShopBridge in
  WordPress admin and approving the reviewed testnet registry transaction.
- Observer: records friction, timestamps, screenshots, and exact help given;
  runs the repository-local smoke and registry CLI.
- Release owner: turns unresolved blockers into follow-up GitHub issues.

The merchant operator should start from
`woocommerce-shopbridge/README.md#merchant-setup` and should not need the
repository, a terminal, Node.js, Python, raw hashes, or calldata. If the
merchant must use any of those to finish setup, record a blocker.

## Prerequisites

Prepare these before starting the clock:

- a staging WordPress admin account with WooCommerce installed;
- a staging domain or tunnel that can serve WordPress public URLs;
- the exact `agentcart-shopbridge.zip` from the published pilot release or
  approved CI artifact, with its source and checksum recorded by the observer;
- a support email, returns URL, and terms URL for the staging merchant;
- at least one simple in-stock WooCommerce test product;
- either sandbox verifier credentials or an explicit decision to use local
  trusted-token mode for the walkthrough only;
- a merchant-controlled external EVM wallet, its public controller address,
  and enough Tempo Moderato testnet gas for supervised onchain enrollment;
- an observer checkout of this repository with the gateway dependencies
  installed; and
- a blank evidence file at the expected path above.

If any prerequisite is missing or unclear to the operator, record it as setup
friction before the walkthrough begins.

## Walkthrough Steps

The owner of each step is explicit. The merchant completes WordPress and wallet
actions without repo-maintainer intervention unless blocked; the observer runs
all repository-local commands.

1. **Merchant:** Install `AgentCart ShopBridge` from the ZIP with WordPress admin's
   `Plugins -> Add New -> Upload Plugin` flow.
2. **Merchant:** Open `WooCommerce -> AgentCart`.
3. **Merchant:** Configure merchant id, support email, returns URL, terms URL, checkout mode,
   verifier or trusted-token setting, and signed request mode.
4. **Merchant:** Configure WooCommerce tax, shipping, and allowed shipping countries for the
   test product.
5. **Merchant:** Choose a product exposure mode and expose the intended staging product.
6. **Merchant:** Use the AgentCart setup checklist to confirm the current
   readiness state. Onchain discovery is expected to remain not finalized at
   this point.
7. **Merchant:** Save or screenshot the AgentCart settings readiness snapshot.
8. **Merchant:** Save or screenshot the product exposure preview/catalog snapshot.
9. **Merchant:** Run the sandbox quote check from the WordPress admin page.
10. **Merchant:** Run the approval-bound sandbox checkout test from the WordPress
    admin page. Record it as an admin dry run: it exercises the ShopBridge and
    WooCommerce quote/order path, creates and cancels a test order, and does not
    call the live payment verifier or prove testnet settlement.
11. **Merchant:** Refresh registry metadata, run the public endpoint check, and
    give the observer the public registry bundle URL. A hosted registry
    submission is optional and is not onchain-registration evidence.
12. **Observer:** Run the live smoke against the staging shop from the repository
    root:

```sh
python3 scripts/woocommerce-shopbridge-smoke.py \
  --base-url https://staging-shop.example \
  --require-shipping \
  --require-vat-lines
```

13. **Observer:** Follow
    [Merchant Onchain Enrollment](MERCHANT_ONCHAIN_ENROLLMENT.md). Run the first
    read-only `prepare` call with the public bundle URL and controller address.
    Give the merchant only the returned public WordPress settings.
14. **Merchant:** Save the four fields under `WooCommerce -> AgentCart`: public
    controller address, CAIP-2 registry chain, registry contract, and registry
    record id. Refresh registry metadata and rerun the public endpoint check.
    Never enter a private key, seed phrase, wallet session, or signature.
15. **Observer:** Run the second `prepare`, write a new retained plan file, and
    review its chain, contract, controller, domain, hash, immutable URI,
    transaction value, operation, 30-minute expiry, intent hash, finalized
    state precondition, and exact acknowledgement with the merchant.
16. **Merchant:** Submit the plan's `eth_sendTransaction` request from the
    controller account in the external wallet. The isolated repo-local signer
    is a supervised fallback, not the normal merchant path.
17. **Observer:** Run `verify --transaction-hash 0x... --expected-state active`
    until the exact transaction and record are `finalized_current`.
    **Merchant:** select **Check registry health** and confirm the plugin's
    pinned direct Tempo RPC check also reports all reads at one canonical
    finalized block hash, with the normalized shop domain and deterministic
    controller-bound record id. This result trusts the pinned Tempo RPC. A
    hosted indexer snapshot alone must remain diagnostic rather than readiness
    proof.
18. **Observer:** Run fresh Direct Skill discovery without cached registry data
    and record whether the merchant appears. Do not perform checkout without a
    fresh financially consistent quote, complete delivery address, and explicit
    buyer approval.

The walkthrough passes only when the merchant reaches a configured staging
ShopBridge install without repository tooling, the observer can point to the
evidence artifacts for each pilot merchant-onboarding requirement, and no P0
blocker remains open. This is supervised testnet evidence, not a claim that the
flow is self-service or production-ready.

## Maintainer Help Log

Every interruption goes into the evidence file, even when the final setup
succeeds:

```text
## Maintainer Help Log

| Time | Step | What the operator tried | Help needed | Root cause | Follow-up issue |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | TODO | TODO |
```

Classify each item:

- `P0`: blocks setup or could cause unsafe payment, product, or privacy state.
- `P1`: setup can finish only with maintainer knowledge or undocumented command.
- `P2`: confusing wording, missing screenshot, or avoidable extra work.

## Evidence Template

Use this structure for
`pilot/pilot-merchant-onboarding/non_maintainer_setup_walkthrough_notes.md`:

```markdown
# Non-Maintainer Merchant Setup Walkthrough Notes

- Operator:
- Observer:
- Merchant/staging URL:
- Started at:
- Finished at:
- Plugin ZIP source:
- Plugin ZIP checksum:
- Checkout mode:
- Payment/verifier mode:
- Registry controller address:
- Registry deployment: tempo-moderato
- Result: passed | blocked | partial

## Setup Path

- Starting doc:
- WordPress/WooCommerce version:
- ShopBridge plugin version:
- Product exposure mode:
- Registry phase 1 result:
- Registry phase 2 result:
- Finalized verification result:
- WordPress onchain readiness result:
- Live smoke command:
- Live smoke result:

## Evidence Links

- Settings readiness snapshot:
- Catalog preview/export:
- Sandbox quote check:
- Sandbox checkout test:
- Live WooCommerce smoke:
- Registry bundle URL:
- Immutable registry record URL:
- Retained enrollment plan:
- Wallet transaction hash:
- Finalized block number/hash:
- Fresh Direct Skill discovery:

## Maintainer Help Log

| Time | Step | What the operator tried | Help needed | Root cause | Follow-up issue |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | TODO | TODO |

## Remaining Blockers

| Severity | Title | Follow-up issue | Notes |
| --- | --- | --- | --- |
| TODO | TODO | TODO | TODO |
```

## Follow-Up Issues

For every remaining blocker, create a GitHub issue with the severity in the
title or body:

```sh
gh issue create \
  --title "[merchant setup][P1] Replace with blocker title" \
  --body "Observed during non-maintainer merchant setup walkthrough.

Severity: P1
Step: TODO
Operator expected: TODO
Actual result: TODO
Suggested fix: TODO"
```

Record the issue URL in the walkthrough notes. The external beta go/no-go
decision should not proceed while any `P0` walkthrough blocker remains open.
Ethereum mainnet, Gnosis mainnet, and Tempo production enrollment remain
separately blocked even when this supervised Tempo Moderato walkthrough passes.
