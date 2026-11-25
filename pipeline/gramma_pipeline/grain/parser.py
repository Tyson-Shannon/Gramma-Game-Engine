"""Recursive-descent parser for Grain v1.

Grammar (informal)::

    program    := (extern | func | entity | scene | game)*
    extern     := 'extern' IDENT IDENT ';'?
    func       := 'func' IDENT '(' params? ')' '->' type block
    entity     := 'entity' IDENT '{' member* '}'
    scene      := 'scene'  IDENT '{' member* '}'
    game       := 'game' '{' (setting | handler)* '}'
    member     := handler | field
    field      := IDENT (':' type)? '=' expr ';'?
    type       := IDENT ('[' INT ']')?
    handler    := ('on_spawn'|'on_update'|'on_draw'|'on_load'|'on_unload'
                   |'on_init') '(' params? ')' block
    params     := IDENT ':' type (',' IDENT ':' type)*
    setting    := IDENT '=' (INT | STRING | '[' IDENT (',' IDENT)* ']') ';'?
    block      := '{' stmt* '}'
    stmt       := var | if | while | return | assign | expr_stmt
    var        := 'var' IDENT (':' type)? '=' expr ';'?

Expressions use conventional precedence, support calls, attribute access,
``a[i]`` indexing, fixed array literals, unary ``-``/``not`` and the usual
arithmetic/comparison/logical operators.
"""

from __future__ import annotations

from .ast import (
    ArrayLiteral, Assign, Attr, Binary, Call, EntityDecl, ExternDecl, Expr,
    ExprStmt, FieldDecl, FunctionDecl, GameDecl, Handler, IfStmt, Index,
    Literal, Name, Program, ReturnStmt, SceneDecl, Stmt, Unary, VarDecl,
    WhileStmt)
from .errors import GrainError, SourcePos
from .lexer import Token, tokenize
from .types import make_array_type

ASSIGN_OPS = {"=", "+=", "-=", "*=", "/="}


class Parser:
    def __init__(self, tokens: list[Token], filename: str):
        self.tokens = tokens
        self.filename = filename
        self.index = 0

    # -- token helpers -----------------------------------------------------
    def peek(self, offset: int = 0) -> Token:
        index = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def at(self, kind: str, value: object | None = None) -> bool:
        token = self.peek()
        return token.kind == kind and (value is None or token.value == value)

    def advance(self) -> Token:
        token = self.peek()
        if token.kind != "EOF":
            self.index += 1
        return token

    def error(self, message: str, token: Token | None = None) -> GrainError:
        token = token or self.peek()
        return GrainError(message, self.filename, token.pos)

    def expect(self, kind: str, value: object | None = None) -> Token:
        token = self.peek()
        if not self.at(kind, value):
            wanted = value if value is not None else kind
            raise self.error(f"expected {wanted}, got {self._describe(token)}")
        return self.advance()

    def expect_one_of(self, *kinds: str) -> Token:
        token = self.peek()
        if token.kind not in kinds:
            wanted = " or ".join(kinds)
            raise self.error(f"expected {wanted}, got {self._describe(token)}")
        return self.advance()

    def _describe(self, token: Token) -> str:
        if token.kind == "EOF":
            return "end of file"
        return f"'{token.value}'"

    def optional_semicolon(self) -> None:
        if self.at("OP", ";"):
            self.advance()

    def optional_colon(self) -> None:
        if self.at("OP", ":"):
            self.advance()

    # -- types -------------------------------------------------------------
    def parse_type(self) -> str:
        base = str(self.expect("IDENT").value)
        if not self.at("OP", "["):
            return base
        open_token = self.advance()
        length_token = self.expect("INT")
        length = int(length_token.value)
        if length <= 0:
            raise self.error("array length must be positive", length_token)
        self.expect("OP", "]")
        if self.at("OP", "["):
            raise self.error("multidimensional arrays are not supported in "
                             "Grain v1", self.peek())
        return make_array_type(base, length)

    # -- program -----------------------------------------------------------
    def parse_program(self) -> Program:
        pos = self.peek().pos
        program = Program(pos=pos)
        while self.peek().kind != "EOF":
            if self.at("KW", "extern"):
                program.externs.append(self.parse_extern())
            elif self.at("KW", "func"):
                program.functions.append(self.parse_function())
            elif self.at("KW", "entity"):
                program.entities.append(self.parse_entity())
            elif self.at("KW", "scene"):
                program.scenes.append(self.parse_scene())
            elif self.at("KW", "game"):
                if program.game is not None:
                    raise self.error("duplicate 'game' declaration")
                program.game = self.parse_game()
            else:
                raise self.error(
                    f"expected 'extern', 'func', 'entity', 'scene' or 'game', "
                    f"got {self._describe(self.peek())}")
        return program

    def parse_extern(self) -> ExternDecl:
        token = self.expect("KW", "extern")
        type_name = self.expect("IDENT").value
        name = self.expect("IDENT").value
        self.optional_semicolon()
        return ExternDecl(str(type_name), str(name), token.pos)

    def parse_params(self) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        while not self.at("OP", ")"):
            name = str(self.expect("IDENT").value)
            if self.at("OP", ":"):
                self.advance()
                type_name = self.parse_type()
            else:
                self.fail_missing_annotation(name)
            params.append((name, type_name))
            if self.at("OP", ","):
                self.advance()
                continue
            break
        self.expect("OP", ")")
        return params

    def fail_missing_annotation(self, name: str) -> None:
        raise self.error(f"parameter '{name}' needs a type annotation "
                         f"(e.g. '{name}: int')")

    def parse_function(self) -> FunctionDecl:
        token = self.expect("KW", "func")
        name = str(self.expect("IDENT").value)
        self.expect("OP", "(")
        params = self.parse_params()
        self.expect("OP", "->")
        return_type = self.parse_type()
        body = self.parse_block()
        return FunctionDecl(name, params, return_type, body, token.pos)

    def parse_entity(self) -> EntityDecl:
        token = self.expect("KW", "entity")
        name = str(self.expect("IDENT").value)
        self.optional_colon()
        self.expect("OP", "{")
        fields, handlers = self.parse_members(allowed_handlers={
            "on_spawn", "on_update", "on_draw"})
        self.expect("OP", "}")
        return EntityDecl(name, fields, handlers, token.pos)

    def parse_scene(self) -> SceneDecl:
        token = self.expect("KW", "scene")
        name = str(self.expect("IDENT").value)
        self.optional_colon()
        self.expect("OP", "{")
        fields, handlers = self.parse_members(allowed_handlers={
            "on_load", "on_unload", "on_update", "on_draw"})
        self.expect("OP", "}")
        return SceneDecl(name, fields, handlers, token.pos)

    def parse_members(self, allowed_handlers: set[str]):
        fields: list[FieldDecl] = []
        handlers: dict[str, Handler] = {}
        while not self.at("OP", "}"):
            if self.peek().kind == "EOF":
                raise self.error("unterminated declaration, expected '}'")
            if self.peek().kind == "KW" and str(self.peek().value).startswith("on_"):
                handler = self.parse_handler()
                if handler.name not in allowed_handlers:
                    raise self.error(
                        f"handler '{handler.name}' is not valid here; "
                        f"expected {', '.join(sorted(allowed_handlers))}",
                        Token("KW", handler.name, handler.pos or SourcePos(1, 1)))
                if handler.name in handlers:
                    raise self.error(f"duplicate handler '{handler.name}'")
                handlers[handler.name] = handler
                continue
            fields.append(self.parse_field())
        return fields, handlers

    def parse_field(self) -> FieldDecl:
        token = self.expect("IDENT")
        name = str(token.value)
        type_name = None
        if self.at("OP", ":"):
            self.advance()
            type_name = self.parse_type()
        self.expect("OP", "=")
        init = self.parse_expression()
        self.optional_semicolon()
        return FieldDecl(name, init, type_name, token.pos)

    def parse_handler(self) -> Handler:
        token = self.expect("KW")
        name = str(token.value)
        self.expect("OP", "(")
        params = self.parse_params()
        body = self.parse_block()
        return Handler(name, body, params, token.pos)

    def parse_game(self) -> GameDecl:
        token = self.expect("KW", "game")
        self.optional_colon()
        self.expect("OP", "{")
        settings: dict[str, object] = {}
        handlers: dict[str, Handler] = {}
        while not self.at("OP", "}"):
            if self.peek().kind == "EOF":
                raise self.error("unterminated 'game' block, expected '}'")
            if self.peek().kind == "KW" and str(self.peek().value).startswith("on_"):
                handler = self.parse_handler()
                if handler.name not in {"on_init", "on_update", "on_draw"}:
                    raise self.error(
                        f"handler '{handler.name}' is not valid in 'game'",
                        Token("KW", handler.name, handler.pos or SourcePos(1, 1)))
                if handler.name in handlers:
                    raise self.error(f"duplicate handler '{handler.name}'")
                handlers[handler.name] = handler
                continue
            name_token = self.expect("IDENT")
            name = str(name_token.value)
            self.expect("OP", "=")
            if name == "required_buttons":
                self.expect("OP", "[")
                buttons: list[str] = []
                while not self.at("OP", "]"):
                    buttons.append(str(self.expect("IDENT").value))
                    if self.at("OP", ","):
                        self.advance()
                        continue
                    break
                self.expect("OP", "]")
                settings[name] = buttons
            else:
                value = self.expect_one_of("INT", "STRING", "FIXED")
                settings[name] = (int(value.value) if value.kind == "INT"
                                  else value.value)
            self.optional_semicolon()
        self.expect("OP", "}")
        return GameDecl(settings, handlers, token.pos)

    # -- statements --------------------------------------------------------
    def parse_block(self) -> list[Stmt]:
        self.optional_colon()
        self.expect("OP", "{")
        statements: list[Stmt] = []
        while not self.at("OP", "}"):
            if self.peek().kind == "EOF":
                raise self.error("unterminated block, expected '}'")
            statements.append(self.parse_statement())
        self.expect("OP", "}")
        return statements

    def parse_statement(self) -> Stmt:
        if self.at("KW", "var"):
            return self.parse_var_decl()
        if self.at("KW", "if"):
            return self.parse_if()
        if self.at("KW", "while"):
            return self.parse_while()
        if self.at("KW", "return"):
            token = self.advance()
            value = None
            if not self.at("OP", ";") and not self.at("OP", "}"):
                value = self.parse_expression()
            self.optional_semicolon()
            return ReturnStmt(value, token.pos)

        expression = self.parse_expression()
        if self.peek().kind == "OP" and self.peek().value in ASSIGN_OPS:
            op = str(self.advance().value)
            if not isinstance(expression, (Name, Attr, Index)):
                raise self.error("assignment target must be a variable, field "
                                 "or array element",
                                 expression.pos or self.peek().pos)
            value = self.parse_expression()
            self.optional_semicolon()
            return Assign(expression, op, value, expression.pos or self.peek().pos)
        self.optional_semicolon()
        return ExprStmt(expression, expression.pos or self.peek().pos)

    def parse_var_decl(self) -> VarDecl:
        token = self.expect("KW", "var")
        name = str(self.expect("IDENT").value)
        type_name = None
        if self.at("OP", ":"):
            self.advance()
            type_name = self.parse_type()
        self.expect("OP", "=")
        init = self.parse_expression()
        self.optional_semicolon()
        return VarDecl(name, init, type_name, token.pos)

    def parse_if(self) -> IfStmt:
        token = self.expect("KW", "if")
        branches: list[tuple[Expr, list[Stmt]]] = []
        self.expect("OP", "(")
        condition = self.parse_expression()
        self.expect("OP", ")")
        branches.append((condition, self.parse_block()))
        while self.at("KW", "elif"):
            self.advance()
            self.expect("OP", "(")
            condition = self.parse_expression()
            self.expect("OP", ")")
            branches.append((condition, self.parse_block()))
        else_body = None
        if self.at("KW", "else"):
            self.advance()
            else_body = self.parse_block()
        return IfStmt(branches, else_body, token.pos)

    def parse_while(self) -> WhileStmt:
        token = self.expect("KW", "while")
        self.expect("OP", "(")
        condition = self.parse_expression()
        self.expect("OP", ")")
        return WhileStmt(condition, self.parse_block(), token.pos)

    # -- expressions -------------------------------------------------------
    def parse_expression(self) -> Expr:
        return self.parse_or()

    def parse_or(self) -> Expr:
        node = self.parse_and()
        while self.at("KW", "or"):
            token = self.advance()
            node = Binary("or", node, self.parse_and(), token.pos)
        return node

    def parse_and(self) -> Expr:
        node = self.parse_comparison()
        while self.at("KW", "and"):
            token = self.advance()
            node = Binary("and", node, self.parse_comparison(), token.pos)
        return node

    def parse_comparison(self) -> Expr:
        node = self.parse_additive()
        while self.peek().kind == "OP" and self.peek().value in {
                "==", "!=", "<", ">", "<=", ">="}:
            token = self.advance()
            node = Binary(str(token.value), node, self.parse_additive(),
                          token.pos)
        return node

    def parse_additive(self) -> Expr:
        node = self.parse_multiplicative()
        while self.peek().kind == "OP" and self.peek().value in {"+", "-"}:
            token = self.advance()
            node = Binary(str(token.value), node, self.parse_multiplicative(),
                          token.pos)
        return node

    def parse_multiplicative(self) -> Expr:
        node = self.parse_unary()
        while self.peek().kind == "OP" and self.peek().value in {"*", "/"}:
            token = self.advance()
            node = Binary(str(token.value), node, self.parse_unary(), token.pos)
        return node

    def parse_unary(self) -> Expr:
        if self.peek().kind == "OP" and self.peek().value == "-":
            token = self.advance()
            return Unary("-", self.parse_unary(), token.pos)
        if self.at("KW", "not"):
            token = self.advance()
            return Unary("not", self.parse_unary(), token.pos)
        return self.parse_postfix()

    def parse_postfix(self) -> Expr:
        node = self.parse_primary()
        while True:
            if self.at("OP", "."):
                token = self.advance()
                name = str(self.expect("IDENT").value)
                node = Attr(node, name, token.pos)
                continue
            if self.at("OP", "["):
                token = self.advance()
                index = self.parse_expression()
                self.expect("OP", "]")
                node = Index(node, index, token.pos)
                continue
            break
        return node

    def parse_primary(self) -> Expr:
        token = self.peek()
        if token.kind == "INT":
            self.advance()
            return Literal("int", int(token.value), token.pos)
        if token.kind == "FIXED":
            self.advance()
            return Literal("fixed", str(token.value), token.pos)
        if token.kind == "STRING":
            self.advance()
            return Literal("string", str(token.value), token.pos)
        if self.at("KW", "true") or self.at("KW", "false"):
            self.advance()
            return Literal("bool", token.value == "true", token.pos)
        if self.at("KW", "self"):
            self.advance()
            return Name("self", token.pos)
        if self.at("OP", "["):
            self.advance()
            elements: list[Expr] = []
            if not self.at("OP", "]"):
                while True:
                    elements.append(self.parse_expression())
                    if self.at("OP", ","):
                        self.advance()
                        continue
                    break
            self.expect("OP", "]")
            if not elements:
                raise self.error("empty array literals are not supported in "
                                 "Grain v1", token)
            return ArrayLiteral(elements, token.pos)
        if token.kind == "IDENT":
            self.advance()
            if self.at("OP", "("):
                self.advance()
                args: list[Expr] = []
                while not self.at("OP", ")"):
                    args.append(self.parse_expression())
                    if self.at("OP", ","):
                        self.advance()
                        continue
                    break
                self.expect("OP", ")")
                return Call(str(token.value), args, token.pos)
            return Name(str(token.value), token.pos)
        if self.at("OP", "("):
            self.advance()
            node = self.parse_expression()
            self.expect("OP", ")")
            return node
        raise self.error(f"expected expression, got {self._describe(token)}")


def parse(text: str, filename: str = "<grain>") -> Program:
    """Tokenize and parse *text* into a Program."""
    return Parser(tokenize(text, filename), filename).parse_program()
