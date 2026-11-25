"""Conformance tests for the versioned host-side backend contract."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_cli.service import METHODS, ServiceError, dispatch  # noqa: E402
from gramma_pipeline import (MANIFEST_SCHEMA_VERSION,  # noqa: E402
                             PROJECT_SCHEMA_VERSION,
                             SERVICE_CONTRACT_VERSION,
                             check_budget_detailed, load_project)

TEST_KART = ROOT / "examples" / "test-kart"
GRAIN_DEMO = ROOT / "examples" / "grain-demo"


class BackendContractTests(unittest.TestCase):
    def test_service_version_and_capabilities(self):
        version = dispatch("service.version")
        self.assertEqual(version["service"], "gramma")
        self.assertEqual(version["contract_version"], SERVICE_CONTRACT_VERSION)
        self.assertEqual(version["project_schema_version"],
                         PROJECT_SCHEMA_VERSION)
        self.assertEqual(version["manifest_schema_version"],
                         MANIFEST_SCHEMA_VERSION)
        self.assertEqual(set(version["methods"]), set(METHODS))

        capabilities = dispatch("service.capabilities")
        self.assertEqual(capabilities["transport"], "jsonrpc-2.0/ndjson")
        self.assertFalse(capabilities["gui_framework_dependency"])
        self.assertIn("pc", capabilities["targets"])
        self.assertIn("grain", capabilities["templates"])

    def test_project_open_reports_schema_and_assets(self):
        result = dispatch("project.open", {"project": str(TEST_KART)})
        self.assertEqual(result["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(result["project"]["name"], "test-kart")
        self.assertTrue(result["assets"]["image"])
        self.assertTrue(result["assets"]["audio"])
        self.assertTrue(result["assets"]["music"])

    def test_check_returns_structured_manifest_and_violations(self):
        result = dispatch("check", {"project": str(TEST_KART),
                                    "target": "pc"})
        self.assertTrue(result["ok"], result["violations"])
        self.assertEqual(result["violations"], [])
        manifest = result["manifest"]
        self.assertEqual(manifest["schema_version"], MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest["artifacts"]["directory"],
                         str((TEST_KART / "generated" / "pc").resolve()))
        for source in manifest["artifacts"]["sources"]:
            self.assertTrue(Path(source).is_file(), source)

        manifest["totals"]["rom_bytes"] = 10 ** 9
        violations = check_budget_detailed(
            load_project(TEST_KART), "pc", manifest)
        rom = [item for item in violations if item["code"] == "budget.rom"]
        self.assertEqual(len(rom), 1)
        self.assertEqual(rom[0]["category"], "rom")
        self.assertEqual(rom[0]["severity"], "error")
        self.assertIn("exceeds", rom[0]["message"])

    def test_grain_check_returns_structured_diagnostics(self):
        bad = dispatch("grain.check", {
            "text": "entity X { speed: fixed = missing; }",
            "source": "bad.grain",
        })
        self.assertFalse(bad["ok"])
        diagnostic = bad["diagnostics"][0]
        self.assertEqual(diagnostic["code"], "grain.error")
        self.assertEqual(diagnostic["severity"], "error")
        self.assertEqual(diagnostic["filename"], "bad.grain")
        self.assertGreaterEqual(diagnostic["line"], 1)
        self.assertGreaterEqual(diagnostic["col"], 1)

        good = dispatch("grain.check", {"project": str(GRAIN_DEMO)})
        self.assertTrue(good["ok"], good["results"])

    def test_project_save_rejects_newer_schema_without_writing(self):
        content = (TEST_KART / "project.toml").read_text(encoding="utf-8")
        content = content.replace("schema_version = 1", "schema_version = 99")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project.toml").write_text(content, encoding="utf-8")
            with self.assertRaises(ServiceError) as caught:
                dispatch("project.save", {"project": str(root),
                                          "content": content})
            self.assertEqual(caught.exception.code, "unsupported_schema")
            self.assertEqual(
                (root / "project.toml").read_text(encoding="utf-8"), content)

    def test_unknown_method_is_method_not_found(self):
        with self.assertRaises(ServiceError) as caught:
            dispatch("project.nope")
        self.assertEqual(caught.exception.code, "method_not_found")
        self.assertEqual(caught.exception.rpc_code, -32601)

    def test_ndjson_stdio_round_trip(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "service.version",
             "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "project.nope",
             "params": {}},
        ]
        payload = "".join(json.dumps(item) + "\n" for item in requests)
        result = subprocess.run(
            [str(ROOT / "tools" / "gr" / "gr"), "serve"],
            cwd=ROOT, input=payload, capture_output=True, text=True,
            check=False, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["id"], 1)
        self.assertEqual(replies[0]["result"]["contract_version"],
                         SERVICE_CONTRACT_VERSION)
        self.assertEqual(replies[1]["id"], 2)
        self.assertEqual(replies[1]["error"]["code"], -32601)

    def test_schema_documents_are_present_and_current(self):
        schema_dir = ROOT / "schemas"
        manifest_schema = json.loads(
            (schema_dir / "manifest.schema.json").read_text(encoding="utf-8"))
        project_schema = json.loads(
            (schema_dir / "project.schema.json").read_text(encoding="utf-8"))
        contract = json.loads(
            (schema_dir / "service-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest_schema["properties"]["schema_version"]["const"],
            MANIFEST_SCHEMA_VERSION)
        self.assertEqual(project_schema["properties"]["schema_version"]["const"],
                         PROJECT_SCHEMA_VERSION)
        self.assertEqual(contract["contract_version"], SERVICE_CONTRACT_VERSION)
        self.assertEqual(set(contract["methods"]), set(METHODS))


if __name__ == "__main__":
    unittest.main()
