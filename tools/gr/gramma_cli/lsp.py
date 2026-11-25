"""A dependency-free Grain language server (JSON-RPC over stdio).

It is deliberately small: one document at a time, full-text sync, and a
single-file symbol index built from the compiler's own lexer/parser. The VS Code
extension talks to it with a tiny LSP client; the same JSON protocol can be
driven from tests without installing VS Code.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

# The compiler lives in pipeline/, which main.py puts on sys.path before this
# module is imported. Keep the import local to avoid a circular CLI dependency.
from gramma_pipeline.grain import (  # noqa: E402
    GrainError, SourcePos, Symbol, builtin_symbols, collect_symbols, parse,
    tokenize, typecheck)
from gramma_pipeline.grain.lexer import Token  # noqa: E402


COMPLETION_KINDS = {
    "keyword": 14,      # Keyword
    "builtin": 3,       # Function
    "constant": 20,     # Constant
    "extern": 21,       # Module
    "function": 3,      # Function
    "entity": 7,        # Class
    "scene": 7,         # Class
    "field": 5,         # Field
    "local": 6,         # Variable
    "parameter": 6,     # Variable
    "type": 22,         # Struct
}


@dataclass
class Document:
    uri: str
    text: str = ""
    tokens: list[Token] = field(default_factory=list)
    symbols: list = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    fields: dict[str, dict[str, str]] = field(default_factory=dict)

    def update(self, text: str) -> None:
        self.text = text
        self.tokens = []
        self.symbols = list(builtin_symbols())
        self.diagnostics = []
        self.fields = {}
        try:
            self.tokens = tokenize(text, self.uri)
        except GrainError as error:
            self.diagnostics = [self._diagnostic(error)]
            return
        try:
            program = parse(text, self.uri)
            checker = typecheck(program, self.uri)
            self.fields = dict(checker.entity_fields)
            self.fields.update(checker.scene_fields)
            self.symbols += collect_symbols(program, self.tokens)
        except GrainError as error:
            self.diagnostics = [self._diagnostic(error)]
            if "program" in locals():
                self.symbols += collect_symbols(program, self.tokens)

    @staticmethod
    def _diagnostic(error: GrainError) -> dict:
        return {
            "range": {
                "start": {"line": error.pos.line - 1,
                          "character": error.pos.col - 1},
                "end": {"line": error.pos.line - 1,
                        "character": error.pos.col},
            },
            "severity": 1,
            "source": "grain",
            "message": error.message,
        }

    def token_at(self, line: int, character: int) -> Token | None:
        for token in self.tokens:
            if token.kind == "EOF" or token.pos.line != line + 1:
                continue
            start = token.pos.col - 1
            end = start + len(str(token.value))
            if start <= character < end or character == start:
                return token
        return None

    def tokens_named(self, name: str) -> Iterable[Token]:
        for token in self.tokens:
            if token.kind in ("IDENT", "KW") and token.value == name:
                yield token

    @staticmethod
    def token_range(token: Token) -> dict:
        line = token.pos.line - 1
        start = token.pos.col - 1
        return {
            "start": {"line": line, "character": start},
            "end": {"line": line, "character": start + len(str(token.value))},
        }

    def owner_at(self, line: int, character: int) -> str | None:
        """Return the entity/scene/function name containing a position."""
        pos = (line + 1, character + 1)
        best: tuple[tuple[int, int], str] | None = None
        for symbol in self.symbols:
            if symbol.kind not in ("entity", "scene", "function"):
                continue
            key = (symbol.pos.line, symbol.pos.col)
            if key <= pos and (best is None or key > best[0]):
                best = (key, symbol.name)
        return best[1] if best is not None else None

    def declarations(self) -> list:
        return [symbol for symbol in self.symbols
                if symbol.kind not in ("keyword", "builtin", "constant",
                                       "type")]


def _position(params: dict) -> tuple[int, int]:
    position = params["position"]
    return int(position["line"]), int(position["character"])


class LanguageServer:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    def process(self, message: dict) -> list[dict]:
        method = message.get("method")
        params = message.get("params") or {}
        identifier = message.get("id")
        result: Any = None
        if method == "initialize":
            result = {
                "capabilities": {
                    "textDocumentSync": 1,
                    "completionProvider": {
                        "triggerCharacters": [".", "("],
                        "resolveProvider": False,
                    },
                    "definitionProvider": True,
                    "renameProvider": True,
                    "hoverProvider": True,
                    "documentSymbolProvider": True,
                },
                "serverInfo": {"name": "gramma-grain", "version": "0.2.0"},
            }
        elif method == "initialized":
            return []
        elif method == "textDocument/didOpen":
            document = self.documents.get(
                params["textDocument"]["uri"])
            if document is None:
                document = Document(params["textDocument"]["uri"])
                self.documents[document.uri] = document
            document.update(params["textDocument"]["text"])
            return [self._publish(document)]
        elif method == "textDocument/didChange":
            document = self.documents.get(params["textDocument"]["uri"])
            if document is not None:
                changes = params.get("contentChanges") or []
                if changes:
                    document.update(changes[-1]["text"])
                    return [self._publish(document)]
        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]
            self.documents.pop(uri, None)
            return [{
                "jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": []},
            }]
        elif method == "textDocument/completion":
            result = self._completion(params)
        elif method == "textDocument/definition":
            result = self._definition(params)
        elif method == "textDocument/rename":
            result = self._rename(params)
        elif method == "textDocument/hover":
            result = self._hover(params)
        elif method == "textDocument/documentSymbol":
            result = self._document_symbols(params)
        elif method == "shutdown":
            result = None
        elif method == "exit":
            return []
        elif method is not None and identifier is not None:
            return [self._error(identifier, -32601,
                                f"method not found: {method}")]

        if identifier is None:
            return []
        return [{"jsonrpc": "2.0", "id": identifier, "result": result}]

    @staticmethod
    def _error(identifier: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": identifier,
                "error": {"code": code, "message": message}}

    @staticmethod
    def _publish(document: Document) -> dict:
        return {
            "jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
            "params": {"uri": document.uri,
                       "diagnostics": document.diagnostics},
        }

    def _document(self, params: dict) -> Document | None:
        return self.documents.get(params["textDocument"]["uri"])

    def _completion(self, params: dict) -> list[dict]:
        document = self._document(params)
        if document is None:
            return []
        line, character = _position(params)
        tokens = [token for token in document.tokens
                  if token.pos.line == line + 1
                  and token.pos.col - 1 < character]
        dot = bool(tokens and tokens[-1].kind == "OP"
                   and tokens[-1].value == ".")
        seen: set[tuple[str, str]] = set()
        items: list[dict] = []
        owner = document.owner_at(line, character)
        candidates = list(document.declarations())
        if dot and owner in document.fields:
            candidates = [symbol for symbol in candidates
                          if symbol.kind == "field"
                          and symbol.name in document.fields[owner]]
        elif dot:
            candidates = []
        else:
            candidates += builtin_symbols()
            if owner in document.fields:
                candidates += [
                    Symbol(name, "field", type_name, SourcePos(1, 1))
                    for name, type_name in document.fields[owner].items()]
        for symbol in candidates:
            key = (symbol.name, symbol.kind)
            if key in seen or not symbol.name.isidentifier():
                continue
            seen.add(key)
            items.append({
                "label": symbol.name,
                "kind": COMPLETION_KINDS.get(symbol.kind, 6),
                "detail": getattr(symbol, "detail", ""),
            })
        return items

    def _definition(self, params: dict) -> list[dict]:
        document = self._document(params)
        if document is None:
            return []
        line, character = _position(params)
        token = document.token_at(line, character)
        if token is None or token.kind not in ("IDENT", "KW"):
            return []
        name = str(token.value)
        tokens = list(document.tokens)
        index = next(i for i, candidate in enumerate(tokens)
                     if candidate is token)
        previous = tokens[index - 1] if index > 0 else None
        owner = document.owner_at(line, character)
        candidates = [symbol for symbol in document.declarations()
                      if symbol.name == name]
        if previous is not None and previous.kind == "OP" \
                and previous.value == "." and owner in document.fields:
            candidates = [symbol for symbol in candidates
                          if symbol.kind == "field"]
        if not candidates:
            return []
        symbol = candidates[0]
        return [{
            "uri": document.uri,
            "range": Document.token_range(
                Token("IDENT", symbol.name, symbol.pos)),
        }]

    def _rename(self, params: dict) -> dict | None:
        document = self._document(params)
        if document is None:
            return None
        line, character = _position(params)
        token = document.token_at(line, character)
        if token is None or token.kind not in ("IDENT", "KW"):
            return None
        name = str(token.value)
        if not any(symbol.name == name
                   for symbol in document.declarations()):
            return None
        new_name = params["newName"]
        edits = [{"range": Document.token_range(match), "newText": new_name}
                 for match in document.tokens_named(name)]
        return {"changes": {document.uri: edits}}

    def _hover(self, params: dict) -> dict | None:
        document = self._document(params)
        if document is None:
            return None
        line, character = _position(params)
        token = document.token_at(line, character)
        if token is None:
            return None
        for symbol in document.symbols:
            if symbol.name == token.value:
                return {"contents": {
                    "kind": "markdown",
                    "value": f"`{symbol.name}` — {symbol.detail}",
                }}
        return None

    def _document_symbols(self, params: dict) -> list[dict]:
        document = self._document(params)
        if document is None:
            return []
        kind_map = {"entity": 5, "scene": 5, "function": 6, "extern": 5,
                    "field": 8, "local": 13, "parameter": 13}
        result = []
        for symbol in document.declarations():
            fake = Token("IDENT", symbol.name, symbol.pos)
            result.append({
                "name": symbol.name,
                "kind": kind_map.get(symbol.kind, 13),
                "range": Document.token_range(fake),
                "selectionRange": Document.token_range(fake),
                "detail": getattr(symbol, "detail", ""),
            })
        return result


def encode(message: dict) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return (f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)


def read_messages(stream) -> Iterable[dict]:
    """Yield JSON-RPC messages from a stdio-like binary stream."""
    while True:
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if not line:
                return
            if line in (b"\r\n", b"\n"):
                break
            if b":" in line:
                key, value = line.decode("ascii").split(":", 1)
                headers[key.strip().lower()] = value.strip()
        if "content-length" not in headers:
            continue
        length = int(headers["content-length"])
        body = stream.read(length)
        if not body:
            return
        yield json.loads(body.decode("utf-8"))


def serve(input_stream=None, output_stream=None) -> int:
    """Run the stdio server. Defaults to process stdin/stdout."""
    source = input_stream if input_stream is not None else sys.stdin.buffer
    sink = output_stream if output_stream is not None else sys.stdout.buffer
    server = LanguageServer()
    for message in read_messages(source):
        try:
            replies = server.process(message)
        except Exception as error:  # keep the protocol alive on bad requests
            identifier = message.get("id") if isinstance(message, dict) else None
            replies = [LanguageServer._error(
                identifier, -32603, str(error))]
        for reply in replies:
            sink.write(encode(reply))
        sink.flush()
    return 0
