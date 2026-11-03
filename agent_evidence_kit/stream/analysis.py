"""Shared analysis pipeline: byte chunks -> SSE events -> projection core."""
from __future__ import annotations

from .parsers import InputRejected, SSEParser, MAX_INPUT_BYTES
from .diagnostics import analyze_events


def analyze_chunks(chunks) -> dict:
    parser = SSEParser()
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > MAX_INPUT_BYTES:
            raise InputRejected("INPUT_TOO_LARGE")
        parser.feed(chunk)
    parser.finish()
    return analyze_events(parser.events, parser.unterminated_tail)


def analyze_bytes(raw: bytes, chunk_size: int = 4096) -> dict:
    return analyze_chunks(
        raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)
    )
