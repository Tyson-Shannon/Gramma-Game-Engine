"""Hand-written tokenizer for Grain.

Blocks are brace-delimited (GDScript-inspired keywords, unambiguous nesting).
Every token carries a line/column so parse and type errors can be reported in
the same `file:line:col: error:` format as the compiler front end.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import GrainError, SourcePos

KEYWORDS = {
    "entity", "scene", "game", "extern", "on_spawn", "on_update",
    "on_draw", "on_load", "on_unload", "on_init", "if", "elif", "else",
    "while", "return", "self", "true", "false", "and", "or", "not",
}

TWO_CHAR_OPS = {"+=", "-=", "*=", "/=", "==", "!=", "<=", ">="}
ONE_CHAR_OPS = set("+-*/=<>(){}[],:.;")


@dataclass(frozen=True)
class Token:
    kind: str                 # IDENT | INT | FIXED | STRING | KW | OP | EOF
    value: object
    pos: SourcePos


def tokenize(text: str, filename: str = "<grain>") -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    col = 1
    length = len(text)

    def here() -> SourcePos:
        return SourcePos(line, col)

    def advance() -> str:
        nonlocal index, line, col
        ch = text[index]
        index += 1
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        return ch

    while index < length:
        ch = text[index]
        if ch.isspace():
            advance()
            continue
        if ch == "#" or (ch == "/" and index + 1 < length
                         and text[index + 1] == "/"):
            while index < length and text[index] != "\n":
                advance()
            continue
        if ch == "/" and index + 1 < length and text[index + 1] == "*":
            start = here()
            advance()
            advance()
            closed = False
            while index < length:
                if text[index] == "*" and index + 1 < length \
                        and text[index + 1] == "/":
                    advance()
                    advance()
                    closed = True
                    break
                advance()
            if not closed:
                raise GrainError("unterminated block comment", filename, start)
            continue

        pos = here()

        if ch.isalpha() or ch == "_":
            word = ""
            while index < length and (text[index].isalnum()
                                      or text[index] == "_"):
                word += advance()
            kind = "KW" if word in KEYWORDS else "IDENT"
            tokens.append(Token(kind, word, pos))
            continue

        if ch.isdigit():
            number = ""
            while index < length and text[index].isdigit():
                number += advance()
            if index < length and text[index] == ".":
                if index + 1 >= length or not text[index + 1].isdigit():
                    raise GrainError("expected digits after '.'", filename,
                                     here())
                number += advance()
                while index < length and text[index].isdigit():
                    number += advance()
                tokens.append(Token("FIXED", number, pos))
            else:
                tokens.append(Token("INT", number, pos))
            continue

        if ch in "\"'":
            quote = advance()
            value = ""
            closed = False
            while index < length:
                current = advance()
                if current == quote:
                    closed = True
                    break
                if current == "\\":
                    if index >= length:
                        break
                    escaped = advance()
                    value += {
                        "n": "\n", "t": "\t", "r": "\r",
                        "\\": "\\", "\"": "\"", "'": "'",
                    }.get(escaped, escaped)
                else:
                    value += current
            if not closed:
                raise GrainError("unterminated string literal", filename, pos)
            tokens.append(Token("STRING", value, pos))
            continue

        pair = text[index:index + 2]
        if pair in TWO_CHAR_OPS:
            advance()
            advance()
            tokens.append(Token("OP", pair, pos))
            continue
        if ch in ONE_CHAR_OPS:
            advance()
            tokens.append(Token("OP", ch, pos))
            continue

        raise GrainError(f"unexpected character {ch!r}", filename, pos)

    tokens.append(Token("EOF", None, here()))
    return tokens
