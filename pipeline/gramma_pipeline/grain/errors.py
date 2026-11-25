"""Diagnostics shared by the Grain lexer, parser and typechecker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePos:
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


class GrainError(ValueError):
    """A source-level error with an exact line/column location.

    Subclassing ValueError lets the existing ``gr`` dispatch report compiler
    diagnostics without a traceback.
    """

    def __init__(self, message: str, filename: str = "<grain>",
                 pos: SourcePos | None = None):
        self.message = message
        self.filename = filename
        self.pos = pos or SourcePos(1, 1)
        super().__init__(str(self))

    def __str__(self) -> str:
        return (f"{self.filename}:{self.pos.line}:{self.pos.col}: "
                f"error: {self.message}")

    def as_dict(self) -> dict:
        return {
            "filename": self.filename,
            "line": self.pos.line,
            "col": self.pos.col,
            "message": self.message,
        }


def format_errors(errors: list[GrainError]) -> str:
    """Render a batch of diagnostics, one per line."""
    return "\n".join(str(error) for error in errors)
