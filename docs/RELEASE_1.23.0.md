# 1.23.0 release notes

This release follows v1.22.0 and targets supervised staging/testnet trials.
Publishing its source and packages does not deploy the Talos services or a
registry v2 contract. The remaining paid-launch gates are listed below.

## Changes

- Codex buyer configuration selects `gpt-6-astra` with the ShopBridge Direct
  Skill. ShopBridge services themselves do not call an AI model.
- Registry v2 adds quorum admission, entity identity, expiring approvals,
  bonded registration, delayed governance, evidence-bound slashing and appeal.
  The Direct Skill requires pinned deployment evidence and agreement from two
  independently operated finalized RPC sources. V1 remains the pilot registry.
- Quote comparison separates currencies, compares delivered prices in common
  units, keeps partial baskets distinct, and randomizes equal-price ties.
  Entity diversity limits sampling dominance. A low price is not a slashable
  offense; these rules do not establish protection against predatory pricing.
- Final quotes use WooCommerce's native stock reservations in hard mode.
  Comparison quotes do not reserve inventory. Ordinary WooCommerce checkout
  sees those holds. New installs and the Helm chart default to hard mode;
  an existing soft-mode installation must explicitly switch before production.
- Checkout persists the original intent before settlement, with payment
  request material encrypted using AES-GCM and the WordPress auth salt.
  Verified settlement is checkpointed before promoting the same unpaid draft.
  Local promotion, stock reduction and completion use one DB transaction.
  Checkout, refund and recovery reject non-InnoDB order/item/stock tables
  before contacting a payment provider.
  A failed WooCommerce payment-completion hook causes rollback. WooCommerce
  11's deferred item deletion is flushed before adding replacement items.
- A manager-only recovery queue appears under WooCommerce → AgentCart, with
  matching `/agentcart/v1/checkout-recovery` REST routes. Three bounded cron
  retries can resume interrupted verification. Cases that cannot be fulfilled
  stay visible for a manager to retry or compensate. Compensation freezes
  checkout and requests the exact original total back to the original payer.
  Pending refunds remain unresolved until rail verification succeeds.
- The optional buyer server holds a process-lifetime file lock before loading
  its JSON state. A second server using the same resolved path refuses to start.
  This provides one writer on a local filesystem; it does not add HA.
- Extension, all three skills, root/gateway packages and locks, and both Helm
  charts are versioned 1.23.0. Gateway capability/OpenAPI/tool metadata uses the
  package version. The Helm bootstrap checks the chart's appVersion instead
  of a stale literal. Release preparation builds all three skill ZIPs and the
  extension ZIP, includes checksums, and detects stale chart/plugin copies.

The merchant registry health check now supports a reviewed v2 deployment and
requires agreement from two configured RPC providers on a common finalized
block. It checks exact record identity, current admission, entity and bond;
expired admission and changed configuration invalidate cached readiness.
Unsigned identity preparation exports the matching operator configuration for
WordPress/Helm. The merchant UI and onboarding bundle explain v2 registration
and renewal. Plugin rollouts now hash all bundled modules, including recovery.

CI and release verification now require the pinned Foundry toolchain, the
release runner installs Helm, and verifier-image checks install their Node
dependencies. Refund-ledger changes also trigger the image workflow. A manifest
signature is included when release signing is configured.

## Validation and reproducibility

Local WordPress/MariaDB integration uses actual WooCommerce order and stock
datastores with in-process fixture payment providers. It exercises ordinary
checkout contention, duplicate checkout, rollback after stock reduction,
lost verification replies, missing quote transients, unavailable stock,
pending-to-successful compensation, manager authorization, request redaction,
and independent processes racing for the last unit. No real funds move.

The checkout drill has been run with legacy order tables and HPOS. The harness
is `scripts/check-woocommerce-checkout-recovery.py`; it requires a separately
seeded Compose project named `shopbridge-recovery-*`. Never point it at merchant
data. The initial run covered WooCommerce 10.8.1 and the follow-up covers the
Helm-pinned WooCommerce 11.0.0. Official WordPress Plugin Check also runs in the
isolated shop. The earlier compatibility pass used WordPress 7.1 / WooCommerce 11.0.0
with legacy storage and HPOS; the chart pins WordPress 7.0.3. The September 7
follow-up passed both storage-mode drills and official Plugin Check on 7.0.3,
plus 129 WooCommerce tests and 52 registry Node tests. The remaining unchanged
suites retain their September 6 evidence (629 tests in the aggregate),
alongside PHPCS/WPCS and chart/package checks. The compact
[local validation record](evidence/release-1.23.0-local.json) records the scope
and artifact checksums; it is not independent production evidence.

```sh
python3 scripts/check-woocommerce-checkout-recovery.py --project shopbridge-recovery-123
scripts/prepare-semantic-release.sh 1.23.0
python3 scripts/stamp-release-version.py 1.23.0 --verify
python3 scripts/verify-release.py
```

## Upgrade requirements and remaining launch gates

Use InnoDB and one WooCommerce database connection for order, item, stock and
refund writes. Preserve WordPress auth salts with backups: changing them makes
pending encrypted recovery requests unreadable. Run WordPress cron from a real
scheduler on Talos and monitor the manager queue; traffic-driven WP-Cron alone
does not guarantee timely retries. Pending cases and verified payments survive
quote-transient deletion. A payment sent before any accepted checkout attempt,
including first arrival after quote expiry, still requires provider/support
reconciliation. Do not send funds for expired quotes.

Do not roll back to an extension version that ignores the recovery states while
unresolved cases exist. Back up the WooCommerce database and verifier SQLite
database before upgrading. Preserve both ledgers and reconcile provider activity
before resuming after a restore. Never clear a ledger to retry a payment.

Still required before a public paid launch:

1. Funded order protection: a reserve/underwriter or escrow arrangement with
   delivery disputes, exposure limits, chargebacks and duplicate-compensation
   accounting. Registry collateral alone cannot cover unlimited merchant sales.
2. Independent registry/security review, named validators and Safe operators,
   public admission and appeal rules, a reviewed v2 deployment and enrollment
   migration. The merchant UI now verifies v2 admission; hosted/optional-service
   v2 authorization paths still need integration. The supported v2 buyer path
   here is the Direct Skill, with unsigned operator preparation.
3. Real Stripe/Tempo sandbox and staging evidence, database/process-death and
   restore drills with the actual installed plugin set, refund reconciliation
   scheduling and paging, rate/abuse protection, and independent merchant/buyer
   trials with fresh Astra evals. Plugin hooks can perform external actions
   that a database rollback cannot undo.

See [production hardening](PRODUCTION_HARDENING.md) and
[registry operations](REGISTRY_V2_OPERATIONS.md) for the detailed gates.
