"""Correlate payment events by quote AND contract across checkout, replay and recovery."""
import json
from pathlib import Path
import sys

work = Path('/work')
recovered = sys.argv[1] == 'recovered'
events = []
for line in (work / 'verifier.log').read_text().splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(event, dict) and event.get('operation') == 'payment':
        events.append(event)

records = []
for name in ('positive-result', 'N1', 'N2', 'N3'):
    path = work / (name + '.json')
    if path.exists():
        records.append(json.loads(path.read_text()))
keys = {(record['quote_hash'], record['payment_contract_hash']) for record in records}
assert len(keys) == len(records), 'Each payment case must have a fresh quote/contract binding'
assert all((event.get('quote_hash'), event.get('payment_contract_hash')) in keys for event in events), events
table = []
for record in records:
    key = (record['quote_hash'], record['payment_contract_hash'])
    matched = [event for event in events if (event.get('quote_hash'), event.get('payment_contract_hash')) == key]
    settled = [event for event in matched if event.get('real_settlement_verified') is True]
    rejected = [event for event in matched if event.get('outcome') == 'rejected']
    assert len(matched) == len(settled) + len(rejected), matched
    assert all(event['status'] == 200 and event.get('outcome') == 'ok' for event in settled), settled
    assert all(event['status'] == 400 and event.get('real_settlement_verified') is False for event in rejected), rejected
    case = record['case']
    if case == 'positive':
        assert len(settled) == 1 and len(rejected) == 0, matched
    elif case == 'N3':
        assert len(settled) == 0, matched
        assert len(rejected) == (2 if recovered else 1), matched
    else:
        assert not matched, (case, matched)
    table.append({'case': case, 'quote_hash': key[0], 'payment_contract_hash': key[1],
                  'settled': len(settled), 'rejected': len(rejected)})
(work / 'event-table.json').write_text(json.dumps(table))
print(json.dumps(table, separators=(',', ':')))
