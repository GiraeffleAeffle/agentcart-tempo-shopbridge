import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
IDENTITY_MODULE = (
    ROOT
    / "woocommerce-shopbridge"
    / "agentcart-shopbridge"
    / "includes"
    / "class-agentcart-shopbridge-onchain-identity.php"
)


@unittest.skipUnless(shutil.which("php"), "php is required for onchain identity behavior tests")
class OnchainIdentityBehaviorTests(unittest.TestCase):
    def run_php(self, body: str) -> dict:
        script = f"""<?php
require {json.dumps(str(IDENTITY_MODULE))};
{body}
"""
        completed = subprocess.run(
            ["php"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_valid_public_identity_is_canonical_and_complete(self) -> None:
        result = self.run_php(
            """
$identity = AgentCart_ShopBridge_Onchain_Identity::compose(
    '0x1234567890ABCDEF1234567890ABCDEF12345678',
    'eip155:42431',
    '0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD',
    '0x' . str_repeat('AB', 32)
);
echo json_encode($identity);
"""
        )

        self.assertEqual(
            result,
            {
                "controller": "0x1234567890abcdef1234567890abcdef12345678",
                "chain_id": "eip155:42431",
                "registry_address": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
                "record_id": "0x" + "ab" * 32,
                "standard": "AgentCart-Onchain-Registry-v1",
            },
        )

    def test_partial_or_invalid_identity_is_not_advertised(self) -> None:
        result = self.run_php(
            """
echo json_encode([
    'partial' => AgentCart_ShopBridge_Onchain_Identity::compose(
        '0x1234567890abcdef1234567890abcdef12345678',
        'eip155:42431',
        '',
        ''
    ),
    'zero_address' => AgentCart_ShopBridge_Onchain_Identity::sanitize_address(
        '0x0000000000000000000000000000000000000000'
    ),
    'bad_chain' => AgentCart_ShopBridge_Onchain_Identity::sanitize_chain_id('42431'),
    'zero_record' => AgentCart_ShopBridge_Onchain_Identity::sanitize_record_id(
        '0x' . str_repeat('0', 64)
    ),
]);
"""
        )

        self.assertEqual(
            result,
            {"partial": [], "zero_address": "", "bad_chain": "", "zero_record": ""},
        )


if __name__ == "__main__":
    unittest.main()
