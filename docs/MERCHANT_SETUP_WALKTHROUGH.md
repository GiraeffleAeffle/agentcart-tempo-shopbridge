# Non-Maintainer Merchant Setup Walkthrough

Status: required human-in-the-loop evidence for external beta.

This walkthrough is the evidence protocol for GitHub issue #20. It must be run
by someone who is not the repo maintainer. A repo maintainer may observe and
record timestamps, but every place where the operator needs maintainer help must
be written down as a setup blocker.

Expected pilot evidence file:

```text
pilot/pilot-merchant-onboarding/non_maintainer_setup_walkthrough_notes.md
```

## Roles

- Operator: non-maintainer running the setup from published docs.
- Observer: records friction, timestamps, screenshots, and exact help given.
- Release owner: turns unresolved blockers into follow-up GitHub issues.

The operator should start from `woocommerce-shopbridge/README.md#merchant-setup`
and should not read source code unless the setup docs explicitly send them
there.

## Prerequisites

Prepare these before starting the clock:

- a staging WordPress admin account with WooCommerce installed;
- a staging domain or tunnel that can serve WordPress public URLs;
- `dist/agentcart-shopbridge.zip` from a release, PR artifact, or local package
  command;
- a support email, returns URL, and terms URL for the staging merchant;
- at least one simple in-stock WooCommerce test product;
- either sandbox verifier credentials or an explicit decision to use local
  trusted-token mode for the walkthrough only;
- a blank evidence file at the expected path above.

If any prerequisite is missing or unclear to the operator, record it as setup
friction before the walkthrough begins.

## Walkthrough Steps

The operator completes these steps without repo-maintainer intervention unless
blocked:

1. Install `AgentCart ShopBridge` from the ZIP with WordPress admin's
   `Plugins -> Add New -> Upload Plugin` flow.
2. Open `WooCommerce -> AgentCart`.
3. Configure merchant id, support email, returns URL, terms URL, checkout mode,
   verifier or trusted-token setting, and signed request mode.
4. Configure WooCommerce tax, shipping, and allowed shipping countries for the
   test product.
5. Choose a product exposure mode and expose the intended staging product.
6. Use the AgentCart setup checklist to confirm readiness state.
7. Save or screenshot the AgentCart settings readiness snapshot.
8. Save or screenshot the product exposure preview/catalog snapshot.
9. Run the sandbox quote check from the WordPress admin page.
10. Run the approval-bound sandbox checkout test from the WordPress admin page.
11. Refresh registry metadata and save the registry bundle URL or hosted
    registry submission result.
12. Run the live smoke from a terminal against the staging shop:

```sh
python3 scripts/woocommerce-shopbridge-smoke.py \
  --base-url https://staging-shop.example \
  --require-shipping \
  --require-vat-lines
```

The walkthrough passes only when the operator reaches a configured staging
ShopBridge install and can point to the evidence artifacts for each pilot
merchant-onboarding requirement.

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
- Checkout mode:
- Payment/verifier mode:
- Result: passed | blocked | partial

## Setup Path

- Starting doc:
- WordPress/WooCommerce version:
- ShopBridge plugin version:
- Product exposure mode:
- Registry result:
- Live smoke command:
- Live smoke result:

## Evidence Links

- Settings readiness snapshot:
- Catalog preview/export:
- Sandbox quote check:
- Sandbox checkout test:
- Live WooCommerce smoke:
- Registry record or bundle URL:

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
