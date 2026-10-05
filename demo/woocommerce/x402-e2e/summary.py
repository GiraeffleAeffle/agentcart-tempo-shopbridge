import json
from pathlib import Path
import sys

work = Path('/work')
read = lambda name: json.loads((work / (name + '.json')).read_text())
table = read('event-table')
after = read('recovery-after')
n3 = after['cases']['N3']
recovery = {key: after[key] for key in ('was_due', 'recovery_ran', 'schedule_state', 'due_at', 'observed_at')}
recovery.update({'order_id': n3['order_id'], 'next_scheduled_at': n3['next_scheduled_at'],
                 'recovery_attempts': n3['recovery_attempts'], 'draft_state': n3['state'], 'paid': n3['paid']})
print(json.dumps({'project': sys.argv[1], 'image': sys.argv[2], 'signer': 'ephemeral-test-only-viem',
                  'capabilities_confirmed': True, 'positive': read('positive-result'),
                  'replay': read('replay'), 'negative_cases': [read(n) for n in ('N1', 'N2', 'N3', 'N4')],
                  'timeout_restored': read('restored')['status'] == 'available',
                  'per_quote_events': table, 'recovery': recovery,
                  'payment_calls': sum(row['settled'] + row['rejected'] for row in table),
                  'settled_calls': sum(row['settled'] for row in table),
                  'rejected_calls': sum(row['rejected'] for row in table)}, separators=(',', ':')))
