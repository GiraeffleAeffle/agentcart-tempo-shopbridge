# ops_event_redaction_sample

- Scope: `pilot_gate`
- Owner id: `pilot-safety-privacy`
- Recorded at: 2026-07-09T20:41Z
- Operator: Codex local verification session authorized by Max (GiraeffleAeffle)
- Command or source: `gateway.tests.test_agentcart.AgentCartTests.test_ops_event_webhook_receives_quote_checkout_and_refund_events`

## Evidence

The focused ops-event test passed. It delivered quote, checkout, and refund
notifications to a fake webhook and asserted that the serialized payloads did
not contain `ship_to`. Checkout evidence contained only structured references,
including the approval-record hash, and refund evidence used the event kind and
severity rather than copying a payment credential. The separate request-log
redaction test also passed and rendered sensitive query values as
`token=%3Credacted%3E`. No bearer token, signed-request secret, private key,
delivery street, or raw payment credential is included in this evidence file.
