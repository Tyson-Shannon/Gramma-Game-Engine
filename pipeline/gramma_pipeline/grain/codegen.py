"""Ahead-of-time C code generation for Grain v1.

Generated sources are plain C89 calls into `gramma/gramma.h`; there is no
interpreter or runtime table shipped to a console. The output deliberately
uses only declarations-at-block-start and ``/* */`` comments so it compiles on
cc65 and GBDK-2020 as well as the host compiler.
"""

from __future__ import annotations

import json
from fractions import Fraction

from .ast import (
    ArrayLiteral, Assign, Attr, Binary, Call, EntityDecl, Expr, ExprStmt,
    FieldDecl, FunctionDecl, GameDecl, Handler, IfStmt, Index, Literal, Name,
    Program, ReturnStmt, SceneDecl, Stmt, Unary, VarDecl, WhileStmt)
from .errors import GrainError, SourcePos
from .parser import parse
from .types import array_parts, is_array_type
from .typechecker import ENGINE_FIELDS, TypeChecker, typecheck

BUTTON_MACROS = {
    "UP": "GR_BTN_UP", "DOWN": "GR_BTN_DOWN", "LEFT": "GR_BTN_LEFT",
    "RIGHT": "GR_BTN_RIGHT", "A": "GR_BTN_A", "B": "GR_BTN_B",
    "X": "GR_BTN_X", "Y": "GR_BTN_Y", "L": "GR_BTN_L", "R": "GR_BTN_R",
    "START": "GR_BTN_START", "SELECT": "GR_BTN_SELECT",
}
PLAYER_MACROS = {"P1": "GR_PLAYER_1", "P2": "GR_PLAYER_2"}
RESOURCE_PREFIX = {"tileset": "gr_tileset", "map": "gr_map",
                   "sfx": "gr_sfx_def", "song": "gr_song"}
DEFAULT_BUTTONS = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START"]


class CodeGenerator:
    def __init__(self, program: Program, checker: TypeChecker,
                 filename: str = "<grain>"):
        self.program = program
        self.checker = checker
        self.filename = filename
        self.lines: list[str] = []
        self.max_actors = 8
        self.entity_by_name = {e.name: e for e in program.entities}
        self.scene_by_name = {s.name: s for s in program.scenes}
        self.has_draw_handlers = any("on_draw" in e.handlers
                                     for e in program.entities)

    # -- output helpers ----------------------------------------------------
    def emit(self, text: str = "", indent: int = 0) -> None:
        self.lines.append("    " * indent + text if text else "")

    def type_of(self, node: object) -> str:
        return self.checker.type_of(node)

    def c_name(self, name: str) -> str:
        return "grain_" + name

    def c_string(self, value: str) -> str:
        return json.dumps(value)

    def c_type(self, type_name: str) -> str:
        return {
            "int": "int", "fixed": "gr_fixed", "bool": "bool",
            "string": "const char *", "tileset": "const gr_tileset *",
            "map": "const gr_map *", "sfx": "const gr_sfx_def *",
            "song": "const gr_song *", "void": "void",
        }.get(type_name, "gr_actor *")

    def c_decl(self, type_name: str | None, name: str) -> str:
        resolved = type_name or "int"
        if is_array_type(resolved):
            element, length = array_parts(resolved)
            return f"{self.c_type(element)} {name}[{length}];"
        return f"{self.c_type(resolved)} {name};"

    def c_zero(self, type_name: str) -> str:
        if type_name == "int":
            return "0"
        if type_name == "fixed":
            return "(gr_fixed)0"
        if type_name == "bool":
            return "false"
        return "NULL"

    def collect_var_decls(self, body: list[Stmt]) -> list[VarDecl]:
        declarations: list[VarDecl] = []
        for statement in body:
            if isinstance(statement, VarDecl):
                declarations.append(statement)
            elif isinstance(statement, IfStmt):
                for _condition, branch in statement.branches:
                    declarations.extend(self.collect_var_decls(branch))
                if statement.else_body is not None:
                    declarations.extend(
                        self.collect_var_decls(statement.else_body))
            elif isinstance(statement, WhileStmt):
                declarations.extend(self.collect_var_decls(statement.body))
        return declarations

    def emit_code(self, body: list[Stmt], context: dict, indent: int, *,
                  prologue: tuple[str, ...] = (),
                  extra_decls: tuple[str, ...] = (),
                  middle: tuple[str, ...] = ()) -> None:
        """Emit a body with every declaration hoisted to its start (C89)."""
        declarations = list(extra_decls)
        local_decls = self.collect_var_decls(body)
        for declaration in local_decls:
            declarations.append(self.c_decl(declaration.type_name,
                                            declaration.name))
        for declaration in declarations:
            self.emit(declaration, indent)
        for declaration in local_decls:
            self.emit(f"(void){declaration.name};", indent)
        for line in prologue:
            self.emit(line, indent)
        for line in middle:
            self.emit(line, indent)
        self.emit_body(body, context, indent)

    # -- entry point -------------------------------------------------------
    def generate(self) -> str:
        game = self.program.game
        if game is None:
            raise GrainError("a Grain program needs a 'game' declaration",
                             self.filename,
                             self.program.pos or SourcePos(1, 1))
        self.max_actors = int(game.settings.get("max_actors", 8))
        self.emit(f"/* Generated by the Grain transpiler from {self.filename}.")
        self.emit(" * DO NOT EDIT - edit the .grain source instead.")
        self.emit(" */")
        self.emit("#include <gramma/gramma.h>")
        self.emit("#include <string.h>")
        self.emit()
        self.emit_externs()
        self.emit(f"#define GRAIN_MAX_ACTORS {self.max_actors}u")
        self.emit()
        self.emit_function_prototypes()
        self.emit_entity_declarations()
        self.emit_scene_declarations()
        self.emit_draw_registry()
        for entity in self.program.entities:
            self.emit_entity(entity)
        for scene in self.program.scenes:
            self.emit_scene(scene)
        for function in self.program.functions:
            self.emit_function(function)
        self.emit_game(game)
        return "\n".join(self.lines).rstrip() + "\n"

    def emit_externs(self) -> None:
        if not self.program.externs:
            return
        self.emit("/* Pipeline-provided assets and sounds. */")
        for extern in self.program.externs:
            prefix = RESOURCE_PREFIX[extern.type_name]
            self.emit(f"extern const {prefix} {extern.name};")
        self.emit()

    def emit_function_prototypes(self) -> None:
        if not self.program.functions:
            return
        self.emit("/* User functions (static, defined below the scenes). */")
        for function in self.program.functions:
            self.emit(self.function_signature(function) + ";")
        self.emit()

    def function_signature(self, function: FunctionDecl) -> str:
        _params, return_type = self.checker.functions[function.name]
        rendered = ", ".join(
            f"{self.c_type(type_name)} {name}"
            for (name, _source_type), type_name in
            zip(function.params, self.checker.functions[function.name][0]))
        if not rendered:
            rendered = "void"
        return f"static {self.c_type(return_type)} grain_fn_{function.name}" \
               f"({rendered})"

    # -- declarations ------------------------------------------------------
    def emit_entity_declarations(self) -> None:
        for entity in self.program.entities:
            name = self.c_name(entity.name)
            fields = self.checker.entity_fields[entity.name]
            self.emit(f"typedef struct {{")
            self.emit("gr_actor *actor;", 1)
            for field, type_name in fields.items():
                self.emit(self.c_decl(type_name, field), 1)
            self.emit(f"}} {name};")
            self.emit(f"static {name} {name}_pool[GRAIN_MAX_ACTORS];")
            self.emit(f"static uint8_t {name}_used;")
            if "on_spawn" in entity.handlers:
                self.emit(f"static void {name}_on_spawn(gr_actor *actor);")
            if "on_update" in entity.handlers:
                self.emit(f"static void {name}_on_update(gr_actor *actor, "
                          f"gr_fixed {self.handler_param_name(entity, 'on_update')});")
            if "on_draw" in entity.handlers:
                self.emit(f"static void {name}_on_draw(gr_actor *actor);")
            self.emit(f"static gr_actor *grain_spawn_{entity.name}("
                      f"gr_fixed x, gr_fixed y);")
            self.emit()

    def handler_param_name(self, owner: EntityDecl | SceneDecl,
                           handler_name: str) -> str:
        handler = owner.handlers.get(handler_name)
        if handler is not None and handler.params:
            return handler.params[0][0]
        return "dt"

    def emit_scene_declarations(self) -> None:
        for scene in self.program.scenes:
            name = self.c_name(scene.name)
            fields = self.checker.scene_fields[scene.name]
            self.emit(f"typedef struct {{")
            if fields.get("background") == "map":
                self.emit("gr_bg bg;", 1)
            for field, type_name in fields.items():
                self.emit(self.c_decl(type_name, field), 1)
            self.emit(f"}} {name};")
            self.emit(f"static {name} {name}_state;")
            self.emit(f"static void {name}_on_load(void);")
            if "on_unload" in scene.handlers:
                self.emit(f"static void {name}_on_unload(void);")
            if "on_update" in scene.handlers:
                self.emit(f"static void {name}_on_update("
                          f"gr_fixed {self.handler_param_name(scene, 'on_update')});")
            if "on_draw" in scene.handlers:
                self.emit(f"static void {name}_on_draw(void);")
            self.emit()

    def emit_draw_registry(self) -> None:
        if not self.has_draw_handlers:
            return
        self.emit("/* Per-entity on_draw() dispatch, driven by game_draw. */")
        self.emit("typedef void (*grain_draw_fn)(gr_actor *);")
        self.emit("typedef struct {")
        self.emit("gr_actor *actor;", 1)
        self.emit("grain_draw_fn draw;", 1)
        self.emit("} grain_draw_entry;")
        self.emit("static grain_draw_entry grain_draw_list[GRAIN_MAX_ACTORS];")
        self.emit("static uint8_t grain_draw_count;")
        self.emit()

    # -- entities ----------------------------------------------------------
    def store_lines(self, target: str, type_name: str | None, init: Expr,
                    context: dict, indent: int) -> list[str]:
        resolved = type_name or self.type_of(init)
        if is_array_type(resolved):
            if not isinstance(init, ArrayLiteral):
                raise GrainError("array initializers must be array literals "
                                 "in Grain v1", self.filename,
                                 init.pos or SourcePos(1, 1))
            element_type, _length = array_parts(resolved)
            return [
                f"{target}[{index}] = {self.emit_expr(element, context, element_type)};"
                for index, element in enumerate(init.elements)
            ]
        value = self.emit_expr(init, context, resolved)
        return [f"{target} = {value};"]

    def emit_store(self, target: str, type_name: str | None, init: Expr,
                   context: dict, indent: int) -> None:
        for line in self.store_lines(target, type_name, init, context, indent):
            self.emit(line, indent)

    def emit_entity(self, entity: EntityDecl) -> None:
        name = self.c_name(entity.name)
        fields = self.checker.entity_fields[entity.name]
        self.emit(f"/* Entity {entity.name} */")
        self.emit(f"static gr_actor *grain_spawn_{entity.name}(gr_fixed x, "
                  f"gr_fixed y)")
        self.emit("{")
        self.emit(f"{name} *data;", 1)
        self.emit("gr_actor_def def;", 1)
        self.emit("gr_actor *actor;", 1)
        self.emit()
        self.emit(f"if ({name}_used >= GRAIN_MAX_ACTORS) {{", 1)
        self.emit("return NULL;", 2)
        self.emit("}", 1)
        self.emit(f"data = &{name}_pool[{name}_used++];", 1)
        self.emit("memset(data, 0, sizeof(*data));", 1)
        for field, type_name in fields.items():
            decl = next(f for f in entity.fields if f.name == field)
            self.emit_store(f"data->{field}", type_name, decl.init, {}, 1)
        self.emit("memset(&def, 0, sizeof(def));", 1)
        self.emit(f"def.name = \"{entity.name}\";", 1)
        if "tileset" in fields:
            self.emit("def.tileset = data->tileset;", 1)
        if "frame_w" in fields:
            self.emit("def.frame_w = (uint8_t)data->frame_w;", 1)
        if "frame_h" in fields:
            self.emit("def.frame_h = (uint8_t)data->frame_h;", 1)
        if "frame" in fields:
            self.emit("def.frame = (uint8_t)data->frame;", 1)
        self.emit("def.x = x;", 1)
        self.emit("def.y = y;", 1)
        update = f"{name}_on_update" if "on_update" in entity.handlers else "NULL"
        self.emit(f"def.update = {update};", 1)
        self.emit("def.userdata = data;", 1)
        self.emit("actor = gr_actor_spawn(&def);", 1)
        self.emit("if (actor == NULL) {", 1)
        self.emit(f"--{name}_used;", 2)
        self.emit("return NULL;", 2)
        self.emit("}", 1)
        self.emit("data->actor = actor;", 1)
        if "on_spawn" in entity.handlers:
            self.emit(f"{name}_on_spawn(actor);", 1)
        if "on_draw" in entity.handlers:
            self.emit("if (grain_draw_count < GRAIN_MAX_ACTORS) {", 1)
            self.emit("grain_draw_list[grain_draw_count].actor = actor;", 2)
            self.emit(f"grain_draw_list[grain_draw_count].draw = "
                      f"{name}_on_draw;", 2)
            self.emit("++grain_draw_count;", 2)
            self.emit("}", 1)
        self.emit("return actor;", 1)
        self.emit("}")
        self.emit()

        if "on_spawn" in entity.handlers:
            self.emit_handler(entity, "on_spawn",
                              f"static void {name}_on_spawn(gr_actor *actor)",
                              entity_ctx=True)
        if "on_update" in entity.handlers:
            param = self.handler_param_name(entity, "on_update")
            self.emit_handler(entity, "on_update",
                              f"static void {name}_on_update(gr_actor *actor, "
                              f"gr_fixed {param})", entity_ctx=True)
        if "on_draw" in entity.handlers:
            self.emit_handler(entity, "on_draw", f"static void {name}_on_draw("
                              f"gr_actor *actor)", entity_ctx=True)

    # -- scenes ------------------------------------------------------------
    def emit_scene(self, scene: SceneDecl) -> None:
        name = self.c_name(scene.name)
        fields = self.checker.scene_fields[scene.name]
        self.emit(f"/* Scene {scene.name} */")
        # Always emit on_load so background setup does not depend on the user
        # having written a handler.
        signature = f"static void {name}_on_load(void)"
        self.emit(signature)
        self.emit("{")
        context = self.scene_context(scene)
        middle: list[str] = []
        for field, type_name in fields.items():
            decl = next(f for f in scene.fields if f.name == field)
            middle.extend(self.store_lines(f"self->{field}", type_name,
                                           decl.init, context, 1))
        if fields.get("background") == "map" \
                and fields.get("tileset") == "tileset":
            middle.append("gr_bg_init(&self->bg, self->tileset, "
                          "self->background, 0);")
        handler = scene.handlers.get("on_load")
        body = handler.body if handler is not None else []
        if handler is not None:
            context = self.scene_context(scene,
                                         {p[0] for p in handler.params})
        self.emit_code(body, context, 1,
                       prologue=(f"self = &{name}_state;", "(void)self;"),
                       extra_decls=(f"{name} *self;",),
                       middle=tuple(middle))
        self.emit("}")
        self.emit()

        if "on_unload" in scene.handlers:
            self.emit_handler(scene, "on_unload",
                              f"static void {name}_on_unload(void)",
                              scene_ctx=True)
        if "on_update" in scene.handlers:
            param = self.handler_param_name(scene, "on_update")
            self.emit_handler(scene, "on_update",
                              f"static void {name}_on_update(gr_fixed {param})",
                              scene_ctx=True)
        if "on_draw" in scene.handlers:
            self.emit_handler(scene, "on_draw",
                              f"static void {name}_on_draw(void)",
                              scene_ctx=True)

        self.emit(f"static gr_scene {name}_scene = {{")
        self.emit(f"\"{scene.name}\", "
                  f"{'&' + name + '_state.bg' if fields.get('background') == 'map' else 'NULL'},", 1)
        self.emit(f"{name}_on_load, "
                  f"{name + '_on_unload' if 'on_unload' in scene.handlers else 'NULL'},", 1)
        self.emit(f"{name + '_on_update' if 'on_update' in scene.handlers else 'NULL'},", 1)
        self.emit(f"{name + '_on_draw' if 'on_draw' in scene.handlers else 'NULL'}", 1)
        self.emit("};")
        self.emit()

    # -- user functions ----------------------------------------------------
    def always_returns(self, body: list[Stmt]) -> bool:
        """Conservative check for a return on every path through *body*."""
        for statement in body:
            if isinstance(statement, ReturnStmt):
                return True
            if isinstance(statement, IfStmt) and statement.else_body is not None:
                branches = [branch for _condition, branch in statement.branches]
                branches.append(statement.else_body)
                if all(self.always_returns(branch) for branch in branches):
                    return True
        return False

    def emit_function(self, function: FunctionDecl) -> None:
        _params, return_type = self.checker.functions[function.name]
        self.emit(self.function_signature(function))
        self.emit("{")
        context = {
            "kind": "function", "owner": function,
            "locals": {name for name, _type in function.params},
            "return_type": return_type,
        }
        prologue = tuple(f"(void){name};" for name, _type in function.params)
        self.emit_code(function.body, context, 1, prologue=prologue)
        if return_type != "void" and not self.always_returns(function.body):
            self.emit(f"return {self.c_zero(return_type)};", 1)
        self.emit("}")
        self.emit()

    # -- game --------------------------------------------------------------
    def emit_game(self, game: GameDecl) -> None:
        self.emit("/* Game configuration */")
        if "on_init" in game.handlers:
            handler = game.handlers["on_init"]
            self.emit("static void grain_game_init(void)")
            self.emit("{")
            self.emit_code(handler.body, self.game_context(), 1)
            self.emit("}")
        else:
            self.emit("static void grain_game_init(void) {}")
        self.emit()

        self.emit("static void grain_game_update(gr_fixed grain_dt)")
        self.emit("{")
        body = (game.handlers["on_update"].body
                if "on_update" in game.handlers else [])
        self.emit_code(body, self.game_context(), 1,
                       prologue=("(void)grain_dt;",))
        self.emit("}")
        self.emit()

        self.emit("static void grain_game_draw(void)")
        self.emit("{")
        extra_decls = ("uint8_t grain_draw_i;",) if self.has_draw_handlers else ()
        body = (game.handlers["on_draw"].body
                if "on_draw" in game.handlers else [])
        self.emit_code(body, self.game_context(), 1,
                       extra_decls=extra_decls)
        if self.has_draw_handlers:
            self.emit("for (grain_draw_i = 0; grain_draw_i < grain_draw_count; "
                      "++grain_draw_i) {", 1)
            self.emit("if (grain_draw_list[grain_draw_i].actor->alive && "
                      "grain_draw_list[grain_draw_i].draw != NULL) {", 2)
            self.emit("grain_draw_list[grain_draw_i].draw("
                      "grain_draw_list[grain_draw_i].actor);", 3)
            self.emit("}", 2)
            self.emit("}", 1)
        self.emit("}")
        self.emit()

        sfx_names = [extern.name for extern in self.program.externs
                     if extern.type_name == "sfx"]
        if sfx_names:
            self.emit("static const gr_sfx_def *const grain_sfx_table[] = {")
            self.emit(", ".join(f"&{name}" for name in sfx_names), 1)
            self.emit("};")
            sfx_table = "grain_sfx_table"
            sfx_count = str(len(sfx_names))
        else:
            sfx_table = "NULL"
            sfx_count = "0"
        self.emit()

        width = game.settings.get("width", "GR_SCREEN_W")
        height = game.settings.get("height", "GR_SCREEN_H")
        title = self.c_string(str(game.settings.get("title", "Grain game")))
        players = int(game.settings.get("players", 1))
        buttons = game.settings.get("required_buttons", DEFAULT_BUTTONS)
        bits = " | ".join(f"GR_BUTTON_BIT({BUTTON_MACROS[b]})"
                          for b in buttons)
        p2_bits = bits if players > 1 else "0"
        self.emit("static const gr_config grain_config = {")
        self.emit(f"{title}, {width}, {height}, {self.max_actors}, "
                  f"{players},", 1)
        self.emit(f"{{ {bits}, {p2_bits} }},", 1)
        self.emit("grain_game_init, grain_game_update, grain_game_draw,", 1)
        self.emit(f"{sfx_table}, {sfx_count}", 1)
        self.emit("};")
        self.emit()
        self.emit("int main(void)")
        self.emit("{")
        self.emit("if (gr_init(&grain_config) != GR_OK) {", 1)
        self.emit("return 1;", 2)
        self.emit("}", 1)
        self.emit("return gr_run();", 1)
        self.emit("}")

    # -- handler bodies ----------------------------------------------------
    def entity_ctx(self, entity: EntityDecl,
                   locals: set[str] | None = None) -> dict:
        return {"kind": "entity", "owner": entity,
                "locals": set(locals or ())}

    def scene_context(self, scene: SceneDecl,
                      locals: set[str] | None = None) -> dict:
        return {"kind": "scene", "owner": scene, "locals": set(locals or ())}

    def game_context(self, locals: set[str] | None = None) -> dict:
        return {"kind": "game", "owner": None, "locals": set(locals or ())}

    def emit_handler(self, owner: EntityDecl | SceneDecl, name: str,
                     signature: str, entity_ctx: bool = False,
                     scene_ctx: bool = False) -> None:
        handler: Handler = owner.handlers[name]
        self.emit(signature)
        self.emit("{")
        struct = self.c_name(owner.name)
        local_names = {param for param, _type in handler.params}
        param_casts = tuple(f"(void){param};" for param, _type in handler.params)
        if entity_ctx:
            self.emit_code(
                handler.body,
                self.entity_ctx(owner, local_names), 1,
                prologue=(f"self = ({struct} *)actor->userdata;",
                          "(void)self;") + param_casts,
                extra_decls=(f"{struct} *self;",))
        elif scene_ctx:
            self.emit_code(
                handler.body,
                self.scene_context(owner, local_names), 1,
                prologue=(f"self = &{struct}_state;", "(void)self;") +
                         param_casts,
                extra_decls=(f"{struct} *self;",))
        else:
            self.emit_code(handler.body, self.game_context(local_names), 1,
                           prologue=param_casts)
        self.emit("}")
        self.emit()

    def emit_body(self, body: list[Stmt], context: dict, indent: int) -> None:
        for statement in body:
            self.emit_stmt(statement, context, indent)

    def emit_stmt(self, stmt: Stmt, context: dict, indent: int) -> None:
        if isinstance(stmt, ExprStmt):
            self.emit(f"{self.emit_expr(stmt.expr, context)};", indent)
        elif isinstance(stmt, VarDecl):
            self.emit_store(stmt.name, stmt.type_name, stmt.init, context,
                            indent)
        elif isinstance(stmt, Assign):
            target_type = self.type_of(stmt.target)
            target = self.emit_expr(stmt.target, context, target_type)
            value = self.emit_expr(stmt.value, context, target_type)
            op = stmt.op
            if op == "=":
                self.emit(f"{target} = {value};", indent)
            elif op == "+=":
                self.emit(f"{target} += {value};", indent)
            elif op == "-=":
                self.emit(f"{target} -= {value};", indent)
            elif op == "*=":
                if target_type == "fixed":
                    self.emit(f"{target} = gr_fmul({target}, {value});", indent)
                else:
                    self.emit(f"{target} *= {value};", indent)
            elif op == "/=":
                if target_type == "fixed":
                    self.emit(f"{target} = gr_fdiv({target}, {value});", indent)
                else:
                    self.emit(f"{target} /= {value};", indent)
        elif isinstance(stmt, IfStmt):
            for index, (condition, body) in enumerate(stmt.branches):
                keyword = "if" if index == 0 else "else if"
                self.emit(f"{keyword} ({self.emit_expr(condition, context)}) {{",
                          indent)
                self.emit_body(body, context, indent + 1)
                self.emit("}", indent)
            if stmt.else_body is not None:
                self.emit("else {", indent)
                self.emit_body(stmt.else_body, context, indent + 1)
                self.emit("}", indent)
        elif isinstance(stmt, WhileStmt):
            self.emit(f"while ({self.emit_expr(stmt.cond, context)}) {{", indent)
            self.emit_body(stmt.body, context, indent + 1)
            self.emit("}", indent)
        elif isinstance(stmt, ReturnStmt):
            expected = context.get("return_type")
            if stmt.value is None:
                self.emit("return;", indent)
            else:
                value = self.emit_expr(stmt.value, context, expected)
                self.emit(f"return {value};", indent)

    # -- expressions -------------------------------------------------------
    def coerce(self, text: str, actual: str, expected: str | None) -> str:
        if expected == "fixed" and actual == "int":
            return f"gr_itof({text})"
        return text

    def fixed_literal(self, raw: str) -> str:
        value = Fraction(raw)
        numerator, denominator = value.numerator, value.denominator
        if denominator == 1:
            return f"(gr_fixed)(GR_FIXED_ONE * {numerator})"
        return (f"(gr_fixed)(GR_FIXED_ONE * {numerator} / {denominator})")

    def actor_expr(self, node: Expr, context: dict) -> str:
        """Render a Grain ``entity`` value as a C ``gr_actor *``."""
        if isinstance(node, Name) and node.name == "self":
            return "self->actor"
        return self.emit_expr(node, context)

    def sprite_expr(self, node: Expr, context: dict) -> str:
        return f"&({self.actor_expr(node, context)})->sprite"

    def emit_expr(self, node: Expr, context: dict | None,
                  expected: str | None = None) -> str:
        context = context or {}
        node_type = self.type_of(node)
        if isinstance(node, Literal):
            if node.kind == "fixed":
                return self.fixed_literal(str(node.value))
            if node.kind == "bool":
                return "true" if node.value else "false"
            if node.kind == "string":
                return self.c_string(str(node.value))
            return self.coerce(str(node.value), "int", expected)
        if isinstance(node, Name):
            name = node.name
            if name in context.get("locals", ()):
                return name
            if name == "self":
                return "self"
            if name in PLAYER_MACROS:
                return PLAYER_MACROS[name]
            if name in BUTTON_MACROS:
                return BUTTON_MACROS[name]
            if name == "SCREEN_W":
                return "GR_SCREEN_W"
            if name == "SCREEN_H":
                return "GR_SCREEN_H"
            if context.get("kind") in {"entity", "scene"}:
                fields = (self.checker.entity_fields if context["kind"] == "entity"
                          else self.checker.scene_fields)
                owner = context.get("owner")
                if owner is not None and name in fields.get(owner.name, {}):
                    return f"self->{name}"
                if context["kind"] == "entity" and name in ENGINE_FIELDS:
                    return f"self->actor->{name}"
            if name in self.checker.globals:
                return "&" + name
            return name
        if isinstance(node, Attr):
            if context.get("kind") == "entity" \
                    and node.field in ENGINE_FIELDS:
                return f"self->actor->{node.field}"
            return f"self->{node.field}"
        if isinstance(node, Unary):
            operand = self.emit_expr(node.operand, context)
            return f"(!{operand})" if node.op == "not" else f"(-{operand})"
        if isinstance(node, Binary):
            return self.emit_binary(node, context)
        if isinstance(node, Call):
            return self.emit_call(node, context)
        if isinstance(node, Index):
            obj = self.emit_expr(node.obj, context)
            index = self.emit_expr(node.index, context, "int")
            return f"{obj}[{index}]"
        if isinstance(node, ArrayLiteral):
            raise GrainError("array literals are only valid as initializers "
                             "in Grain v1", self.filename,
                             node.pos or SourcePos(1, 1))
        return "0"

    def emit_binary(self, node: Binary, context: dict) -> str:
        op = node.op
        if op == "and" or op == "or":
            left = self.emit_expr(node.left, context)
            right = self.emit_expr(node.right, context)
            return f"({left} {'&&' if op == 'and' else '||'} {right})"
        left_type = self.type_of(node.left)
        right_type = self.type_of(node.right)
        left = self.emit_expr(node.left, context,
                              "fixed" if "fixed" in (left_type, right_type)
                              else left_type)
        right = self.emit_expr(node.right, context,
                               "fixed" if "fixed" in (left_type, right_type)
                               else right_type)
        if op in {"+", "-"}:
            return f"({left} {op} {right})"
        if op == "*":
            if "fixed" in (left_type, right_type):
                return f"gr_fmul({left}, {right})"
            return f"({left} * {right})"
        if op == "/":
            if "fixed" in (left_type, right_type):
                return f"gr_fdiv({left}, {right})"
            return f"({left} / {right})"
        return f"({left} {op} {right})"

    def emit_call(self, node: Call, context: dict) -> str:
        name = node.callee
        args = node.args
        if name in self.checker.functions:
            params, _result = self.checker.functions[name]
            rendered = [self.emit_expr(arg, context, expected)
                        for arg, expected in zip(args, params)]
            return f"grain_fn_{name}({', '.join(rendered)})"
        direct_math = {
            "itof": "gr_itof", "ftoi": "gr_ftoi", "fclamp": "gr_fclamp",
            "sfx_play": "gr_sfx_play", "music_play": "gr_music_play",
            "music_stop": "gr_music_stop", "request_quit": "gr_request_quit",
            "quit_requested": "gr_quit_requested",
        }
        if name in direct_math:
            rendered = [self.emit_expr(arg, context) for arg in args]
            return f"{direct_math[name]}({', '.join(rendered)})"
        if name in {"fmul", "fdiv"}:
            left, right = (self.emit_expr(arg, context, "fixed")
                           for arg in args)
            c_name = "gr_fmul" if name == "fmul" else "gr_fdiv"
            return f"{c_name}({left}, {right})"
        if name in {"pad_down", "pad_pressed", "pad_released"}:
            first, second = (self.emit_expr(arg, context) for arg in args)
            return f"gr_{name}({first}, {second})"
        if name in {"hide", "set_frame", "set_flip", "show"}:
            sprite = self.sprite_expr(args[0], context)
            rest = [self.emit_expr(arg, context)
                    for arg in args[1:]]
            c_name = {
                "hide": "gr_sprite_hide", "set_frame": "gr_sprite_set_frame",
                "set_flip": "gr_sprite_set_flip", "show": "gr_sprite_show",
            }[name]
            return f"{c_name}({sprite}{''.join(', ' + r for r in rest)})"
        if name == "scroll":
            x, y = (self.emit_expr(arg, context, "int") for arg in args)
            return f"gr_bg_set_scroll(&self->bg, {x}, {y})"
        if name == "destroy":
            return f"gr_actor_destroy({self.actor_expr(args[0], context)})"
        if name == "spawn":
            entity_name = args[0].name  # validated by the checker
            x, y = (self.emit_expr(arg, context, "fixed") for arg in args[1:])
            return f"grain_spawn_{entity_name}({x}, {y})"
        if name == "load_scene":
            return f"gr_scene_load(&grain_{args[0].name}_scene)"
        return "0"


def transpile(text: str, filename: str = "<grain>",
              checker: TypeChecker | None = None) -> tuple[str, TypeChecker]:
    """Parse, typecheck and emit C for *text*; return ``(source, checker)``."""
    program = parse(text, filename)
    checker = checker or typecheck(program, filename)
    source = CodeGenerator(program, checker, filename).generate()
    return source, checker
