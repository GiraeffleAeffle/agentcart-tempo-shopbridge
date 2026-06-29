# Pilot Execution Playbook

Status: supervised external-beta preparation. This playbook turns the checked
pilot gates into an operator workflow for one staging merchant and the required
buyer-agent runtimes.

The dry-run path proves the evidence runner, report schema, and folder layout
work without external merchant credentials. It is not pilot evidence.

## Dry Run

Run this before scheduling a staging merchant:

```sh
scripts/pilot-evidence-dry-run.sh pilot-evidence-dry-run-report.json
```

The dry run:

- creates a temporary sample evidence folder with every required file name;
- writes a temporary production-shaped payment env file;
- runs `scripts/collect-pilot-evidence.py`;
- validates that the generated report uses
  `agentcart.pilot_evidence_runner.v1`;
- writes an attachable JSON report to the path you pass.

The generated report proves the local tooling path only. Do not attach it to a
real go/no-go decision.

## Real Pilot Command

For a staging merchant, create the evidence folder once:

```sh
python3 scripts/collect-pilot-evidence.py --write-sample pilot-evidence/example-shop
```

Replace every generated `TODO` with real artifacts, then run:

```sh
python3 scripts/collect-pilot-evidence.py \
  --pilot-evidence-dir pilot-evidence/example-shop/pilot \
  --buyer-agent-evidence-dir pilot-evidence/example-shop/buyer-agents \
  --payment-env-file deploy/home-server/.env \
  --report-out pilot-evidence-report.json
```

The release owner attaches `pilot-evidence-report.json` to the decision record.
The report is useful only when every evidence file points to real staging
commands, transcripts, screenshots, hashes, URLs, or operator notes.

## Evidence Map

| Evidence section | Operator action that produces it |
| --- | --- |
| `pilot/pilot-merchant-onboarding/*` | Install the ShopBridge ZIP on the staging WooCommerce shop, configure merchant identity/support/payment settings, export the exposed catalog preview, run sandbox quote/checkout checks, run the live WooCommerce smoke, and record the registry bundle or hosted registry URL. |
| `pilot/pilot-buyer-agent-setup/*` | Run the buyer-agent test matrix and one complete discovery, quote, approval, checkout handoff, aftercare, and audit export/import path for each required runtime. |
| `pilot/pilot-payment-mode/*` | Record the payment-mode decision, verifier health or fixture result, production payment profile check, refund policy, and sample payment contract hash. |
| `pilot/pilot-support-channel/*` | Record monitored support contact, response SLA, diagnostic collection steps, and the named incident owner for the pilot window. |
| `pilot/pilot-rollback/*` | Record the previous plugin ZIP, release manifest, rollback or revocation command evidence, and registry revocation URL. |
| `pilot/pilot-safety-privacy/*` | Record the privacy notice, redacted ops event sample, rate-limit smoke, prompt-injection corpus result, and prompt-injection review notes. |
| `buyer-agents/agentcart-service-openclaw/*` | Capture the service-backed buyer path: install/configuration, health, discovery transcript, quote comparison transcript, approval hash, checkout handoff or order result, aftercare, and audit export. |
| `buyer-agents/shopbridge-direct-skill/*` | Capture the direct-skill buyer path: install/configuration, doctor result, discovery transcript, quote comparison transcript, approval hash, checkout handoff or payload, aftercare, audit packet, and optional audit import. |
| `buyer-agents/generic-mcp-client/*` | Capture the generic MCP-style path: tool catalog export, discovery transcript, quote creation transcript, approval hash, checkout handoff or order result, aftercare, and audit export. |

## Replacement Rules

These dry-run artifacts must never be reused as real pilot evidence:

- generated sample markdown files that still contain `TODO`;
- the dry-run payment env file created by `scripts/pilot-evidence-dry-run.sh`;
- dry-run report output from a temporary sample folder;
- screenshots from local demo shops unless the decision explicitly scopes the
  pilot to that local demo;
- transcripts that do not name the merchant id, buyer-agent runtime, command or
  tool used, and timestamp.

Real evidence files should include:

- the command, URL, or source system that produced the artifact;
- the operator who recorded it;
- the timestamp and environment name;
- hashes or IDs needed to connect quote, approval, payment, order, and audit
  records;
- a clear note when an artifact is intentionally sandbox, testnet, or simulated.

## Verify Integration

`scripts/verify.sh` always runs `scripts/pilot-evidence-dry-run.sh` to protect
the no-credential report path.

For real pilot evidence, opt into the evidence-required gate:

```sh
AGENTCART_BETA_RELEASE_GATE=1 \
AGENTCART_PILOT_EVIDENCE_DIR=pilot-evidence/example-shop/pilot \
AGENTCART_BUYER_AGENT_EVIDENCE_DIR=pilot-evidence/example-shop/buyer-agents \
AGENTCART_PAYMENT_ENV_FILE=deploy/home-server/.env \
AGENTCART_PILOT_EVIDENCE_REPORT_OUT=pilot-evidence-report.json \
./scripts/verify.sh
```

Set `AGENTCART_WOO_COMPATIBILITY_SMOKE=1` when the decision needs the
Docker-backed WooCommerce compatibility smoke included in the same report.

## Exit Package

Before asking for the go/no-go decision, the operator should have:

- the populated evidence folder;
- `pilot-evidence-report.json` with `status: "passed"`;
- verifier operations evidence from issue #18;
- WooCommerce merchant-variance evidence from issue #19;
- non-maintainer setup walkthrough notes from issue #20;
- rollback owner, support owner, and observation window recorded in the
  decision record.
