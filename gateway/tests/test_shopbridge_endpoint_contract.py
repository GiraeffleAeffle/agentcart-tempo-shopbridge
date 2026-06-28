from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-shopbridge-endpoint-contract.py"
CONTRACT_PATH = ROOT_DIR / "gateway" / "config" / "shopbridge_endpoint_contract.json"
SPEC = importlib.util.spec_from_file_location("shopbridge_endpoint_contract_tool", TOOL_PATH)
shopbridge_endpoint_contract_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["shopbridge_endpoint_contract_tool"] = shopbridge_endpoint_contract_tool
SPEC.loader.exec_module(shopbridge_endpoint_contract_tool)


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


class ShopBridgeEndpointContractTest(unittest.TestCase):
    def test_checked_in_contract_is_valid(self) -> None:
        errors = shopbridge_endpoint_contract_tool.validate_contract(load_contract())

        self.assertEqual([], errors)

    def test_expected_endpoint_ids_are_pinned(self) -> None:
        contract = load_contract()
        endpoint_ids = {endpoint["id"] for endpoint in contract["endpoints"]}

        self.assertTrue(shopbridge_endpoint_contract_tool.EXPECTED_ENDPOINTS.issubset(endpoint_ids))

    def test_missing_fixture_response_field_fails(self) -> None:
        contract = load_contract()
        mutated = copy.deepcopy(contract)
        quote = next(endpoint for endpoint in mutated["endpoints"] if endpoint["id"] == "quote")
        quote["fixtures"]["response"]["payment_requirements"].pop("payment_contract_hash")

        errors = shopbridge_endpoint_contract_tool.validate_contract(mutated)

        self.assertTrue(any("quote: fixture response missing payment_requirements.payment_contract_hash" in error for error in errors), errors)

    def test_missing_invariant_fails(self) -> None:
        contract = load_contract()
        mutated = copy.deepcopy(contract)
        mutated["invariants"] = [
            invariant
            for invariant in mutated["invariants"]
            if invariant["id"] != "checkout_requires_quote_hash_and_idempotency"
        ]

        errors = shopbridge_endpoint_contract_tool.validate_contract(mutated)

        self.assertTrue(any("checkout_requires_quote_hash_and_idempotency" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
