"""Limited reading and strict parsing of configuration documents.

Standard library only. Every limit is enforced on the bytes actually
read, never on stat() alone. Paths are program arguments and are never
echoed into errors.

R01 fix: a bounded bracket-depth pre-scan rejects deeply nested input
*before* the recursive parser runs, so ~1500-level JSON/TOML documents
are rejected with the stable LIMIT_EXCEEDED code instead of crashing
with RecursionError and leaking source paths via a traceback.
"""
from __future__ import annotations

import json
import os
import tomllib

MAX_FILE_BYTES = 256 * 1024
MAX_DEPTH = 16
MAX_SERVICES = 32
_READ_CHUNK = 64 * 1024

_ALLOWED_EXTENSIONS = {".json", ".toml"}


class InputRejected(Exception):
    """A stable, fixed-code rejection; carries no user data."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def read_file_bytes(path: str) -> bytes:
    ext = os.path.splitext(path)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise InputRejected("UNSUPPORTED_FORMAT")
    try:
        with open(path, "rb") as handle:
            chunks = []
            total = 0
            while True:
                chunk = handle.read(_READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise InputRejected("INPUT_TOO_LARGE")
                chunks.append(chunk)
    except InputRejected:
        raise
    except OSError:
        raise InputRejected("INPUT_UNREADABLE") from None
    return b"".join(chunks)


def decode_text(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InputRejected("INVALID_ENCODING") from None


def bracket_depth(text: str) -> int:
    """Maximum nesting depth of ``{``/``[`` outside string literals.

    Iterative and bounded: it never recurses, so arbitrarily deep input
    cannot crash the checker. Comments (``#`` to end of line, TOML only)
    are skipped when ``toml_mode`` is set.
    """
    depth = 0
    max_depth = 0
    in_string = False
    quote = ""
    escaped = False
    in_comment = False
    in_line_string = False  # inside a " multi-line basic string (TOML)
    literal_multiline = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_comment:
            if ch == "\n":
                in_comment = False
            i += 1
            continue
        if in_string:
            if quote == '"':
                # Backslash escapes only apply to basic (double-quoted)
                # strings; TOML literal strings treat them as data.
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif in_line_string:
                    if text.startswith('"""', i):
                        in_string = False
                        in_line_string = False
                        i += 2
                elif ch == '"':
                    in_string = False
            else:
                if literal_multiline:
                    if text.startswith("'''", i):
                        in_string = False
                        literal_multiline = False
                        i += 2
                elif ch == "'":
                    in_string = False
            i += 1
            continue
        if ch == "#":
            # TOML comment; JSON documents cannot contain a bare '#' outside
            # strings, so treating it as a comment start is safe for both.
            in_comment = True
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            if text.startswith('"""', i):
                in_line_string = True
                i += 2
            elif text.startswith("'''", i):
                literal_multiline = True
                i += 2
            i += 1
            continue
        if ch in "{[":
            depth += 1
            if depth > max_depth:
                max_depth = depth
            i += 1
            continue
        if ch in "}]":
            if depth > 0:
                depth -= 1
            i += 1
            continue
        i += 1
    return max_depth


class _DuplicateKey(Exception):
    pass


def _reject_constant(name: str):
    raise ValueError(name)


def _object_pairs_no_duplicates(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _DuplicateKey
        seen.add(key)
    return dict(pairs)


def parse_document(text: str, fmt: str) -> object:
    if fmt not in ("json", "toml"):
        raise InputRejected("UNSUPPORTED_FORMAT")
    # Bounded pre-scan: anything whose bracket nesting exceeds the frozen
    # depth limit is rejected without invoking the (recursive) parser.
    if bracket_depth(text) > MAX_DEPTH:
        raise InputRejected("LIMIT_EXCEEDED")
    try:
        if fmt == "json":
            return json.loads(
                text,
                object_pairs_hook=_object_pairs_no_duplicates,
                parse_constant=_reject_constant,
            )
        return tomllib.loads(text)
    except _DuplicateKey:
        raise InputRejected("DUPLICATE_KEY") from None
    except RecursionError:
        # Defensive backstop: the pre-scan bounds real nesting, but the
        # parser itself must never escape as a traceback.
        raise InputRejected("LIMIT_EXCEEDED") from None
    except tomllib.TOMLDecodeError as exc:
        message = str(exc).lower()
        if "overwrite" in message or "twice" in message:
            raise InputRejected("DUPLICATE_KEY") from None
        raise InputRejected("INVALID_SYNTAX") from None
    except ValueError:
        raise InputRejected("INVALID_SYNTAX") from None


def container_depth(value: object) -> int:
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return 0
    deepest = 0
    for child in children:
        deepest = max(deepest, container_depth(child))
    return 1 + deepest


def check_limits(document: object) -> None:
    if container_depth(document) > MAX_DEPTH:
        raise InputRejected("LIMIT_EXCEEDED")
