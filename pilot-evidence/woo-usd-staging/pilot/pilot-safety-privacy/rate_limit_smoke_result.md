# rate_limit_smoke_result

- Scope: `pilot_gate`
- Owner id: `pilot-safety-privacy`
- Recorded at: 2026-07-09T20:36Z
- Operator: Codex live staging verification session authorized by Max (GiraeffleAeffle)
- Command or source: live ShopBridge smoke with `--abuse-rate-limits --rate-limit-buckets quote --rate-limit-max-attempts 35`

## Evidence

The live staging abuse smoke exhausted the quote bucket and exited successfully
only after observing HTTP 429. The capability policy advertised 30 quote
requests per 60 seconds for a hashed client. Because earlier release checks had
already consumed part of the bucket, the abuse probe reached the limit after
18 additional attempts. The rejection included bucket `quote`, limit 30,
`retry_after_seconds=56`, and reset time `2026-07-09T20:36:00Z`. No merchant
credential was used for this public quote-rate-limit test.
