"""Smoke tests for the VS Code Grain syntax/diagnostics extension."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "editors" / "vscode-grain"


class VSCodeGrainTests(unittest.TestCase):
    def test_manifest_declares_language_grammar_and_setting(self):
        manifest = json.loads((EXTENSION / "package.json").read_text(
            encoding="utf-8"))
        language = manifest["contributes"]["languages"][0]
        self.assertEqual(language["id"], "grain")
        self.assertIn(".grain", language["extensions"])
        grammar = manifest["contributes"]["grammars"][0]
        self.assertEqual(grammar["scopeName"], "source.grain")
        self.assertTrue((EXTENSION / grammar["path"]).is_file())
        self.assertEqual(manifest["main"], "./extension.js")
        self.assertIn("grain.cliPath",
                      manifest["contributes"]["configuration"]["properties"])
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertTrue((EXTENSION / "lsp-client.js").is_file())

    def test_language_configuration_is_valid_json(self):
        config = json.loads((EXTENSION / "language-configuration.json").read_text(
            encoding="utf-8"))
        self.assertEqual(config["comments"]["lineComment"], "#")
        self.assertIn(["{", "}"], config["brackets"])

    def test_grammar_uses_grain_scope(self):
        grammar = json.loads((EXTENSION / "syntaxes" /
                              "grain.tmLanguage.json").read_text(
                                  encoding="utf-8"))
        self.assertEqual(grammar["scopeName"], "source.grain")
        includes = [item["include"] for item in grammar["patterns"]]
        self.assertIn("#keywords", includes)
        self.assertIn("#builtins", includes)

    def test_diagnostics_parser(self):
        try:
            result = subprocess.run(
                ["node", str(EXTENSION / "test.js")],
                cwd=ROOT, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            self.skipTest("node not available")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LSP framing OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
