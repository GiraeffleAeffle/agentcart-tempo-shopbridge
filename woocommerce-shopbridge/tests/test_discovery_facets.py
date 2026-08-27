import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
FACETS_MODULE = (
    ROOT
    / "woocommerce-shopbridge"
    / "agentcart-shopbridge"
    / "includes"
    / "class-agentcart-shopbridge-discovery-facets.php"
)


@unittest.skipUnless(shutil.which("php"), "php is required for discovery facets behavior tests")
class DiscoveryFacetsBehaviorTests(unittest.TestCase):
    def run_php(self, body: str) -> dict:
        script = f"""<?php
define('ABSPATH', '/');
require {json.dumps(str(FACETS_MODULE))};
{body}
"""
        completed = subprocess.run(
            ["php"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_derives_facets_from_exposed_catalog_snapshot(self) -> None:
        result = self.run_php(
            """
$snapshot = ['products' => [
    ['category_slugs' => ['tea', 'beverages']],
    ['category_slugs' => ['tea', 'gift_sets']],
    ['category_slugs' => ['coffee beans', 'ignored!']],
]];
echo json_encode(AgentCart_ShopBridge_Discovery_Facets::from_exposure_snapshot($snapshot));
"""
        )

        self.assertEqual(
            result["categories"], ["beverages", "coffee-beans", "gift-sets", "tea"]
        )
        self.assertEqual(result["coverage"], "complete")
        self.assertFalse(result["truncated"])

    def test_caps_categories_and_validates_consistency(self) -> None:
        result = self.run_php(
            """
$snapshot = ['products' => []];
for ($i = 0; $i < 10; $i++) {
    $snapshot['products'][] = ['category_slugs' => ['category-' . $i]];
}
$facets = AgentCart_ShopBridge_Discovery_Facets::from_exposure_snapshot($snapshot);
echo json_encode([
    'facets' => $facets,
    'errors' => AgentCart_ShopBridge_Discovery_Facets::validate($facets),
]);
"""
        )

        self.assertEqual(len(result["facets"]["categories"]), 8)
        self.assertEqual(result["facets"]["coverage"], "partial")
        self.assertTrue(result["facets"]["truncated"])
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
