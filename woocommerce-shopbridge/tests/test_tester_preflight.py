import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preflight', ROOT / 'scripts/tester-preflight.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
STAMP = '2026-09-21T10:00:00+00:00'
NOW = 1789984800


def fixture():
    shop = {'schema': 'agentcart.shopbridge.support_diagnostics.v1', 'generated_at': STAMP,
            'plugin': {'version': 'test', 'environment_type': 'staging', 'public_origin_is_https': True},
            'tokens': {'production_strength': dict.fromkeys(('merchant_token_is_strong', 'payment_verifier_token_is_strong', 'signed_request_key_is_strong'), True), 'production_credentials_separated': True},
            'signed_requests': {'required_for': ['quote', 'checkout', 'refund', 'cancellation']},
            'payment': {'external_verifier_required_for_checkout': True, 'payment_verifier_configured': True, 'tempo_network': 'testnet', 'x402_configured': False},
            'catalog': {'stock_hold_mode': 'hard'},
            'operations': dict.fromkeys(('transactional_storage', 'encrypted_recovery_available', 'external_scheduler_configured', 'heartbeat_fresh'), True),
            'registry': {'domain_proof_configured': True, 'onchain_readiness': {'ready': True}}}
    shop['operations']['attention_required'] = False
    verifier = {'generated_at': STAMP, 'version': 'test', 'ok': True, 'token_required': True,
                'enabled_rails': ['tempo-mpp'], 'allowed_tempo_networks': ['testnet'], 'stripe_credential_mode': 'not_configured',
                'replay_store_driver': 'sqlite', 'replay_store_durable': True, 'replay_store_writable': True, 'replay_journal_writable': True,
                'tempo_settlement': {'configured': True}, 'tempo_refunds': {'configured': True}, 'refund_ledger': {'counts': {}},
                'refund_reconciliation': {'enabled': True, 'last_completed_at': STAMP, 'queued': 0, 'errors': 0}}
    return shop, verifier


class PreflightTests(unittest.TestCase):
    def evaluate(self, shop, verifier, **kwargs):
        return p.evaluate(shop, verifier, version='test', artifacts_ok=True, now=NOW, **kwargs)

    def test_curated_pilot_requires_explicit_choice(self):
        shop, verifier = fixture()
        self.assertFalse(self.evaluate(shop, verifier)['ready'])
        self.assertTrue(self.evaluate(shop, verifier, curated_v1=True)['ready'])

    def test_each_essential_configuration_fails_closed(self):
        mutations = [('plugin', 'environment_type', 'production'), ('plugin', 'version', 'old'),
                     ('tokens', 'production_credentials_separated', False), ('signed_requests', 'required_for', []),
                     ('payment', 'tempo_network', 'mainnet'), ('payment', 'x402_configured', True),
                     ('operations', 'heartbeat_fresh', False), ('operations', 'transactional_storage', False),
                     ('operations', 'attention_required', True), ('catalog', 'stock_hold_mode', 'soft')]
        for section, field, value in mutations:
            with self.subTest(field=field):
                shop, verifier = fixture()
                shop[section][field] = value
                self.assertFalse(self.evaluate(shop, verifier, curated_v1=True)['ready'])

    def test_live_unknown_mixed_rails_stale_and_review_required_fail(self):
        for key, value in [('stripe_credential_mode', 'live'), ('stripe_credential_mode', 'unknown'),
                           ('allowed_tempo_networks', ['testnet', 'mainnet']), ('enabled_rails', ['x402']),
                           ('generated_at', '2000-01-01T00:00:00Z'), ('generated_at', '2099-01-01T00:00:00Z'),
                           ('generated_at', '2026-09-21T10:00:00'), ('refund_ledger', {'counts': {'review_required': 1}})]:
            with self.subTest(key=key, value=value):
                shop, verifier = fixture()
                verifier[key] = value
                self.assertFalse(self.evaluate(shop, verifier, curated_v1=True)['ready'])

    def test_v2_requires_unexpired_eligible_admission(self):
        shop, verifier = fixture()
        shop['registry']['onchain_readiness']['admission'] = {'eligible': True, 'expires_at': NOW + 600}
        self.assertTrue(self.evaluate(shop, verifier)['ready'])
        shop['registry']['onchain_readiness']['admission']['expires_at'] = NOW
        self.assertFalse(self.evaluate(shop, verifier, curated_v1=True)['ready'])

    def test_missing_malformed_fields_and_secrets_never_escape(self):
        for value in (None, [], 'SECRET', {'unexpected': 'SECRET'}, True):
            shop, verifier = fixture()
            shop['operations'] = value
            verifier['configuration_errors'] = ['SECRET buyer@example.test']
            report = self.evaluate(shop, verifier, curated_v1=True)
            self.assertFalse(report['ready'])
            self.assertNotIn('SECRET', json.dumps(report))
            self.assertNotIn('buyer@example', json.dumps(report))
        self.assertFalse(self.evaluate({}, {})['ready'])

    def test_missing_artifacts_cannot_pass(self):
        shop, verifier = fixture()
        self.assertFalse(p.evaluate(shop, verifier, version='test', artifacts_ok=False, now=NOW, curated_v1=True)['ready'])
