"""Wait using the WordPress scheduler's clock; never force a not-yet-due event."""
import json
from pathlib import Path

before = json.loads(Path('/work/recovery-before.json').read_text())
wait_seconds = max(0, before['cases']['N3']['next_scheduled_at'] - before['observed_at']) + 1
assert wait_seconds <= 150, f'Recovery wait exceeds bound: {wait_seconds}s'
print(wait_seconds)
