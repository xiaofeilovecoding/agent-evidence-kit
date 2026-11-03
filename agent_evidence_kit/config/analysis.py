"""Shared analysis pipeline used by both CLI and Web adapters.

Takes raw bytes (or text) plus a fixed input format and returns the
language-neutral projection core. This is the single place the
parse→limit→diagnose chain exists.
"""
from __future__ import annotations

from .parsers import InputRejected, check_limits, decode_text, parse_document
from .diagnostics import analyze_document


def analyze_text(text: str, input_format: str) -> dict:
    document = parse_document(text, input_format)
    check_limits(document)
    return analyze_document(document)


def analyze_bytes(raw: bytes, input_format: str) -> dict:
    return analyze_text(decode_text(raw), input_format)
