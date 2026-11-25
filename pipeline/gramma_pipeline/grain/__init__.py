"""Grain: a small statically typed language that transpiles to Gramma C.

Public entry points used by the CLI and the asset pipeline::

    from gramma_pipeline.grain import transpile_grain, check_grain

    source = transpile_grain(text, "game.grain")
    errors = check_grain(text, "game.grain")
"""

from __future__ import annotations

from pathlib import Path

from .codegen import CodeGenerator, transpile
from .errors import GrainError, SourcePos, format_errors
from .lexer import tokenize
from .parser import parse
from .typechecker import TypeChecker, typecheck


def check_grain(text: str, filename: str = "<grain>") -> list[GrainError]:
    """Return source diagnostics; an empty list means the program is valid."""
    try:
        typecheck(parse(text, filename), filename)
    except GrainError as error:
        return [error]
    return []


def transpile_grain(text: str, filename: str = "<grain>") -> str:
    """Parse, typecheck and emit C. Raises GrainError on invalid input."""
    return transpile(text, filename)[0]


def transpile_file(path: Path | str) -> str:
    path = Path(path)
    return transpile_grain(path.read_text(encoding="utf-8"), str(path))


__all__ = [
    "CodeGenerator", "GrainError", "SourcePos", "TypeChecker",
    "check_grain", "format_errors", "parse", "tokenize", "transpile",
    "transpile_file", "transpile_grain", "typecheck",
]
