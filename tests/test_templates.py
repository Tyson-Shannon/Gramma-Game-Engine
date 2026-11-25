"""Tests for the `gr new` starter templates."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_pipeline import generate, load_project  # noqa: E402
from gramma_pipeline.grain import check_grain  # noqa: E402
from gramma_cli.template import TEMPLATES, create_project  # noqa: E402


class TemplateTests(unittest.TestCase):
    def test_all_templates_are_playable_projects(self):
        for name, spec in TEMPLATES.items():
            with self.subTest(template=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "demo"
                create_project(root, "demo", name)
                self.assertTrue((root / "README.md").is_file())
                self.assertTrue((root / spec["source_path"]).is_file())
                self.assertTrue((root / "assets" / "hero.png").is_file())
                self.assertTrue((root / "assets" / "ground.png").is_file())
                self.assertTrue((root / "assets" / "blip.wav").is_file())
                self.assertIn("subdir('generated/' + target)",
                              (root / "meson.build").read_text(
                                  encoding="utf-8"))
                project = load_project(root)
                self.assertEqual(project.name, "demo")
                manifest = generate(root, "pc", project)
                self.assertTrue((root / "generated" / "pc" / "meson.build")
                                .is_file())
                if name.startswith("grain"):
                    self.assertEqual(manifest["grain"][0]["file"],
                                     "grain_game.c")
                else:
                    self.assertNotIn("grain", manifest)
                if name == "grain-music":
                    self.assertTrue((root / "assets" / "theme.tick").is_file())
                    self.assertIn(
                        "music", [asset["kind"] for asset in manifest["assets"]])

    def test_grain_templates_typecheck(self):
        for name in ("grain", "grain-music"):
            with self.subTest(template=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "demo"
                create_project(root, "demo", name)
                source = (root / "src" / "game.grain").read_text(
                    encoding="utf-8")
                self.assertEqual(check_grain(source, "game.grain"), [])

    def test_c_template_is_c89_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "demo"
            create_project(root, "demo", "c")
            result = subprocess.run(
                ["gcc", "-std=c89", "-pedantic", "-Wall", "-Wextra",
                 "-fsyntax-only", "-I", str(ROOT / "core" / "include"),
                 str(root / "src" / "main.c")],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_template_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown template"):
                create_project(Path(tmp) / "demo", "demo", "missing")


if __name__ == "__main__":
    unittest.main()
