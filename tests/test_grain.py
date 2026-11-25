"""Unit tests for the Grain parser, typechecker, transpiler and pipeline hook."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "pipeline"))

from gramma_pipeline import generate, load_project  # noqa: E402
from gramma_pipeline.grain import (  # noqa: E402
    GrainError, check_grain, parse, tokenize, transpile_grain)
from gramma_pipeline.grain.typechecker import typecheck  # noqa: E402

SAMPLE = """
extern tileset hero_tileset

entity Hero {
    tileset: tileset = hero_tileset;
    speed: fixed = 1.0;
    jumps: int = 0;

    on_update(dt: fixed) {
        x += fmul(speed, dt);
        y /= speed;
        jumps += 1;
        if (pad_down(P1, RIGHT)) {
            set_frame(self, 1);
        }
    }

    on_draw() {
        show(self, 0, ftoi(x), ftoi(y));
    }
}

scene Field {
    on_load() {
        return;
    }
}

game {
    title = "Grain test";
    max_actors = 2;
    on_init() {
        load_scene(Field);
        spawn(Hero, itof(10), itof(20));
    }
}
"""


class LexerTests(unittest.TestCase):
    def test_tokens_and_positions(self):
        tokens = tokenize("entity Hero {\n  speed = 1.5; # hi\n}", "g.grain")
        kinds = [token.kind for token in tokens]
        self.assertIn("KW", kinds)
        self.assertIn("IDENT", kinds)
        self.assertIn("FIXED", kinds)
        fixed = next(token for token in tokens if token.kind == "FIXED")
        self.assertEqual(fixed.value, "1.5")
        self.assertEqual((fixed.pos.line, fixed.pos.col), (2, 11))

    def test_comment_and_block_comment_ignored(self):
        tokens = tokenize("/* a */ game { } # b", "g.grain")
        self.assertEqual([token.value for token in tokens[:-1]], ["game", "{", "}"])

    def test_bad_character_has_location(self):
        with self.assertRaises(GrainError) as caught:
            tokenize("game { @ }", "g.grain")
        self.assertEqual(caught.exception.pos.line, 1)
        self.assertIn("g.grain:1:", str(caught.exception))


class ParserTests(unittest.TestCase):
    def test_parses_sample(self):
        program = parse(SAMPLE, "sample.grain")
        self.assertEqual([e.name for e in program.entities], ["Hero"])
        self.assertEqual([s.name for s in program.scenes], ["Field"])
        self.assertEqual(program.game.settings["title"], "Grain test")
        entity = program.entities[0]
        self.assertEqual([f.name for f in entity.fields],
                         ["tileset", "speed", "jumps"])
        self.assertEqual(entity.handlers["on_update"].params,
                         [("dt", "fixed")])
        self.assertEqual(len(entity.handlers["on_update"].body), 4)

    def test_optional_colons_and_semicolons(self):
        program = parse("game: { title = \"x\"; }", "g.grain")
        self.assertEqual(program.game.settings["title"], "x")

    def test_reports_missing_brace(self):
        with self.assertRaises(GrainError) as caught:
            parse("entity Hero { speed = 1", "g.grain")
        self.assertIn("unterminated", caught.exception.message)


class TypeCheckerTests(unittest.TestCase):
    def test_valid_sample(self):
        program = parse(SAMPLE, "sample.grain")
        checker = typecheck(program, "sample.grain")
        self.assertEqual(checker.entity_fields["Hero"]["speed"], "fixed")
        assignment = program.entities[0].handlers["on_update"].body[0]
        self.assertEqual(checker.node_types[id(assignment.target)], "fixed")
        self.assertEqual(checker.type_of(assignment.value), "fixed")

    def test_check_grain_returns_no_errors_for_valid_source(self):
        self.assertEqual(check_grain(SAMPLE, "sample.grain"), [])

    def test_unknown_identifier(self):
        source = SAMPLE.replace("x += fmul(speed, dt);",
                                "x += fmul(nope, dt);")
        errors = check_grain(source, "sample.grain")
        self.assertEqual(len(errors), 1)
        self.assertIn("unknown identifier 'nope'", errors[0].message)

    def test_type_mismatch(self):
        source = SAMPLE.replace("jumps += 1;", "jumps = true;")
        errors = check_grain(source, "sample.grain")
        self.assertIn("expected int, got bool", errors[0].message)

    def test_builtin_arity(self):
        source = SAMPLE.replace("set_frame(self, 1);", "set_frame(self);")
        errors = check_grain(source, "sample.grain")
        self.assertIn("set_frame() expects 2", errors[0].message)

    def test_handler_signature(self):
        source = SAMPLE.replace("on_update(dt: fixed)",
                                "on_update(dt: int)")
        errors = check_grain(source, "sample.grain")
        self.assertIn("expects fixed", errors[0].message)

    def test_duplicate_entity(self):
        source = SAMPLE + "\nentity Hero { tileset: tileset = hero_tileset; }"
        errors = check_grain(source, "sample.grain")
        self.assertIn("duplicate declaration 'Hero'", errors[0].message)

    def test_reserved_field(self):
        source = SAMPLE.replace("jumps: int = 0;", "x: fixed = 0;")
        errors = check_grain(source, "sample.grain")
        self.assertIn("reserved engine field", errors[0].message)

    def test_missing_tileset_field(self):
        source = SAMPLE.replace("tileset: tileset = hero_tileset;", "")
        errors = check_grain(source, "sample.grain")
        self.assertIn("needs a 'tileset: tileset' field", errors[0].message)

    def test_scroll_requires_scene_fields(self):
        source = SAMPLE.replace("on_load() {", "on_update(dt: fixed) { scroll(0, 0); }\n    on_load() {")
        errors = check_grain(source, "sample.grain")
        self.assertIn("scroll() needs a scene", errors[0].message)

    def test_self_outside_handler(self):
        source = SAMPLE.replace("speed: fixed = 1.0;", "speed: fixed = self.x;")
        errors = check_grain(source, "sample.grain")
        self.assertIn("'self' is only available inside handlers",
                      errors[0].message)


class CodeGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.source = transpile_grain(SAMPLE, "sample.grain")

    def test_emits_api_calls(self):
        for fragment in (
            "extern const gr_tileset hero_tileset;",
            "static gr_actor *grain_spawn_Hero",
            "gr_actor_spawn(&def)",
            "gr_fmul(self->speed, dt)",
            "gr_fdiv(self->actor->y, self->speed)",
            "gr_pad_down(GR_PLAYER_1, GR_BTN_RIGHT)",
            "gr_sprite_show(&(self->actor)->sprite",
            "gr_scene_load(&grain_Field_scene)",
            "static const gr_config grain_config",
            "int main(void)",
        ):
            self.assertIn(fragment, self.source)

    def test_int_to_fixed_coercion(self):
        source = transpile_grain(SAMPLE.replace("itof(10)", "10"),
                                 "sample.grain")
        self.assertIn("grain_spawn_Hero(gr_itof(10)", source)

    def test_param_annotations_and_fixed_literals(self):
        self.assertIn("(gr_fixed)(GR_FIXED_ONE)", self.source.replace(
            "(gr_fixed)(GR_FIXED_ONE * 1)", "(gr_fixed)(GR_FIXED_ONE)"))
        self.assertIn("gr_fixed dt", self.source)

    def test_generated_source_is_c89_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grain_game.c"
            path.write_text(self.source, encoding="utf-8")
            command = ["gcc", "-std=c89", "-pedantic", "-Wall",
                       "-fsyntax-only", f"-I{ROOT / 'core' / 'include'}",
                       str(path)]
            try:
                result = subprocess.run(command, capture_output=True,
                                        text=True, check=False)
            except FileNotFoundError:
                self.skipTest("gcc not available")
            self.assertEqual(result.returncode, 0, result.stderr)


class PipelineIntegrationTests(unittest.TestCase):
    def test_load_project_discovers_grain_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "project.toml").write_text(
                "[project]\nname = 'temp'\n", encoding="utf-8")
            (root / "src" / "one.grain").write_text(SAMPLE, encoding="utf-8")
            project = load_project(root)
            self.assertEqual([p.name for p in project.grain_sources],
                             ["one.grain"])

    def test_generate_emits_and_lists_generated_c(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "project.toml").write_text(
                "[project]\nname = 'temp'\n\n[grain]\n"
                "sources = ['src/game.grain']\n", encoding="utf-8")
            (root / "src" / "game.grain").write_text(SAMPLE, encoding="utf-8")
            manifest = generate(root, "pc")
            output = root / "generated" / "pc"
            self.assertTrue((output / "grain_game.c").is_file())
            self.assertIn("'grain_game.c'",
                          (output / "meson.build").read_text())
            grain = manifest["grain"][0]
            self.assertEqual(grain["entities"], ["Hero"])
            self.assertEqual(grain["scenes"], ["Field"])

    def test_generate_reports_grain_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "project.toml").write_text(
                "[project]\nname = 'temp'\n", encoding="utf-8")
            (root / "src" / "bad.grain").write_text(
                "game { title = 1; }", encoding="utf-8")
            with self.assertRaises(GrainError) as caught:
                generate(root, "pc")
            self.assertIn("'title' must be a string", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
