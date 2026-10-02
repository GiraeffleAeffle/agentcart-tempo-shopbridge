"""Exercise the real skill CLI; adversarial receipts intentionally use a fake signature."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

CLI = Path('/repo/gateway/shopbridge-direct-skill/scripts/shopbridge-command.py')
ORIGIN = 'http://shop.local'
RAIL = 'x402-compatible'
STATE = Path('/work/positive.json')


def http_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def skill(command, args, error=None):
    result = subprocess.run([sys.executable, str(CLI)], input=json.dumps({'command': command, 'args': args}),
                            text=True, capture_output=True, timeout=90)
    if error:
        assert result.returncode != 0 and error in result.stdout + result.stderr, (command, result.stdout, result.stderr)
        return
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    output = json.loads(result.stdout)
    output.pop('rc', None)
    return output


def profile():
    manifest = http_json(ORIGIN + '/.well-known/agentcart.json')
    profiles = manifest['protocol_profiles']
    if isinstance(profiles, dict):
        return profiles[RAIL]
    return next(p for p in profiles if p.get('id') == RAIL or p.get('profile') == RAIL)


def fresh():
    manifest = http_json(ORIGIN + '/.well-known/agentcart.json')
    winner = skill('discover_quotes', {'registry_records': [manifest['discovery']['suggested_registry_record']],
                   'query': 'tea', 'country': 'US', 'postal_code': '10001', 'payment_rail': RAIL,
                   'allow_private_origin': True, 'format': 'json'})['winner']
    quote = skill('quote', {'base_url': ORIGIN, 'product_id': winner['quote']['items'][0]['product_id'],
                  'quantity': 1, 'payment_rail': RAIL, 'quote_trust': winner['quote_trust'],
                  'allow_private_origin': True, 'ship_to': {'first_name': 'Fake', 'last_name': 'Buyer',
                  'address_1': '1 Test Street', 'city': 'New York', 'state': 'NY', 'postcode': '10001', 'country': 'US'}})
    approval = skill('approval_packet', {'quote': quote, 'payment_rail': RAIL})
    assert approval['approval_ready'] is True
    args = {'base_url': ORIGIN, 'quote': quote, 'payment_rail': RAIL, 'approved': True,
            'approval_hash': approval['approval_hash'], 'allow_private_origin': True}
    handoff = skill('payment_handoff', args)
    assert handoff['ok'] is True
    args.update(handoff['checkout_args'])
    return args, handoff


def adversarial_receipt(args, handoff, case):
    request = handoff['payment_request']
    accepted = request['accepted']
    nonce = request['authorization_nonce']
    if case in ('N1', 'N2'):
        nonce = nonce[:-1] + ('0' if nonce[-1] != '0' else '1')
    valid_before = request['validBefore']
    if case == 'N3':
        valid_before = str(int(time.time()) + accepted['maxTimeoutSeconds'] + 600)
    payload = {'x402Version': 2, 'accepted': accepted, 'payload': {'signature': '0x' + '11' * 65,
               'authorization': {'from': '0x' + '11' * 20, 'to': accepted['payTo'], 'value': accepted['amount'],
                                 'validAfter': request['validAfter'], 'validBefore': valid_before, 'nonce': nonce}}}
    return {'method': RAIL, 'status': 'authorized', 'x402_version': 2,
            'x402_payment_signature': base64.b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode(),
            'amount': accepted['amount'], 'network': accepted['network'], 'asset': accepted['asset'],
            'pay_to': accepted['payTo'], 'quote_hash': request['quote_hash'],
            'payment_contract_hash': request['payment_contract_hash'],
            'amount_cents': args['quote']['total_cents'], 'currency': args['quote']['currency']}


def run(case):
    if case in ('available', 'N4'):
        p = profile()
        assert p['status'] == ('unavailable' if case == 'N4' else 'available'), p
        if case == 'N4':
            assert 'x402_max_timeout_seconds' in json.dumps(p), p
        return {'case': case, 'status': p['status']}
    if case == 'replay':
        state = json.loads(STATE.read_text())
        order = skill('checkout', state['args'])
        assert order['id'] == state['order']['id'], order
        status = skill('order_status', {'status_url': order['status_url'], 'status_token': order['status_token'],
                                       'allow_private_origin': True})
        assert status['payment_status'] == 'paid', status
        return {'case': case, 'order_id': order['id'], 'payment_status': status['payment_status']}
    args, handoff = fresh()
    if case == 'positive':
        payer = http_json('http://signer:4293/payer')['payer']
        signing_args = {key: args[key] for key in ('quote', 'payment_rail', 'approved', 'approval_hash')}
        signing_args['payment_handoff'] = handoff
        typed = skill('x402_typed_data', {**signing_args, 'payer': payer})
        signed = http_json('http://signer:4293/sign', typed)
        assert signed['payer'].lower() == payer.lower()
        receipt = skill('x402_receipt', {**signing_args, **signed})
        assert receipt['checkout_args'] == handoff['checkout_args']
        args['payment_receipt'] = receipt['payment_receipt']
        order = skill('checkout', args)
        assert order['payment_verification']['real_settlement_verified'] is True, order
        assert order.get('payment_response') or order['payment_verification'].get('payment_response'), order
        STATE.write_text(json.dumps({'args': args, 'order': order}))
        return {'case': case, 'order_id': order['id'], 'real_settlement_verified': True}
    args['payment_receipt'] = adversarial_receipt(args, handoff, case)
    if case == 'N2':
        # Simulated non-compliant client: skip only the skill's receipt gate, not payload construction.
        spec = importlib.util.spec_from_file_location('shopbridge_command', CLI)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(CLI.parent))
        spec.loader.exec_module(module)
        module.registry_trust.x402_receipt_issues = lambda _receipt, _destination: []
        try:
            module.command_checkout(args)
        except SystemExit as exc:
            error = json.loads(str(exc))['error']
            assert error['status'] == 402 and error['detail']['code'] == 'agentcart_x402_nonce_mismatch', error
        else:
            raise AssertionError('Plugin accepted wrong nonce')
    else:
        skill('checkout', args, error={'N1': 'x402_authorization_nonce_mismatch',
                                     'N3': 'x402_authorization_window_invalid'}[case])
    return {'case': case, 'rejected': True}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), separators=(',', ':')))
