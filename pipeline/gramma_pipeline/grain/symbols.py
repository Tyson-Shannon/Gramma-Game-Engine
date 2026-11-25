"""Symbol index used by the Grain language server.

The compiler already has source positions on every AST node and tokens. This
module turns those into a small index for completion, go-to-definition and
single-file rename. It deliberately avoids external dependencies: the language
server speaks JSON-RPC over stdio and runs with bare Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .ast import (
    EntityDecl, ExternDecl, FieldDecl, FunctionDecl, GameDecl, Handler,
    Program, SceneDecl, VarDecl)
from .errors import SourcePos
from .lexer import Token, tokenize
from .typechecker import BUILTINS, CONSTANTS, PRIMITIVES

SymbolKind = Literal[
    "keyword", "builtin", "constant", "extern", "function", "entity",
    "scene", "field", "local", "parameter", "type"]


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: SymbolKind
    detail: str
    pos: SourcePos

    def as_lsp(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "detail": self.detail,
            "line": self.pos.line,
            "column": self.pos.col,
        }


def _find_name_token(tokens: list[Token], name: str,
                     after: SourcePos) -> SourcePos:
    """Locate the identifier token for a declaration whose keyword is at *after*."""
    for token in tokens:
        if (token.kind == "IDENT" and token.value == name
                and (token.pos.line, token.pos.col) >= (after.line, after.col)):
            return token.pos
    return after


def _walk_statements(body, owner: str, scope: str,
                     symbols: list[Symbol]) -> None:
    def visit(statements) -> None:
        for statement in statements:
            if isinstance(statement, VarDecl):
                symbols.append(Symbol(
                    statement.name, "local", statement.type_name or "var",
                    statement.pos or SourcePos(1, 1)))
            nested = getattr(statement, "body", None)
            if isinstance(nested, list):
                visit(nested)
            else_body = getattr(statement, "else_body", None)
            if isinstance(else_body, list):
                visit(else_body)
            for _condition, branch in getattr(statement, "branches", []):
                visit(branch)
    visit(body)


def collect_symbols(program: Program, tokens: list[Token]) -> list[Symbol]:
    """Collect declaration symbols from a parsed program."""
    symbols: list[Symbol] = []
    for extern in program.externs:
        symbols.append(Symbol(extern.name, "extern", extern.type_name,
                              _find_name_token(tokens, extern.name, extern.pos)))
    for function in program.functions:
        pos = _find_name_token(tokens, function.name, function.pos)
        signature = f"{function.return_type} {function.name}(" + ", ".join(
            f"{name}: {type_name}" for name, type_name in function.params) + ")"
        symbols.append(Symbol(function.name, "function", signature, pos))
        _walk_statements(function.body, function.name, "function", symbols)
    for entity in program.entities:
        _collect_owner(entity, "entity", tokens, symbols)
    for scene in program.scenes:
        _collect_owner(scene, "scene", tokens, symbols)
    if program.game is not None:
        for name, handler in program.game.handlers.items():
            pos = _find_name_token(tokens, name, handler.pos or program.game.pos
                                   or SourcePos(1, 1))
            symbols.append(Symbol(name, "field", "game handler", pos))
            _walk_statements(handler.body, "game", "game", symbols)
    return symbols


def _collect_owner(owner: EntityDecl | SceneDecl, kind: str,
                   tokens: list[Token], symbols: list[Symbol]) -> None:
    pos = _find_name_token(tokens, owner.name, owner.pos or SourcePos(1, 1))
    symbols.append(Symbol(owner.name, kind, kind, pos))
    for field in owner.fields:
        symbols.append(Symbol(field.name, "field", field.type_name or "field",
                              field.pos or pos))
    for name, handler in owner.handlers.items():
        handler_pos = _find_name_token(
            tokens, name, handler.pos or pos)
        symbols.append(Symbol(name, "field", f"{kind} handler", handler_pos))
        for param_name, param_type in handler.params:
            symbols.append(Symbol(
                param_name, "parameter", param_type,
                _find_name_token(tokens, param_name, handler_pos)))
        _walk_statements(handler.body, owner.name, kind, symbols)


def builtin_symbols() -> list[Symbol]:
    origin = SourcePos(1, 1)
    result = [Symbol(name, "builtin", f"({', '.join(params)}) -> {returns}",
                     origin)
              for name, (params, returns) in BUILTINS.items()]
    result += [Symbol(name, "constant", kind, origin)
               for name, kind in CONSTANTS.items()]
    result += [Symbol(name, "type", "Grain type", origin)
               for name in PRIMITIVES]
    result += [Symbol(name, "keyword", "keyword", origin)
               for name in ("entity", "scene", "game", "extern", "func",
                            "var", "if", "elif", "else", "while", "return",
                            "self", "true", "false", "and", "or", "not")]
    return result
