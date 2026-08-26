from __future__ import annotations

import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP_DIR = REPO_ROOT / "charts" / "agentcart-shopbridge" / "files" / "bootstrap"
PREPARE = (BOOTSTRAP_DIR / "prepare-wordpress.sh").read_text()
SEED = (BOOTSTRAP_DIR / "seed-before-start.sh").read_text()


class HelmBootstrapScriptTests(unittest.TestCase):
    def test_wp_cli_wrapper_is_installed_only_after_source_checksums_pass(self) -> None:
        wrapper_copy = 'cp /usr/local/bin/wp "$site/wp-cli.phar"'

        self.assertNotIn(wrapper_copy, PREPARE)
        self.assertIn(wrapper_copy, SEED)
        self.assertLess(SEED.index("wp core verify-checksums"), SEED.index(wrapper_copy))
        self.assertLess(SEED.index("wp plugin verify-checksums woocommerce"), SEED.index(wrapper_copy))
        self.assertLess(SEED.index(wrapper_copy), SEED.index('touch "$site/.agentcart-seeded"'))


if __name__ == "__main__":
    unittest.main()
