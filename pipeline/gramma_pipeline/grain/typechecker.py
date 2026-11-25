"""Static type checker for Grain v1.

The checker is intentionally strict where it matters (unknown names, field
types, builtin/user-function arity, handler signatures, return types,
numeric/bool mixing and fixed-size arrays) and permissive where C does the
right thing (an ``int`` may feed a ``fixed`` parameter and is coerced by the
code generator). Every expression is annotated with its type so code generation
never has to guess, which is what lets ``*=`` and ``/=`` emit ``gr_fmul``/
``gr_fdiv`` instead of raw integer arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast import (
    ArrayLiteral, Assign, Attr, Binary, Call, EntityDecl, Expr, ExprStmt,
    FieldDecl, FunctionDecl, GameDecl, Handler, IfStmt, Index, Literal, Name,
    Program, ReturnStmt, SceneDecl, Stmt, Unary, VarDecl, WhileStmt)
from .errors import GrainError, SourcePos
from .types import array_parts, is_array_type, make_array_type

PRIMITIVES = {"int", "fixed", "bool", "string", "tileset", "map", "sfx",
              "song"}
RESOURCE_TYPES = {"tileset", "map", "sfx", "song"}
BUTTONS = {"UP", "DOWN", "LEFT", "RIGHT", "A", "B", "X", "Y", "L", "R",
           "START", "SELECT"}
PLAYERS = {"P1": "int", "P2": "int"}
CONSTANTS = {
    **PLAYERS,
    **{button: "int" for button in BUTTONS},
    "SCREEN_W": "int",
    "SCREEN_H": "int",
}
ENGINE_FIELDS = {"x": "fixed", "y": "fixed", "vx": "fixed", "vy": "fixed"}
RESERVED_ENTITY_FIELDS = set(ENGINE_FIELDS) | {"actor"}
C_RESERVED = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "int",
    "long", "register", "return", "short", "signed", "sizeof", "static",
    "struct", "switch", "typedef", "union", "unsigned", "void", "volatile",
    "while", "bool", "actor",
}

# Builtin name -> (parameter types, return type). ``entity``/``scene`` are
# pseudo-types meaning "a value of any declared entity/scene type".
BUILTINS: dict[str, tuple[list[str], str]] = {
    "itof": (["int"], "fixed"),
    "ftoi": (["fixed"], "int"),
    "fmul": (["fixed", "fixed"], "fixed"),
    "fdiv": (["fixed", "fixed"], "fixed"),
    "fclamp": (["fixed", "fixed", "fixed"], "fixed"),
    "pad_down": (["int", "int"], "bool"),
    "pad_pressed": (["int", "int"], "bool"),
    "pad_released": (["int", "int"], "bool"),
    "sfx_play": (["int", "int"], "void"),
    "music_play": (["song"], "void"),
    "music_stop": ([], "void"),
    "show": (["entity", "int", "int", "int"], "void"),
    "hide": (["entity"], "void"),
    "set_frame": (["entity", "int"], "void"),
    "set_flip": (["entity", "bool", "bool"], "void"),
    "scroll": (["int", "int"], "void"),
    "destroy": (["entity"], "void"),
    "request_quit": ([], "void"),
    "quit_requested": ([], "bool"),
}


@dataclass
class Context:
    kind: str                 # "entity" | "scene" | "game" | "function"
    owner: object
    handler: str
    locals: dict[str, str] = field(default_factory=dict)
    return_type: str | None = None


class TypeChecker:
    def __init__(self, program: Program, filename: str = "<grain>"):
        self.program = program
        self.filename = filename
        self.node_types: dict[int, str] = {}
        self.entity_fields: dict[str, dict[str, str]] = {}
        self.scene_fields: dict[str, dict[str, str]] = {}
        self.globals: dict[str, str] = {}
        self.functions: dict[str, tuple[list[str], str]] = {}
        self.entity_names = {entity.name for entity in program.entities}
        self.scene_names = {scene.name for scene in program.scenes}

    # -- helpers -----------------------------------------------------------
    def fail(self, message: str, node: object | None = None,
             pos: SourcePos | None = None) -> None:
        if pos is None:
            pos = getattr(node, "pos", None) or SourcePos(1, 1)
        raise GrainError(message, self.filename, pos)

    def mark(self, node: object, type_name: str) -> str:
        self.node_types[id(node)] = type_name
        return type_name

    def type_of(self, node: object) -> str:
        return self.node_types.get(id(node), "error")

    def check_identifier(self, name: str, node: object) -> None:
        if name in C_RESERVED:
            self.fail(f"'{name}' is a reserved identifier", node)
        if name in CONSTANTS or name in BUILTINS:
            self.fail(f"cannot redeclare '{name}'", node)

    @staticmethod
    def compatible(actual: str, expected: str) -> bool:
        if actual == expected:
            return True
        if actual == "int" and expected == "fixed":
            return True
        if expected == "entity" and actual.startswith("entity:"):
            return True
        if expected == "scene" and actual.startswith("scene:"):
            return True
        return False

    def require(self, actual: str, expected: str, what: str,
                node: Expr) -> None:
        if not self.compatible(actual, expected):
            self.fail(f"{what}: expected {expected}, got {actual}", node)

    def is_scalar(self, type_name: str) -> bool:
        if type_name in PRIMITIVES:
            return True
        if type_name.startswith("entity:"):
            return type_name[7:] in self.entity_names
        if type_name.startswith("scene:"):
            return type_name[6:] in self.scene_names
        return False

    def normalize_type(self, type_name: str | None) -> str | None:
        if type_name is None:
            return None
        if type_name in self.entity_names:
            return f"entity:{type_name}"
        if type_name in self.scene_names:
            return f"scene:{type_name}"
        if is_array_type(type_name):
            element, length = array_parts(type_name)
            if element in self.entity_names:
                element = f"entity:{element}"
            elif element in self.scene_names:
                element = f"scene:{element}"
            return make_array_type(element, length)
        return type_name

    def validate_type(self, type_name: str, node: object, *,
                      allow_array: bool = True,
                      allow_void: bool = False) -> None:
        if type_name == "void":
            if allow_void:
                return
            self.fail("'void' is only valid as a function return type", node)
        if is_array_type(type_name):
            if not allow_array:
                self.fail("arrays are only valid for fields, locals and "
                          "array literals", node)
            element, _length = array_parts(type_name)
            if not self.is_scalar(element):
                self.fail(f"unknown type '{element}'", node)
            return
        if not self.is_scalar(type_name):
            self.fail(f"unknown type '{type_name}'", node)

    # -- entry point -------------------------------------------------------
    def check(self) -> None:
        seen: dict[str, str] = {}
        for entity in self.program.entities:
            if entity.name in seen:
                self.fail(f"duplicate declaration '{entity.name}'", entity)
            seen[entity.name] = "entity"
        for scene in self.program.scenes:
            if scene.name in seen:
                self.fail(f"duplicate declaration '{scene.name}'", scene)
            seen[scene.name] = "scene"
        for function in self.program.functions:
            self.check_identifier(function.name, function)
            if function.name in seen or function.name in self.globals \
                    or function.name in self.functions:
                self.fail(f"duplicate declaration '{function.name}'", function)
            seen[function.name] = "function"
            self.validate_type(function.return_type, function,
                               allow_array=False, allow_void=True)
            params: list[str] = []
            for param_name, param_type in function.params:
                self.check_identifier(param_name, function)
                if param_name in params:
                    self.fail(f"duplicate parameter '{param_name}'", function)
                self.validate_type(param_type, function, allow_array=False)
                params.append(self.normalize_type(param_type) or param_type)
            self.functions[function.name] = (params, function.return_type)

        for extern in self.program.externs:
            if extern.type_name not in RESOURCE_TYPES:
                self.fail(f"unknown extern type '{extern.type_name}'; "
                          f"expected {', '.join(sorted(RESOURCE_TYPES))}",
                          extern)
            self.check_identifier(extern.name, extern)
            if extern.name in seen or extern.name in self.globals:
                self.fail(f"duplicate identifier '{extern.name}'", extern)
            self.globals[extern.name] = extern.type_name

        for entity in self.program.entities:
            self.check_fields(entity, "entity")
        for scene in self.program.scenes:
            self.check_fields(scene, "scene")
        for function in self.program.functions:
            self.check_function(function)
        for entity in self.program.entities:
            self.check_handlers(entity, "entity")
        for scene in self.program.scenes:
            self.check_handlers(scene, "scene")
        if self.program.game is not None:
            self.check_game(self.program.game)

    # -- fields, functions and handlers -----------------------------------
    def check_fields(self, owner: EntityDecl | SceneDecl, kind: str) -> None:
        result: dict[str, str] = {}
        for decl in owner.fields:
            self.check_identifier(decl.name, decl)
            if decl.name in result:
                self.fail(f"duplicate field '{decl.name}' in {kind} "
                          f"'{owner.name}'", decl)
            if kind == "entity" and decl.name in RESERVED_ENTITY_FIELDS:
                self.fail(f"'{decl.name}' is a reserved engine field", decl)
            declared = self.normalize_type(decl.type_name)
            if declared is not None:
                self.validate_type(declared, decl)
            inferred = self.check_expr(decl.init, None, declared)
            if inferred == "void":
                self.fail(f"field '{decl.name}' cannot have a void initializer",
                          decl)
            if declared is not None:
                self.require(inferred, declared,
                             f"field '{decl.name}' initializer", decl.init)
                decl.type_name = declared
                result[decl.name] = declared
            else:
                decl.type_name = inferred
                result[decl.name] = inferred
        if kind == "entity" and result.get("tileset") != "tileset":
            self.fail(f"entity '{owner.name}' needs a "
                      f"'tileset: tileset' field so it can be spawned", owner)
        if kind == "entity":
            self.entity_fields[owner.name] = result
        else:
            self.scene_fields[owner.name] = result

    def check_function(self, function: FunctionDecl) -> None:
        params, return_type = self.functions[function.name]
        context = Context("function", function, function.name,
                          dict(zip((p[0] for p in function.params), params)),
                          return_type)
        self.check_body(function.body, context)

    def check_handlers(self, owner: EntityDecl | SceneDecl, kind: str) -> None:
        expected_params = {
            "on_spawn": [], "on_update": ["fixed"], "on_draw": [],
            "on_load": [], "on_unload": [], "on_init": [],
        }
        for name, handler in owner.handlers.items():
            wanted = expected_params.get(name)
            if wanted is None:
                self.fail(f"unknown handler '{name}'", handler)
            actual: list[str] = []
            for param_name, type_name in handler.params:
                self.check_identifier(param_name, handler)
                self.validate_type(type_name, handler, allow_array=False)
                actual.append(self.normalize_type(type_name) or type_name)
            if actual != wanted:
                signature = ", ".join(wanted) if wanted else "no parameters"
                self.fail(f"handler '{name}' expects {signature}, got "
                          f"{', '.join(actual) if actual else 'no parameters'}",
                          handler)
            context = Context(kind, owner, name,
                              dict(zip((p[0] for p in handler.params), actual)))
            self.check_body(handler.body, context)

    def check_game(self, game: GameDecl) -> None:
        known = {"title", "width", "height", "max_actors", "players",
                 "required_buttons"}
        for key, value in game.settings.items():
            if key not in known:
                self.fail(f"unknown game setting '{key}'", game)
            if key == "title" and not isinstance(value, str):
                self.fail("'title' must be a string", game)
            if key == "required_buttons":
                if not isinstance(value, list):
                    self.fail("'required_buttons' must be a list", game)
                for button in value:
                    if button not in BUTTONS:
                        self.fail(f"unknown button '{button}' in "
                                  f"required_buttons", game)
            elif key != "title" and not isinstance(value, int):
                self.fail(f"'{key}' must be an integer", game)
            if key in {"width", "height"} and isinstance(value, int):
                if value <= 0 or value % 8 != 0:
                    self.fail(f"'{key}' must be a positive multiple of 8",
                              game)
            if key == "max_actors" and isinstance(value, int):
                if not 1 <= value <= 64:
                    self.fail("'max_actors' must be between 1 and 64", game)
            if key == "players" and isinstance(value, int):
                if value not in (1, 2):
                    self.fail("'players' must be 1 or 2", game)
        for name, handler in game.handlers.items():
            if handler.params:
                self.fail(f"game handler '{name}' takes no parameters",
                          handler)
            self.check_body(handler.body, Context("game", game, name))

    # -- statements --------------------------------------------------------
    def check_body(self, body: list[Stmt], context: Context) -> None:
        for statement in body:
            self.check_stmt(statement, context)

    def check_stmt(self, stmt: Stmt, context: Context) -> None:
        if isinstance(stmt, ExprStmt):
            self.check_expr(stmt.expr, context)
        elif isinstance(stmt, VarDecl):
            self.check_identifier(stmt.name, stmt)
            if stmt.name in context.locals:
                self.fail(f"duplicate local variable '{stmt.name}' in "
                          f"{context.kind} '{getattr(context.owner, 'name', 'game')}'",
                          stmt)
            declared = self.normalize_type(stmt.type_name)
            if declared is not None:
                self.validate_type(declared, stmt)
            inferred = self.check_expr(stmt.init, context, declared)
            if inferred == "void":
                self.fail(f"local '{stmt.name}' cannot have a void initializer",
                          stmt)
            resolved = declared or inferred
            if declared is not None:
                self.require(inferred, declared,
                             f"local '{stmt.name}' initializer", stmt.init)
            stmt.type_name = resolved
            self.mark(stmt, resolved)
            context.locals[stmt.name] = resolved
        elif isinstance(stmt, Assign):
            target_type = self.check_expr(stmt.target, context)
            if is_array_type(target_type):
                self.fail("cannot assign to a whole array; assign elements "
                          "instead (e.g. 'a[0] = 1')", stmt)
            value_type = self.check_expr(stmt.value, context, target_type)
            if isinstance(stmt.target, Name) and stmt.target.name in CONSTANTS:
                self.fail(f"cannot assign to constant '{stmt.target.name}'",
                          stmt)
            self.require(value_type, target_type, "assignment", stmt.value)
            if stmt.op in {"+=", "-=", "*=", "/="} \
                    and target_type not in {"int", "fixed"}:
                self.fail(f"operator '{stmt.op}' needs a numeric target", stmt)
        elif isinstance(stmt, IfStmt):
            for condition, body in stmt.branches:
                self.require(self.check_expr(condition, context), "bool",
                             "if condition", condition)
                self.check_body(body, context)
            if stmt.else_body is not None:
                self.check_body(stmt.else_body, context)
        elif isinstance(stmt, WhileStmt):
            self.require(self.check_expr(stmt.cond, context), "bool",
                         "while condition", stmt.cond)
            self.check_body(stmt.body, context)
        elif isinstance(stmt, ReturnStmt):
            expected = context.return_type
            if expected in (None, "void"):
                if stmt.value is not None:
                    self.fail("handlers and void functions cannot return a "
                              "value", stmt)
            elif stmt.value is None:
                self.fail(f"function '{getattr(context.owner, 'name', '')}' "
                          f"must return a {expected}", stmt)
            else:
                actual = self.check_expr(stmt.value, context, expected)
                self.require(actual, expected, "return value", stmt.value)
        else:
            self.fail(f"unsupported statement {type(stmt).__name__}", stmt)

    # -- expressions -------------------------------------------------------
    def check_expr(self, node: Expr, context: Context | None,
                   expected: str | None = None) -> str:
        if isinstance(node, Literal):
            return self.mark(node, node.kind)
        if isinstance(node, Name):
            return self.check_name(node, context)
        if isinstance(node, Attr):
            return self.check_attr(node, context)
        if isinstance(node, Unary):
            operand = self.check_expr(node.operand, context)
            if node.op == "-":
                if operand not in {"int", "fixed"}:
                    self.fail("unary '-' needs a numeric operand", node)
                return self.mark(node, operand)
            if operand != "bool":
                self.fail("'not' needs a bool operand", node)
            return self.mark(node, "bool")
        if isinstance(node, Binary):
            return self.check_binary(node, context)
        if isinstance(node, Call):
            return self.check_call(node, context)
        if isinstance(node, ArrayLiteral):
            return self.check_array_literal(node, context, expected)
        if isinstance(node, Index):
            return self.check_index(node, context)
        self.fail(f"unsupported expression {type(node).__name__}", node)
        return "error"

    def check_array_literal(self, node: ArrayLiteral, context: Context | None,
                            expected: str | None) -> str:
        if not expected or not is_array_type(expected):
            self.fail("array literals need an array-typed target (e.g. "
                      "'var a: int[2] = [1, 2]')", node)
        element_type, length = array_parts(expected)
        if len(node.elements) != length:
            self.fail(f"array literal has {len(node.elements)} element(s), "
                      f"expected {length}", node)
        for element in node.elements:
            actual = self.check_expr(element, context, element_type)
            self.require(actual, element_type, "array element", element)
        return self.mark(node, expected)

    def check_index(self, node: Index, context: Context | None) -> str:
        obj_type = self.check_expr(node.obj, context)
        if not is_array_type(obj_type):
            self.fail("can only index a fixed-size array", node)
        index_type = self.check_expr(node.index, context, "int")
        if index_type != "int":
            self.fail(f"array index must be an int, got {index_type}", node)
        element_type, _length = array_parts(obj_type)
        return self.mark(node, element_type)

    def check_name(self, node: Name, context: Context | None) -> str:
        name = node.name
        if name == "self":
            if context is None or context.kind in {"game", "function"}:
                self.fail("'self' is only available inside handlers", node)
            if context.kind == "entity":
                return self.mark(node, f"entity:{context.owner.name}")
            return self.mark(node, f"scene:{context.owner.name}")
        if context is not None and name in context.locals:
            return self.mark(node, context.locals[name])
        if context is not None and context.kind in {"entity", "scene"}:
            fields = (self.entity_fields if context.kind == "entity"
                      else self.scene_fields)
            available = fields.get(context.owner.name, {})
            if name in available:
                return self.mark(node, available[name])
            if context.kind == "entity" and name in ENGINE_FIELDS:
                return self.mark(node, ENGINE_FIELDS[name])
        if name in self.globals:
            return self.mark(node, self.globals[name])
        if name in CONSTANTS:
            return self.mark(node, CONSTANTS[name])
        if name in self.functions:
            self.fail(f"'{name}' is a function; call it as '{name}(...)'", node)
        if name in self.entity_names or name in self.scene_names:
            self.fail(f"'{name}' is a type name, not a value", node)
        self.fail(f"unknown identifier '{name}'", node)
        return "error"

    def check_attr(self, node: Attr, context: Context | None) -> str:
        if not isinstance(node.obj, Name) or node.obj.name != "self":
            self.fail("only 'self.field' access is supported in Grain v1",
                      node)
        if context is None or context.kind in {"game", "function"}:
            self.fail("'self' is only available inside handlers", node)
        fields = (self.entity_fields if context.kind == "entity"
                  else self.scene_fields)
        available = fields.get(context.owner.name, {})
        if context.kind == "entity" and node.field in ENGINE_FIELDS:
            return self.mark(node, ENGINE_FIELDS[node.field])
        if node.field not in available:
            self.fail(f"'{context.owner.name}' has no field '{node.field}'",
                      node)
        return self.mark(node, available[node.field])

    def check_binary(self, node: Binary, context: Context | None) -> str:
        left = self.check_expr(node.left, context)
        right = self.check_expr(node.right, context)
        op = node.op
        if op in {"and", "or"}:
            if left != "bool" or right != "bool":
                self.fail(f"'{op}' needs two bool operands", node)
            return self.mark(node, "bool")
        if op in {"==", "!=", "<", ">", "<=", ">="}:
            numeric = {"int", "fixed"}
            if left in numeric and right in numeric:
                return self.mark(node, "bool")
            if op in {"==", "!="} and left == right and not is_array_type(left):
                return self.mark(node, "bool")
            self.fail(f"cannot compare {left} with {right}", node)
        if op in {"+", "-", "*", "/"}:
            if left not in {"int", "fixed"} or right not in {"int", "fixed"}:
                self.fail(f"operator '{op}' needs numeric operands", node)
            return self.mark(node, "fixed" if "fixed" in (left, right)
                             else "int")
        self.fail(f"unknown operator '{op}'", node)
        return "error"

    def check_call(self, node: Call, context: Context | None) -> str:
        name = node.callee
        if name in self.functions:
            params, result = self.functions[name]
            if len(node.args) != len(params):
                self.fail(f"{name}() expects {len(params)} argument(s), got "
                          f"{len(node.args)}", node)
            for index, (arg, expected) in enumerate(zip(node.args, params)):
                actual = self.check_expr(arg, context, expected)
                self.require(actual, expected,
                             f"{name}() argument {index + 1}", arg)
            return self.mark(node, result)
        if name == "spawn":
            if len(node.args) != 3:
                self.fail("spawn() expects (EntityType, x, y)", node)
            target = node.args[0]
            if not isinstance(target, Name) or target.name not in self.entity_names:
                self.fail("spawn() first argument must be an entity type", target)
            self.mark(target, f"entity:{target.name}")
            self.require(self.check_expr(node.args[1], context), "fixed",
                         "spawn x", node.args[1])
            self.require(self.check_expr(node.args[2], context), "fixed",
                         "spawn y", node.args[2])
            return self.mark(node, f"entity:{target.name}")
        if name == "load_scene":
            if len(node.args) != 1:
                self.fail("load_scene() expects one scene type", node)
            target = node.args[0]
            if not isinstance(target, Name) or target.name not in self.scene_names:
                self.fail("load_scene() argument must be a scene type", target)
            self.mark(target, f"scene:{target.name}")
            return self.mark(node, "void")
        if name not in BUILTINS:
            self.fail(f"unknown function '{name}'", node)
        params, result = BUILTINS[name]
        if len(node.args) != len(params):
            self.fail(f"{name}() expects {len(params)} argument(s), got "
                      f"{len(node.args)}", node)
        if name == "scroll":
            if context is None or context.kind != "scene":
                self.fail("scroll() is only available in scene handlers", node)
            fields = self.scene_fields.get(context.owner.name, {})
            if fields.get("background") != "map" \
                    or fields.get("tileset") != "tileset":
                self.fail("scroll() needs a scene with 'background: map' and "
                          "'tileset: tileset' fields", node)
        for index, (arg, expected) in enumerate(zip(node.args, params)):
            actual = self.check_expr(arg, context, expected)
            self.require(actual, expected,
                         f"{name}() argument {index + 1}", arg)
        return self.mark(node, result)


def typecheck(program: Program, filename: str = "<grain>") -> TypeChecker:
    checker = TypeChecker(program, filename)
    checker.check()
    return checker
