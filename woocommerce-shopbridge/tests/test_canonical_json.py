import pathlib
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("php"), "php is required for canonical JSON behavior tests")
class CanonicalJsonBehaviorTests(unittest.TestCase):
    def test_plugin_and_registry_event_shared_vectors(self) -> None:
        harness = pathlib.Path(__file__).with_name("canonical-json.php")
        result = subprocess.run(["php", str(harness)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
