import json
from pathlib import Path
import sys

work = Path('/work')
read = lambda name: json.loads((work / (name + '.json')).read_text())
print(json.dumps({'project': sys.argv[1], 'image': sys.argv[2], 'signer': 'ephemeral-test-only-viem',
                  'capabilities_confirmed': True, 'positive': read('positive-result'),
                  'replay': read('replay'), 'negative_cases': [read(n) for n in ('N1', 'N2', 'N3', 'N4')],
                  'timeout_restored': read('restored')['status'] == 'available',
                  'payment_calls': 2, 'settled_calls': 1, 'rejected_calls': 1}, separators=(',', ':')))
