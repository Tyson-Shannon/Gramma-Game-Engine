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
from gramma_pipeline.grain.ast import ArrayLiteral, Index, VarDecl  # noqa: E402
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

V1_SAMPLE = """
extern tileset hero_tileset

func twice(v: int) -> int {
    return v * 2;
}

func step(speed: fixed, dt: fixed) -> fixed {
    var scaled: fixed = fmul(speed, dt);
    return scaled;
}

entity Hero {
    tileset: tileset = hero_tileset;
    frames: int[2] = [0, 1];

    on_update(dt: fixed) {
        var amount: fixed = step(1.0, dt);
        x += amount;
        frames[0] = twice(frames[0]);
        show(self, 0, ftoi(x), frames[0]);
    }

    on_draw() {
        set_frame(self, frames[0]);
    }
}

game {
    title = "Grain v1";
    on_init() {
        spawn(Hero, itof(0), itof(0));
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

    def test_v1_keywords_and_arrow(self):
        tokens = tokenize("func f(a: int) -> int { var n: int = a; }",
                          "g.grain")
        keywords = [t.value for t in tokens if t.kind == "KW"]
        self.assertIn("func", keywords)
        self.assertIn("var", keywords)
        self.assertIn("->", [t.value for t in tokens if t.kind == "OP"])


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

    def test_parses_v1_functions_locals_and_arrays(self):
        program = parse(V1_SAMPLE, "v1.grain")
        self.assertEqual([f.name for f in program.functions], ["twice", "step"])
        self.assertEqual(program.functions[1].return_type, "fixed")
        entity = program.entities[0]
        self.assertEqual(entity.fields[1].name, "frames")
        self.assertEqual(entity.fields[1].type_name, "int[2]")
        self.assertIsInstance(entity.fields[1].init, ArrayLiteral)
        update = entity.handlers["on_update"].body
        self.assertIsInstance(update[0], VarDecl)
        self.assertEqual(update[0].type_name, "fixed")
        self.assertIsInstance(update[2].target, Index)

    def test_rejects_multidimensional_arrays(self):
        source = V1_SAMPLE.replace("int[2]", "int[2][3]")
        with self.assertRaises(GrainError) as caught:
            parse(source, "v1.grain")
        self.assertIn("multidimensional arrays", caught.exception.message)


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

    def test_valid_v1_sample(self):
        program = parse(V1_SAMPLE, "v1.grain")
        checker = typecheck(program, "v1.grain")
        self.assertEqual(checker.functions["twice"], (["int"], "int"))
        update = program.entities[0].handlers["on_update"].body
        self.assertEqual(checker.type_of(update[0]), "fixed")
        self.assertEqual(checker.type_of(update[2].target), "int")
        self.assertEqual(check_grain(V1_SAMPLE, "v1.grain"), [])

    def test_unknown_function(self):
        source = V1_SAMPLE.replace("step(1.0, dt)", "missing(1.0, dt)")
        errors = check_grain(source, "v1.grain")
        self.assertIn("unknown function 'missing'", errors[0].message)

    def test_user_function_arity(self):
        source = V1_SAMPLE.replace("twice(frames[0])", "twice()")
        errors = check_grain(source, "v1.grain")
        self.assertIn("twice() expects 1 argument(s)", errors[0].message)

    def test_return_type_mismatch(self):
        source = V1_SAMPLE.replace("return v * 2;", "return true;")
        errors = check_grain(source, "v1.grain")
        self.assertIn("return value: expected int, got bool",
                      errors[0].message)

    def test_void_function_cannot_return_value(self):
        source = V1_SAMPLE.replace(
            "func twice", "func ping() -> void {\n    return 1;\n}\n\nfunc twice",
            1)
        errors = check_grain(source, "v1.grain")
        self.assertIn("cannot return a value", errors[0].message)

    def test_array_length_and_index_types(self):
        short = V1_SAMPLE.replace("frames: int[2] = [0, 1];",
                                  "frames: int[2] = [0];")
        self.assertIn("expected 2", check_grain(short, "v1.grain")[0].message)
        bad_index = V1_SAMPLE.replace("frames[0] = twice(frames[0]);",
                                      "frames[true] = twice(frames[0]);")
        self.assertIn("array index must be an int",
                      check_grain(bad_index, "v1.grain")[0].message)

    def test_duplicate_local_and_whole_array_assignment(self):
        duplicate = V1_SAMPLE.replace(
            "var amount: fixed = step(1.0, dt);",
            "var amount: fixed = step(1.0, dt);\n        var amount: int = 1;")
        self.assertIn("duplicate local variable 'amount'",
                      check_grain(duplicate, "v1.grain")[0].message)
        whole_array = V1_SAMPLE.replace("frames[0] = twice(frames[0]);",
                                        "frames = [0, 1];")
        self.assertIn("cannot assign to a whole array",
                      check_grain(whole_array, "v1.grain")[0].message)

    def test_self_and_void_values_in_functions(self):
        self_source = V1_SAMPLE.replace(
            "func twice", "func bad() -> int {\n    return self.x;\n}\n\nfunc twice",
            1)
        self.assertIn("'self' is only available inside handlers",
                      check_grain(self_source, "v1.grain")[0].message)
        void_source = V1_SAMPLE.replace(
            "var amount: fixed = step(1.0, dt);",
            "var amount: fixed = music_stop();")
        self.assertIn("cannot have a void initializer",
                      check_grain(void_source, "v1.grain")[0].message)


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


class V1CodeGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.source = transpile_grain(V1_SAMPLE, "v1.grain")

    def test_emits_function_prototypes_and_definitions(self):
        for fragment in (
            "static int grain_fn_twice(int v);",
            "static gr_fixed grain_fn_step(gr_fixed speed, gr_fixed dt);",
            "static int grain_fn_twice(int v)",
            "static gr_fixed grain_fn_step(gr_fixed speed, gr_fixed dt)",
            "amount = grain_fn_step(",
            "self->frames[0] = grain_fn_twice(self->frames[0]);",
        ):
            self.assertIn(fragment, self.source)

    def test_emits_fixed_array_fields_and_locals(self):
        self.assertIn("int frames[2];", self.source)
        self.assertIn("data->frames[0] = 0;", self.source)
        self.assertIn("data->frames[1] = 1;", self.source)
        self.assertIn("gr_fixed amount;", self.source)
        declaration = self.source.index("gr_fixed amount;")
        assignment = self.source.index("amount = grain_fn_step(")
        self.assertLess(declaration, assignment)

    def test_v1_generated_source_is_c89_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grain_v1.c"
            path.write_text(self.source, encoding="utf-8")
            command = ["gcc", "-std=c89", "-pedantic", "-Wall", "-Wextra",
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
