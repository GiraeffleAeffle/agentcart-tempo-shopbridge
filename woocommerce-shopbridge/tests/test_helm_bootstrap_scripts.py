from __future__ import annotations

import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP_DIR = REPO_ROOT / "charts" / "agentcart-shopbridge" / "files" / "bootstrap"
PREPARE = (BOOTSTRAP_DIR / "prepare-wordpress.sh").read_text()
SEED = (BOOTSTRAP_DIR / "seed-before-start.sh").read_text()
NGINX = (REPO_ROOT / "charts" / "agentcart-shopbridge" / "files" / "nginx.conf").read_text()


class HelmBootstrapScriptTests(unittest.TestCase):
    def test_nginx_allows_only_hash_addressed_registry_archive_documents(self) -> None:
        archive_location = (
            r'location ~ "^/\.well-known/agentcart-registry-records/[0-9a-f]{64}\.json$" '
            r"{ try_files $uri /index.php?$args; }"
        )

        self.assertIn(archive_location, NGINX)
        self.assertLess(NGINX.index(archive_location), NGINX.index(r"location ~ /\. { deny all; }"))

    def test_wp_cli_wrapper_is_installed_only_after_source_checksums_pass(self) -> None:
        wrapper_copy = 'cp /usr/local/bin/wp "$site/wp-cli.phar"'

        self.assertNotIn(wrapper_copy, PREPARE)
        self.assertIn(wrapper_copy, SEED)
        self.assertLess(SEED.index("wp core verify-checksums"), SEED.index(wrapper_copy))
        self.assertLess(SEED.index("wp plugin verify-checksums woocommerce"), SEED.index(wrapper_copy))
        self.assertLess(SEED.index(wrapper_copy), SEED.index('touch "$site/.agentcart-seeded"'))


if __name__ == "__main__":
    unittest.main()
