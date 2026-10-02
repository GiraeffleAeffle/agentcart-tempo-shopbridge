"""Assert cumulative payment events after each boundary, including the replay."""
import json
from pathlib import Path
import sys

accepted, rejected = map(int, sys.argv[1:])
events = []
for line in Path('/work/verifier.log').read_text().splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(event, dict) and event.get('operation') == 'payment':
        events.append(event)
assert len(events) == accepted + rejected, events
successes = [e for e in events if e.get('real_settlement_verified') is True]
failures = [e for e in events if e.get('outcome') == 'rejected']
assert len(successes) == accepted, events
assert all(e['status'] == 200 and e.get('outcome') == 'ok' for e in successes), successes
assert len(failures) == rejected, events
assert all(e['status'] == 400 and e.get('real_settlement_verified') is False for e in failures), failures
print(json.dumps({'payment_calls': len(events), 'settled': accepted, 'rejected': rejected}))
