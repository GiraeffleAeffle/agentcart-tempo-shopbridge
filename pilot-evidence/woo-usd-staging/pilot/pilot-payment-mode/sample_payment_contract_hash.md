# sample_payment_contract_hash

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-05T21:06Z
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `scripts/woocommerce-usd-mppx-settlement-smoke.sh` (see live smoke evidence)

## Evidence

Sample from the 2026-07-05 settlement rehearsal on
`https://woo-usd.agentcart.eu` (Tempo **testnet**, not real settlement):

- payment_contract_hash:
  `7648187b2c80678baae8259214bc84ea32f00d79711159c8789c2706f06b9274`
- bound quote_hash:
  `ab6f67fac8d048fde507b1882b215efb56ddfbd0403423e974586b04ba866467`
- amount: 1578 cents USD; rail `tempo-mpp`; network `testnet`
- payer: `0x2cbd9b394fa407bd299b4ab74d796795659187a9`
  (source `did:pkh:eip155:42431:0x2cbD9B394fA407bD299b4Ab74d796795659187A9`)
- recipient: `0x39a0134d5140e499ce1d8bceffdbbd7523108531`
- transaction reference (replay-protected):
  `0x110e0bad0a2d2af65f96497192d9a9f430e7d3837c516f96ee76659a8fe2b4cf`
- verifier state: `verified`, `real_settlement_verified=true`

Full transcript:
`pilot-evidence/woo-usd-staging/attachments/usd-mppx-settlement-smoke-2026-07-05.txt`.

## Post-hardening sample

The 2026-07-09 post-deployment run bound quote hash
`e4cce9c39be18d614cd816b246bd3dff5df3324646d3a5f01745b5468a8caa16`
to payment contract hash
`230ea41e82a2635dfdc7a3db0749bca784bfeed423d0e836aa06b2121e694c1d`.
The verifier accepted payment reference
`0x786ac168d49ba11a0a2923efff790b06a0ea38aa34a63e360ec5c50cb6f7019e`
for 1,578 cents USD on Tempo testnet and recorded it in the durable SQLite
replay store.
