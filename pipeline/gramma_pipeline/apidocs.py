"""Deterministic API reference generation from the public C headers.

The hand-written ``docs/api.md`` stays the narrative guide. This module emits
``docs/generated/api-reference.md``: a compact index of every public function,
type and constant with the declaration and its leading header comment. It uses
only the standard library so ``gr docs --check`` can run in a bare CI image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

FUNCTION_RE = re.compile(r"\b(gr_[A-Za-z0-9_]+)\s*\(")
TYPE_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*;")
ENUM_MEMBER_RE = re.compile(r"\b(GR_[A-Z0-9_]+)\b")


@dataclass
class Entry:
    name: str
    declaration: str
    doc: str = ""


@dataclass
class Header:
    path: str
    title: str
    summary: str = ""
    functions: list[Entry] = field(default_factory=list)
    types: list[Entry] = field(default_factory=list)
    macros: list[Entry] = field(default_factory=list)


def _clean_doc(lines: list[str]) -> str:
    """Turn a leading ``/* ... */`` comment into one prose paragraph."""
    parts: list[str] = []
    for line in lines:
        text = line.strip()
        if text.startswith("/*"):
            text = text[2:]
        if text.endswith("*/"):
            text = text[:-2]
        if text.startswith("*"):
            text = text[1:]
        text = text.strip()
        if not text or set(text) <= set("-="):
            continue
        if re.match(r"^[-A-Za-z ]+[-]{4,}$", text):
            continue
        parts.append(text)
    return " ".join(parts)


def _declaration(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines)
    return re.sub(r"\s+", " ", text).strip()


def parse_header(path: Path, root: Path) -> Header:
    """Parse public declarations and their preceding comments from *path*."""
    lines = path.read_text(encoding="utf-8").splitlines()
    relative = path.relative_to(root).as_posix()
    header = Header(path=relative, title=path.stem)

    pending_doc: list[str] = []
    buffer: list[str] = []
    in_comment = False
    brace_depth = 0
    for line in lines + [""]:
        stripped = line.strip()
        if in_comment:
            pending_doc.append(line)
            if "*/" in stripped:
                in_comment = False
            continue
        if stripped.startswith("/*"):
            pending_doc = [line]
            in_comment = "*/" not in stripped
            continue
        if brace_depth:
            buffer.append(line)
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0 and stripped.endswith(";"):
                brace_depth = 0
                _add_declaration(header, _declaration(buffer),
                                 _clean_doc(pending_doc))
                buffer = []
                pending_doc = []
            continue
        if not stripped or stripped.startswith("#ifndef") \
                or stripped.startswith("#define GRAMMA_") \
                or stripped.startswith("#include") \
                or stripped.startswith("#ifdef __cplusplus") \
                or stripped.startswith("#endif") \
                or stripped in {"extern \"C\" {", "}"}:
            continue
        if stripped.startswith("#define"):
            match = re.match(r"#define\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if match:
                header.macros.append(Entry(
                    match.group(1), stripped, _clean_doc(pending_doc)))
            pending_doc = []
            continue

        buffer.append(line)
        brace_depth = stripped.count("{") - stripped.count("}")
        if brace_depth > 0:
            continue
        if not stripped.endswith(";"):
            continue
        _add_declaration(header, _declaration(buffer), _clean_doc(pending_doc))
        buffer = []
        pending_doc = []

    header.title = _title_for(relative, header.title)
    return header


def _add_declaration(header: Header, declaration: str, doc: str) -> None:
    if declaration.startswith("typedef enum"):
        for member in ENUM_MEMBER_RE.findall(declaration):
            header.macros.append(Entry(member, member, doc))
        return
    if declaration.startswith("typedef") and "(*" not in declaration:
        matches = TYPE_NAME_RE.findall(declaration)
        if matches:
            header.types.append(Entry(matches[-1], declaration, doc))
        return
    match = FUNCTION_RE.search(declaration)
    if match is not None:
        header.functions.append(Entry(match.group(1), declaration, doc))


def _title_for(relative: str, fallback: str) -> str:
    titles = {
        "gramma/gramma.h": "Base API (gramma.h)",
        "gramma/types.h": "Public types (types.h)",
        "gramma/target.h": "Target limits and fixed-point helpers (target.h)",
        "gramma/bank.h": "Bank switching (bank.h)",
        "gramma/overlay.h": "Vblank overlays (overlay.h)",
        "gramma/target/gb/mapper.h": "Game Boy mapper (target/gb/mapper.h)",
        "gramma/target/nes/mapper.h": "NES mapper (target/nes/mapper.h)",
        "gramma/target/sms/mapper.h": "SMS/GG mapper (target/sms/mapper.h)",
    }
    return titles.get(relative, fallback)


def public_headers(repo: Path) -> list[Path]:
    include = repo / "core" / "include" / "gramma"
    return sorted(path for path in include.rglob("*.h")
                  if "internal" not in path.parts)


def _render_entry(entry: Entry) -> list[str]:
    lines: list[str] = []
    if entry.doc:
        lines.append(f"  {entry.doc}")
    lines.append("```c")
    lines.append(entry.declaration)
    lines.append("```")
    return lines


def build_api_reference(repo: Path) -> str:
    """Return the generated Markdown reference for *repo*."""
    include = repo / "core" / "include"
    headers = [parse_header(path, include) for path in public_headers(repo)]
    lines = [
        "# Generated API reference",
        "",
        "This file is generated from the public headers by "
        "`gr docs`. Edit the headers, then regenerate; the narrative guide "
        "lives in [`api.md`](../api.md). `gramma.h` does not include any "
        "opt-in header listed below.",
        "",
        "## Contents",
        "",
    ]
    for header in headers:
        anchor = header.path.replace("/", "-").replace(".h", "")
        lines.append(f"- [{header.title}](#{anchor})")
    lines.append("")
    for header in headers:
        anchor = header.path.replace("/", "-").replace(".h", "")
        lines += [f"## {header.title} {{#{anchor}}}", "",
                  f"Header: [`{header.path}`]"
                  f"(../../core/include/{header.path}).", ""]
        if header.summary:
            lines += [header.summary, ""]
        for section_name, entries in (
                ("Functions", header.functions),
                ("Types", header.types),
                ("Constants and macros", header.macros)):
            if not entries:
                continue
            lines += [f"### {section_name}", ""]
            for entry in entries:
                lines += [f"#### `{entry.name}`", ""]
                lines += _render_entry(entry)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_api_reference(repo: Path) -> Path:
    """Write the generated reference and return its path."""
    path = repo / "docs" / "generated" / "api-reference.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_api_reference(repo), encoding="utf-8")
    return path
