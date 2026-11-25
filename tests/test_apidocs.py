"""Tests for generated API reference docs."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from gramma_pipeline.apidocs import build_api_reference  # noqa: E402


class ApiDocsTests(unittest.TestCase):
    def test_reference_is_deterministic_and_current(self):
        text = build_api_reference(ROOT)
        self.assertEqual(text, build_api_reference(ROOT))
        path = ROOT / "docs" / "generated" / "api-reference.md"
        self.assertTrue(path.is_file(), "run ./tools/gr/gr docs")
        self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_generated_reference_is_not_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("!docs/generated/", ignore)
        self.assertIn("!docs/generated/api-reference.md", ignore)

    def test_reference_indexes_public_api(self):
        text = build_api_reference(ROOT)
        for name in ("gr_init", "gr_sprite_show", "gr_overlay_flush",
                     "gr_bank_select", "gr_nes_mapper_runtime_id",
                     "gr_gb_mapper_runtime_id", "gr_sms_mapper_runtime_init"):
            self.assertIn(f"#### `{name}`", text)
        self.assertIn("Game Boy mapper", text)
        self.assertIn("NES mapper", text)
        self.assertIn("SMS/GG mapper", text)
        self.assertNotIn("internal/backend.h", text)

    def test_cli_check_accepts_current_reference(self):
        result = subprocess.run(
            [str(ROOT / "tools" / "gr" / "gr"), "docs", "--check"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up to date", result.stdout)


if __name__ == "__main__":
    unittest.main()
