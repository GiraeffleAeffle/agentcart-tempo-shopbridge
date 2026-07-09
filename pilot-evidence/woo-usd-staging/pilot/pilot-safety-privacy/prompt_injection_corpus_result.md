# prompt_injection_corpus_result

- Scope: `pilot_gate`
- Owner id: `pilot-safety-privacy`
- Recorded at: 2026-07-09T20:41Z
- Operator: Codex local verification session authorized by Max (GiraeffleAeffle)
- Command or source: `python3 scripts/check-prompt-injection-corpus.py --corpus gateway/config/prompt_injection_corpus.json --verify-test-refs`

## Evidence

The checked corpus command exited successfully and verified every referenced
test. Six adversarial cases cover product titles, product descriptions,
merchant names, registry profiles, delivery notes, and refund policies. Each
case requires merchant text to remain untrusted with instructions disabled;
the control set additionally requires explicit human approval, prevents
checkout from text, and preserves quote/payment-contract hashes where relevant.
The corpus schema is `agentcart.prompt_injection_corpus.v1` version 0.1.0.
