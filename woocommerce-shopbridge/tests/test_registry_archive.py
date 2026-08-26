import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ARCHIVE_MODULE = (
    ROOT
    / "woocommerce-shopbridge"
    / "agentcart-shopbridge"
    / "includes"
    / "class-agentcart-shopbridge-registry-archive.php"
)


@unittest.skipUnless(shutil.which("php"), "php is required for registry archive behavior tests")
class RegistryArchiveBehaviorTests(unittest.TestCase):
    def run_php(self, body: str) -> dict:
        script = f"""<?php
define('ABSPATH', '/');
require {json.dumps(str(ARCHIVE_MODULE))};
{body}
"""
        completed = subprocess.run(
            ["php"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_record_hash_round_trips_through_an_immutable_public_path(self) -> None:
        record_hash = "ab" * 32
        result = self.run_php(
            f"""
$hash = {json.dumps(record_hash)};
$path = AgentCart_ShopBridge_Registry_Archive::immutable_path($hash);
echo json_encode([
    'path' => $path,
    'parsed_hash' => AgentCart_ShopBridge_Registry_Archive::hash_from_path($path),
]);
"""
        )

        self.assertEqual(
            result,
            {
                "path": f"/.well-known/agentcart-registry-records/{record_hash}.json",
                "parsed_hash": record_hash,
            },
        )

    def test_archived_records_are_idempotent_and_immutable(self) -> None:
        record_hash = "cd" * 32
        record = {"merchant_id": "tea.example", "domain": "tea.example"}
        result = self.run_php(
            f"""
$hash = {json.dumps(record_hash)};
$record = json_decode({json.dumps(json.dumps(record))}, true);
$archive = AgentCart_ShopBridge_Registry_Archive::put([], $hash, $record, '2026-08-26T12:00:00Z');
$archive = AgentCart_ShopBridge_Registry_Archive::put($archive, $hash, $record, '2026-08-26T13:00:00Z');
$conflict = '';
try {{
    AgentCart_ShopBridge_Registry_Archive::put(
        $archive,
        $hash,
        ['merchant_id' => 'other.example'],
        '2026-08-26T14:00:00Z'
    );
}} catch (RuntimeException $error) {{
    $conflict = $error->getMessage();
}}
echo json_encode([
    'entry' => AgentCart_ShopBridge_Registry_Archive::get($archive, $hash),
    'count' => count($archive),
    'conflict' => $conflict,
]);
"""
        )

        self.assertEqual(result["entry"]["record"], record)
        self.assertEqual(result["entry"]["archived_at"], "2026-08-26T12:00:00Z")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["conflict"], "immutable registry record hash collision")

    def test_invalid_hashes_are_rejected(self) -> None:
        result = self.run_php(
            """
$error = '';
try {
    AgentCart_ShopBridge_Registry_Archive::immutable_path('../record');
} catch (InvalidArgumentException $exception) {
    $error = $exception->getMessage();
}
echo json_encode(['error' => $error]);
"""
        )

        self.assertEqual(result["error"], "registry record hash must be 64 lowercase hex characters")


if __name__ == "__main__":
    unittest.main()
