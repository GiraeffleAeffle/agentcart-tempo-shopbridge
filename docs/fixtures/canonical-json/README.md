# ShopBridge canonical JSON (`shopbridge-json-v1`)

`vectors.json` pins 19 input values, exact canonical strings, and lowercase
SHA-256 hex digests. Hash the canonical string's UTF-8 bytes, without a BOM or
trailing newline. Gateway Python, portable skill Python, Node indexers, and the
PHP plugin consume this same fixture.

## Rule

- Recursively sort object keys lexicographically by **Unicode code point**, not
  UTF-16 code unit, locale, or insertion order. Array order remains unchanged.
- Emit `,` and `:` separators with no whitespace. Preserve object/list types,
  including `{}` versus `[]`. Emit `true`, `false`, and `null` in lowercase.
- Emit non-ASCII characters directly, including astral characters and U+2028 /
  U+2029; leave `/` and U+007F unescaped. Do not normalize Unicode.
- Escape only `"`, `\`, and characters below U+0020. Use `\"`, `\\`, the short
  forms `\b`, `\f`, `\n`, `\r`, `\t`, and otherwise `\u00xx` with **lowercase**
  hexadecimal digits (the existing Python, PHP, and Node convention).
- Hashed cross-runtime material contains **integers only, never floats**. Use
  plain decimal integers (zero is `0`), within the interoperable safe-integer
  range `[-9007199254740991, 9007199254740991]`. Money uses integer minor units.
  Decimal quantities must be represented as agreed strings or scaled integers.
  Floats, non-finite numbers, lone surrogates, duplicate object keys, and
  non-JSON runtime types are outside this contract; native serializer support
  for them does not establish cross-runtime equivalence.

This is **not RFC 8785 / JCS**. Its string escaping and whitespace rules match
JCS, but JCS sorts keys by UTF-16 code units and specifies ECMAScript / IEEE-754
number serialization, including non-integral numbers. ShopBridge deliberately
retains its existing Python/PHP code-point ordering and integer-only domain.
The BMP/astral key vectors distinguish these two ordering rules.

## Historical commitments and PHP representations

No existing on-chain record hash or committed document is rewritten. Gateway
`registry_record_hash` already delegates to the UTF-8 skill trust serializer;
`registry_record.py` now inherits the corrected gateway encoding for newly
created claim/manifest hashes. Records produced with a divergent encoder need
an explicitly published replacement, not a reinterpretation of an existing
on-chain commitment.

Persisted gateway approvals, decisions, imported-packet metadata, and audit
JSONL events retain their original identifiers; loading/exporting them does
not recompute those stored hashes. New packet imports verify only this UTF-8
rule (not an automatic ASCII fallback). New audit exports use this rule.
The gateway's hosted registry transparency chain and the operator's JSONL
ledger **do** reverify event hashes: unmarked historical events explicitly use
the old ASCII-escaped Python encoding. Newly appended events carry the hashed
`canonicalization: "shopbridge-json-v1"` field and use UTF-8. Mixed chains retain
the exact previous hashes; unknown markers fail verification. No ledger
migration or historical event rewriting is performed.

Persisted `state.refund_idempotency` request hashes also require version-aware
comparison: new entries store `canonicalization: "shopbridge-json-v1"` beside
the UTF-8 request hash. Same-key retries against unmarked historical entries
use only the old ASCII encoding, preserving non-ASCII reasons such as
`Rücksendung`. Unknown markers or changed requests fail with an idempotency
conflict; legacy entries are not rewritten. The request material still
includes the order id and every request field except the authentication token.
Other gateway request hashes in registry receipts, revocations, and
transparency events are metadata, not independently compared on retries.
Checkout idempotency stores order ids; its payment-challenge digest hashes raw
HTTP bytes and is unaffected by canonical JSON encoding.

PHP fixtures decode JSON objects as `stdClass`, preserving empty and numeric-key
objects. Native associative decoding (`json_decode(..., true)`) irreversibly
turns `{}` into `[]` and objects with contiguous numeric keys into lists. The
plugin preserves existing PHP-array semantics; callers requiring those object
shapes must retain `stdClass`. Both PHP encoders sort their members recursively.

## Scoped verification

```sh
cd gateway && python3 -m unittest discover -s tests -p test_canonical_json.py
node --test gateway/tests/canonical-json.test.mjs  # from repository root
php woocommerce-shopbridge/tests/canonical-json.php
python3 -m unittest discover -s woocommerce-shopbridge/tests -p test_canonical_json.py
```

Python covers gateway and all three skill hash encoders, mixed historical/new
ledgers, durable Unicode refund retries/conflicts, and a real HTTP import of a
skill packet approved by `Jürgen Müller`.
Node covers the indexer serializer and the loop's independent-history hash;
the duplicate serializer was removed. PHP checks the real plugin and registry
event encoders with only WordPress hook/JSON-wrapper stubs.
