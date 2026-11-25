"""AST nodes for Grain v0.

The grammar is deliberately small: declarations (extern/entity/scene/game),
typed fields, handlers and a statement/expression subset that maps one-to-one
onto the portable C API. Locations are kept on every node so diagnostics from
later phases can point back at source text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SourcePos


# ---- Expressions ---------------------------------------------------------

@dataclass
class Literal:
    kind: str                 # "int" | "fixed" | "bool" | "string"
    value: Any
    pos: SourcePos


@dataclass
class Name:
    name: str
    pos: SourcePos


@dataclass
class Unary:
    op: str                   # "-" | "not"
    operand: "Expr"
    pos: SourcePos


@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    pos: SourcePos


@dataclass
class Call:
    callee: str
    args: list["Expr"] = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class Attr:
    obj: "Expr"
    field: str
    pos: SourcePos


Expr = Literal | Name | Unary | Binary | Call | Attr


# ---- Statements ----------------------------------------------------------

@dataclass
class Assign:
    target: Expr
    op: str                   # "=" | "+=" | "-=" | "*=" | "/="
    value: Expr
    pos: SourcePos


@dataclass
class ExprStmt:
    expr: Expr
    pos: SourcePos


@dataclass
class IfStmt:
    branches: list[tuple[Expr, list["Stmt"]]] = field(default_factory=list)
    else_body: list["Stmt"] | None = None
    pos: SourcePos | None = None


@dataclass
class WhileStmt:
    cond: Expr
    body: list["Stmt"] = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class ReturnStmt:
    value: Expr | None = None
    pos: SourcePos | None = None


Stmt = Assign | ExprStmt | IfStmt | WhileStmt | ReturnStmt


# ---- Declarations --------------------------------------------------------

@dataclass
class ExternDecl:
    type_name: str
    name: str
    pos: SourcePos


@dataclass
class FieldDecl:
    name: str
    init: Expr
    type_name: str | None = None
    pos: SourcePos | None = None


@dataclass
class Handler:
    name: str
    body: list[Stmt] = field(default_factory=list)
    params: list[tuple[str, str | None]] = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class EntityDecl:
    name: str
    fields: list[FieldDecl] = field(default_factory=list)
    handlers: dict[str, Handler] = field(default_factory=dict)
    pos: SourcePos | None = None


@dataclass
class SceneDecl:
    name: str
    fields: list[FieldDecl] = field(default_factory=list)
    handlers: dict[str, Handler] = field(default_factory=dict)
    pos: SourcePos | None = None


@dataclass
class GameDecl:
    settings: dict[str, Any] = field(default_factory=dict)
    handlers: dict[str, Handler] = field(default_factory=dict)
    pos: SourcePos | None = None


@dataclass
class Program:
    externs: list[ExternDecl] = field(default_factory=list)
    entities: list[EntityDecl] = field(default_factory=list)
    scenes: list[SceneDecl] = field(default_factory=list)
    game: GameDecl | None = None
    pos: SourcePos | None = None
