# Tester readiness after 1.23.0

The release is suitable for supervised staging/testnet evaluation with synthetic
customer data. A published release is not a production approval. Registry v2
still needs a reviewed deployment and real validator operators; until that
exists, describe the existing v1 pilot as a curated test registry, not a
verified open marketplace. Keep paid public checkout out of this test scope.

## Next work we can implement ourselves

| Priority | Deliverable | Acceptance evidence |
| --- | --- | --- |
| P0 | One-command tester preflight and staging profile | Check artifact version/checksums, health, quote and payment networks, hard stock holds, storage, scheduler and registry configuration. Reject mixed networks, live-payment credentials and missing prerequisites before a tester starts. Produce a redacted report with exact remediation steps. |
| P0 | Scheduled reconciliation and useful alerts | Run checkout recovery without shop traffic; resume pending refunds using their original operation IDs. Alert on unresolved age, failed verification and compensations needing a manager. Prove repeated/concurrent runs cannot duplicate settlement or refunds. Keep existing retry limits and manager authorization. |
| P0 | Automated crash-and-restore drills | Kill workers around each durable boundary, restore WooCommerce and verifier ledgers into an isolated environment, and reconcile against provider history before re-enabling writes. Prove no double debit/refund or overselling. A successful database copy alone is insufficient. |
| P1 | Reproducible multi-merchant test kit | Seed distinct shops, identical products, currencies, tax/shipping differences, last-unit stock and dishonest catalog claims. Provide a resettable fixture, buyer walkthrough and redacted support bundle. Test duplicate-entity shops, expired admission, missing witnesses and inconclusive comparisons. |
| P1 | Fresh Codex/Astra buyer evaluation | Exercise discovery, exact all-in comparison, partial baskets, substitutions, explicit final-quote approval, timeout recovery and aftercare. Include malicious merchant text that tries to change buyer instructions. Record failures and require zero unauthorized payment actions. |
| P1 | V2 testnet enrollment and case rehearsal | Automate unsigned setup/verification and receipt tracking for admission, renewal, suspension, appeal and slashing. Test distinct validator wallets, quorum changes and stale approvals. The operators still perform business checks and adjudication. |
| P2 | Consistent authorization across buyer runtimes | Bring the optional hosted/service path to the Direct Skill's v2 deployment, witness and admission requirements before inviting testers onto those paths. Restrict the first v2 pilot to the Direct Skill until this passes. |

Start with preflight, scheduling/alerts and the resettable test kit. Run a
maintainer-observed walkthrough before unattended external sessions. Collect
installation friction, incorrect comparison results, stuck operations and
recovery time; give testers a named support contact and stop procedure.

## Work that code alone cannot finish

Independent security/contract review; accountable and independent validator
operators; published admission, sanctions, conflicts and appeal rules; real
provider staging exercises; and a funded buyer-protection arrangement for a
paid launch. We can implement a dispute/case ledger and exposure limits once
the settlement and funding policy is selected. A registry bond does not insure
unlimited shop turnover, and low pricing is not evidence for slashing.

See [release scope and upgrade precautions](RELEASE_1.23.0.md) and
[v2 operator instructions](REGISTRY_V2_OPERATIONS.md).
