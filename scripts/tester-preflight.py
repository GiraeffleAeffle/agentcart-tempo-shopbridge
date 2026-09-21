#!/usr/bin/env python3
"""Read-only supervised staging gate; consumes freshly exported operator diagnostics."""
from __future__ import annotations
import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024


def load(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('oversize input')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('expected object')
    return data


def get(data, *keys):
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def fresh(value, now):
    try:
        stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.tzinfo is not None and 0 <= now - stamp.timestamp() <= 300
    except (ValueError, TypeError, AttributeError, OverflowError):
        return False


def evaluate(shop, verifier, *, version, artifacts_ok, curated_v1=False, now=None):
    now = time.time() if now is None else now
    checks = []
    def check(name, passed, fix):
        checks.append({'check': name, 'passed': bool(passed), 'remediation': '' if passed else fix})
    check('fresh_diagnostics', get(shop, 'schema') == 'agentcart.shopbridge.support_diagnostics.v1'
          and fresh(get(shop, 'generated_at'), now) and fresh(get(verifier, 'generated_at'), now),
          'Export both diagnostics again; use reports less than five minutes old and synchronized clocks.')
    check('release_artifacts', artifacts_ok, 'Verify the release manifest and all four ZIPs from the same release.')
    check('matching_versions', get(shop, 'plugin', 'version') == version == get(verifier, 'version'),
          'Install the plugin and verifier image matching this preflight release.')
    check('staging_https', get(shop, 'plugin', 'environment_type') == 'staging'
          and get(shop, 'plugin', 'public_origin_is_https') is True,
          'Use a separate HTTPS staging shop with synthetic customer data.')
    check('credentials', all(get(shop, 'tokens', 'production_strength', k) is True for k in
          ('merchant_token_is_strong', 'payment_verifier_token_is_strong', 'signed_request_key_is_strong'))
          and get(shop, 'tokens', 'production_credentials_separated') is True and get(verifier, 'token_required') is True,
          'Configure distinct strong merchant, verifier and signing credentials.')
    required = get(shop, 'signed_requests', 'required_for')
    check('signed_mutations', isinstance(required, list) and all(x in required for x in ('quote', 'checkout', 'refund', 'cancellation')),
          'Require signed requests for quote, checkout, refund and cancellation.')
    check('verified_checkout', get(shop, 'payment', 'external_verifier_required_for_checkout') is True
          and get(shop, 'payment', 'payment_verifier_configured') is True and get(verifier, 'ok') is True,
          'Require an external verifier and resolve its health failures.')
    check('staging_rails', get(shop, 'payment', 'tempo_network') == 'testnet'
          and get(verifier, 'allowed_tempo_networks') == ['testnet']
          and get(verifier, 'stripe_credential_mode') in ('test', 'not_configured')
          and get(shop, 'payment', 'x402_configured') is False,
          'Limit this pilot to Tempo testnet and optional Stripe test credentials; disable x402 for this profile.')
    rails = get(verifier, 'enabled_rails')
    check('supported_rails', isinstance(rails, list) and bool(rails)
          and all(x in ('tempo-mpp', 'stripe-card-mpp') for x in rails)
          and ('stripe-card-mpp' not in rails or get(verifier, 'stripe_credential_mode') == 'test'),
          'Enable only supported test rails with matching credentials.')
    check('tempo_aftercare', not isinstance(rails, list) or 'tempo-mpp' not in rails or (
          get(verifier, 'tempo_settlement', 'configured') is True and get(verifier, 'tempo_refunds', 'configured') is True),
          'Configure testnet settlement verification and a test-only refund wallet before payment tests.')
    check('durable_checkout', get(shop, 'catalog', 'stock_hold_mode') == 'hard'
          and get(shop, 'operations', 'transactional_storage') is True
          and get(shop, 'operations', 'encrypted_recovery_available') is True,
          'Enable hard stock holds, transactional WooCommerce tables and OpenSSL AES-GCM recovery.')
    check('durable_verifier', get(verifier, 'replay_store_driver') == 'sqlite'
          and all(get(verifier, k) is True for k in ('replay_store_durable', 'replay_store_writable', 'replay_journal_writable')),
          'Mount persistent SQLite and replay-journal storage; resolve storage errors.')
    check('scheduler', get(shop, 'operations', 'external_scheduler_configured') is True
          and get(shop, 'operations', 'heartbeat_fresh') is True
          and get(verifier, 'refund_reconciliation', 'enabled') is True
          and fresh(get(verifier, 'refund_reconciliation', 'last_completed_at'), now),
          'Run an external WordPress cron worker and enable verifier reconciliation; wait for fresh heartbeats.')
    counts = get(verifier, 'refund_ledger', 'counts')
    check('operations_clear', isinstance(counts, dict)
          and all(type(n) is int and n >= 0 and (state in ('succeeded', 'failed', 'canceled') or n == 0) for state, n in counts.items())
          and get(shop, 'operations', 'attention_required') is False
          and get(verifier, 'refund_reconciliation', 'queued') == 0
          and get(verifier, 'refund_reconciliation', 'errors') == 0,
          'Resolve outstanding checkout/refund cases before starting a new tester session.')
    admission = get(shop, 'registry', 'onchain_readiness', 'admission')
    expiry = get(admission, 'expires_at')
    check('registry', get(shop, 'registry', 'domain_proof_configured') is True
          and get(shop, 'registry', 'onchain_readiness', 'ready') is True
          and ((get(admission, 'eligible') is True and type(expiry) is int and expiry > now)
               or (curated_v1 and admission is None)),
          'Refresh registry health and current admission, or explicitly select a maintainer-curated v1 staging pilot.')
    return {'schema': 'agentcart.tester_preflight.v1', 'ready': all(c['passed'] for c in checks),
            'scope': 'supervised_staging_only', 'registry_policy': 'curated_v1_pilot' if curated_v1 else 'bonded_admission',
            'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shop-diagnostics', required=True, type=Path)
    parser.add_argument('--verifier-health', required=True, type=Path)
    parser.add_argument('--release-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--curated-v1-pilot', action='store_true')
    args = parser.parse_args()
    try:
        spec = importlib.util.spec_from_file_location('release_verifier', ROOT / 'scripts/verify-release.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        errors = module.verify_release(manifest_path=args.manifest, root=args.release_root)
        version = load(ROOT / 'package.json')['version']
        manifest = load(args.manifest)
        components = get(manifest, 'components')
        expected_components = ('gateway', 'woocommerce_shopbridge', 'shopbridge_direct_skill', 'agentcart_service_skill', 'household_os_skill')
        artifacts = get(manifest, 'artifacts')
        artifacts_ok = (not errors and get(manifest, 'release', 'version') == version
                        and isinstance(artifacts, list) and len(artifacts) == 4
                        and {get(a, 'component') for a in artifacts} == set(expected_components[1:])
                        and all(get(components, key, 'version') == version for key in expected_components))
        report = evaluate(load(args.shop_diagnostics), load(args.verifier_health), version=version,
                          artifacts_ok=artifacts_ok, curated_v1=args.curated_v1_pilot)
    except (OSError, ValueError, TypeError, KeyError):
        # Never copy file paths, parser excerpts, provider errors or input bodies.
        report = {'schema': 'agentcart.tester_preflight.v1', 'ready': False,
                  'error': 'Invalid or unreadable diagnostic/release input. Re-export JSON and release artifacts.'}
    print(json.dumps(report, indent=2))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
