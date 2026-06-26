# Prompt-Injection Corpus

Status: alpha safety gate for merchant-provided text.

The machine-readable source is
`gateway/config/prompt_injection_corpus.json`. Validate it with:

```sh
python3 scripts/check-prompt-injection-corpus.py --verify-test-refs
```

The corpus covers these untrusted merchant-controlled surfaces:

- product title;
- product description;
- merchant name;
- registry profile text;
- delivery note;
- refund policy.

Every case requires controls for untrusted merchant text, disabled instruction
execution, explicit human approval, and preservation of quote/payment contract
hashes where relevant.

## Current Runtime Checks

- Direct skill approval packets label merchant text as untrusted data and render
  product/merchant names as quoted merchant-provided display text.
- AgentCart service catalog and quote-tournament paths mark registry-discovered
  merchant products as untrusted data.

## Rule

Merchant text can be displayed, summarized, filtered, ranked, or quoted. It must
not become an instruction to the buyer agent, must not synthesize approval, and
must not mark payment or refunds as complete without verifier evidence.
