import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agentcart import exclusive_state_writer


class StateWriterTests(unittest.TestCase):
    def test_other_process_is_blocked_and_can_take_over_after_release(self):
        script = 'import pathlib, sys; from agentcart import exclusive_state_writer;\nwith exclusive_state_writer(pathlib.Path(sys.argv[1])): print("acquired")'
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'state.json'
            with exclusive_state_writer(path):
                result = subprocess.run([sys.executable, '-c', script, str(path)], cwd=ROOT, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('requires one writer', result.stderr)
            result = subprocess.run([sys.executable, '-c', script, str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'acquired')

    def test_alias_of_state_directory_cannot_bypass_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'data').mkdir()
            (root / 'alias').symlink_to(root / 'data', target_is_directory=True)
            with exclusive_state_writer(root / 'data/state.json'):
                with self.assertRaisesRegex(RuntimeError, 'Another AgentCart'):
                    with exclusive_state_writer(root / 'alias/state.json'):
                        self.fail('alias acquired a second writer')


if __name__ == '__main__':
    unittest.main()
