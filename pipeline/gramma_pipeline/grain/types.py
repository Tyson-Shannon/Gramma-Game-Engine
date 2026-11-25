"""Shared type-name helpers for Grain.

Grain v1 keeps type names as strings in the AST. Scalars keep their source
spelling (``int``, ``fixed``, ...); fixed arrays are encoded as ``T[N]`` so the
same helpers work in the parser, typechecker and C back end.
"""

from __future__ import annotations

import re

ARRAY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\[([1-9][0-9]*)\]$")


def is_array_type(type_name: str | None) -> bool:
    return bool(type_name and ARRAY_RE.match(type_name))


def array_parts(type_name: str) -> tuple[str, int]:
    """Return ``(element_type, length)`` for a fixed array type."""
    match = ARRAY_RE.match(type_name)
    if match is None:
        raise ValueError(f"not a Grain array type: {type_name!r}")
    return match.group(1), int(match.group(2))


def make_array_type(element_type: str, length: int) -> str:
    if length <= 0:
        raise ValueError("array length must be positive")
    return f"{element_type}[{length}]"
