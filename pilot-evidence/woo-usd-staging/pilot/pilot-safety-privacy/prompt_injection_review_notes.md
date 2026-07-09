# prompt_injection_review_notes

- Scope: `pilot_gate`
- Owner id: `pilot-safety-privacy`
- Recorded at: 2026-07-09T20:41Z
- Operator: Codex security review session authorized by Max (GiraeffleAeffle)
- Command or source: manual review of all six checked cases in `gateway/config/prompt_injection_corpus.json`

## Evidence

Review conclusion: the cases cover the merchant-controlled surfaces most likely
to influence an agent before purchase and aftercare. Product and merchant text
cannot authorize checkout; registry prose cannot bypass payment verification;
delivery notes cannot claim a refund happened; and refund-policy prose cannot
mark money returned. The expected controls consistently classify merchant text
as display-only untrusted data and preserve explicit approval plus quote/payment
bindings. No case asks a model to infer trust from merchant wording. Future
coverage should add encoded/Unicode variants and multi-field instruction
splitting before a real-money pilot.
