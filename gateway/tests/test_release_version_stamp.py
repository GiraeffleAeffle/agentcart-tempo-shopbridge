from __future__ import annotations

import importlib.util
import pathlib
import json
import tempfile
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "stamp-release-version.py"
SPEC = importlib.util.spec_from_file_location("agentcart_release_stamp", TOOL)
release_stamp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart_release_stamp"] = release_stamp
SPEC.loader.exec_module(release_stamp)


class ReleaseVersionStampTest(unittest.TestCase):
    def fixture(self, root):
        for name in ('package.json', 'gateway/package.json', 'package-lock.json', 'gateway/package-lock.json'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {'name': 'fixture', 'version': '1.22.0'}
            if 'lock' in name:
                data['packages'] = {'': {'version': '1.22.0'}}
            path.write_text(json.dumps(data))
        for name in ('woocommerce-shopbridge/agentcart-shopbridge', 'charts/agentcart-shopbridge/files/plugin'):
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            (path / 'agentcart-shopbridge.php').write_text('<?php\n/**\n * Version: 1.22.0\n */\n')
            (path / 'readme.txt').write_text('Stable tag: 1.22.0\n')
        for name in ('gateway/shopbridge-direct-skill', 'gateway/openclaw-skill', 'household-os/openclaw-skill'):
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            (path / 'SKILL.md').write_text('---\nname: fixture\nmetadata:\n  version: "1.22.0"\n---\n')
        for name in ('agentcart-shopbridge', 'agentcart-shopbridge-registry'):
            path = root / 'charts' / name
            path.mkdir(parents=True, exist_ok=True)
            (path / 'Chart.yaml').write_text('version: 1.22.0\nappVersion: "1.22.0"\n')

    def test_release_cohort_and_stale_chart_copy_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            with patch.object(release_stamp, 'ROOT', root):
                release_stamp.stamp_all('1.23.0', check=False)
                with self.assertRaisesRegex(ValueError, 'files/plugin'):
                    release_stamp.verify_versions('1.23.0')
                for name in ('agentcart-shopbridge.php', 'readme.txt'):
                    (root / 'charts/agentcart-shopbridge/files/plugin' / name).write_bytes((root / 'woocommerce-shopbridge/agentcart-shopbridge' / name).read_bytes())
                release_stamp.verify_versions('1.23.0')
                self.assertEqual(json.loads((root / 'package-lock.json').read_text())['packages']['']['version'], '1.23.0')
                skill = root / 'household-os/openclaw-skill/SKILL.md'
                skill.write_text(skill.read_text().replace('1.23.0', '1.22.0'))
                with self.assertRaisesRegex(ValueError, 'household-os'):
                    release_stamp.verify_versions('1.23.0')

    def test_bad_marker_prevents_partial_version_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            (root / 'household-os/openclaw-skill/SKILL.md').write_text('missing marker')
            before = (root / 'package.json').read_bytes()
            with patch.object(release_stamp, 'ROOT', root):
                self.assertEqual(release_stamp.main(['1.23.0']), 1)
            self.assertEqual((root / 'package.json').read_bytes(), before)

    def test_nested_skill_metadata_version_is_stamped(self) -> None:
        source = (
            "---\n"
            "name: shopbridge-direct\n"
            "description: Direct ShopBridge buyer skill.\n"
            "metadata:\n"
            '  version: "0.1.0-alpha"\n'
            "---\n"
        )

        updated = release_stamp.replace_once(
            source,
            release_stamp.SKILL_VERSION_PATTERN,
            r'\g<1>1.12.0\g<2>',
            "ShopBridge direct skill metadata",
        )

        self.assertIn('  version: "1.12.0"', updated)
        self.assertNotIn("0.1.0-alpha", updated)


if __name__ == "__main__":
    unittest.main()
