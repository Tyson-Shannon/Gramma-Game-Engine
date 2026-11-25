"""Tests for the dependency-free Grain language server."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_cli.lsp import (  # noqa: E402
    LanguageServer, encode, read_messages)

SOURCE = """extern tileset kart_tileset

entity Kart {
    speed: fixed = 1.0;

    on_update(dt: fixed) {
        var step: fixed = fmul(speed, dt);
    }
}
"""
URI = "file:///tmp/game.grain"


class LanguageServerTests(unittest.TestCase):
    def setUp(self):
        self.server = LanguageServer()
        self.replies(self._open(SOURCE))

    def replies(self, message: dict) -> list[dict]:
        return self.server.process(message)

    def _open(self, text: str) -> dict:
        return {
            "jsonrpc": "2.0", "id": 1, "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": URI, "languageId": "grain",
                                        "version": 1, "text": text}},
        }

    def _request(self, method: str, params: dict, identifier: int = 2) -> dict:
        replies = self.replies({"jsonrpc": "2.0", "id": identifier,
                                "method": method, "params": params})
        self.assertEqual(len(replies), 1)
        self.assertNotIn("error", replies[0])
        return replies[0]["result"]

    def test_initialize_advertises_editor_features(self):
        capabilities = self._request("initialize", {})["capabilities"]
        self.assertTrue(capabilities["definitionProvider"])
        self.assertTrue(capabilities["renameProvider"])
        self.assertTrue(capabilities["completionProvider"]["triggerCharacters"])

    def test_open_publishes_diagnostics(self):
        replies = self.replies(self._open(
            "entity Kart { speed: fixed = missing; }\n"))
        self.assertEqual(replies[0]["method"],
                         "textDocument/publishDiagnostics")
        self.assertTrue(replies[0]["params"]["diagnostics"])

    def test_definition_finds_field_declaration(self):
        result = self._request("textDocument/definition", {
            "textDocument": {"uri": URI},
            "position": {"line": 6, "character": 31},
        })
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["range"]["start"],
                         {"line": 3, "character": 4})

    def test_definition_finds_extern_declaration(self):
        text = SOURCE + "\nfunc use() -> fixed {\n    return fmul(kart_tileset, 1);\n}\n"
        self.replies(self._open(text))
        result = self._request("textDocument/definition", {
            "textDocument": {"uri": URI},
            "position": {"line": 11, "character": 16},
        })
        self.assertEqual(result[0]["range"]["start"],
                         {"line": 0, "character": 15})

    def test_rename_updates_declaration_and_uses(self):
        result = self._request("textDocument/rename", {
            "textDocument": {"uri": URI},
            "position": {"line": 6, "character": 31},
            "newName": "velocity",
        })
        edits = result["changes"][URI]
        self.assertEqual(len(edits), 2)
        self.assertEqual({edit["newText"] for edit in edits}, {"velocity"})
        self.assertEqual({edit["range"]["start"]["line"] for edit in edits},
                         {3, 6})

    def test_completion_offers_builtins_and_context_symbols(self):
        result = self._request("textDocument/completion", {
            "textDocument": {"uri": URI},
            "position": {"line": 6, "character": 44},
        })
        labels = {item["label"] for item in result}
        self.assertIn("fmul", labels)
        self.assertIn("step", labels)
        self.assertIn("speed", labels)

    def test_document_symbols_include_entity_fields(self):
        result = self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": URI},
        })
        names = {symbol["name"] for symbol in result}
        self.assertTrue({"Kart", "speed", "step", "dt"} <= names)

    def test_json_rpc_framing_round_trip(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "shutdown"},
                    {"jsonrpc": "2.0", "method": "exit"}]
        stream = io.BytesIO(b"".join(encode(message) for message in messages))
        self.assertEqual(list(read_messages(stream)), messages)

    def test_cli_lsp_answers_requests(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
            {"jsonrpc": "2.0", "method": "exit", "params": {}},
        ]
        payload = b"".join(encode(message) for message in requests)
        result = subprocess.run(
            [str(ROOT / "tools" / "gr" / "gr"), "lsp"],
            cwd=ROOT, input=payload, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = list(read_messages(io.BytesIO(result.stdout)))
        self.assertEqual([reply.get("id") for reply in replies], [1, 2])
        self.assertTrue(replies[0]["result"]["capabilities"]["renameProvider"])


if __name__ == "__main__":
    unittest.main()
