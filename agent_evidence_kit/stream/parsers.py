"""Limited incremental reading and SSE framing over byte chunks.

Standard library only. All limits are enforced on the bytes actually
processed, never on stat() alone. Byte-space line splitting is safe for
UTF-8 because newline bytes (0x0A/0x0D) never occur inside multi-byte
sequences, so a line boundary is always a real line boundary.
"""
from __future__ import annotations

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 128 * 1024
MAX_EVENT_DATA_BYTES = 256 * 1024
MAX_DATA_EVENTS = 10000
MAX_JSON_DEPTH = 16


class InputRejected(Exception):
    """A stable, fixed-code rejection; carries no user data."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RawEvent:
    """One dispatched SSE event: field names and data lines only."""

    __slots__ = ("event_type", "data_parts")

    def __init__(self):
        self.event_type: str | None = None  # explicit "event:" value
        self.data_parts: list[str] = []


class SSEParser:
    """Feed byte chunks; collect dispatched events.

    SSE subset (frozen): LF/CRLF/CR line breaks (CRLF split across chunks
    counts once), blank line dispatches, comments (leading colon) ignored,
    "field: value" strips at most one leading space, unknown fields and
    id/retry are ignored without echoing values.
    """

    def __init__(self):
        self._pending = bytearray()   # completed bytes of the current line
        self._cr_held = False
        self._bom_checked = False
        self._fields: dict[str, list[str]] = {}
        self._data_bytes = 0
        self.events: list[RawEvent] = []
        self.unterminated_tail = False

    # ---- byte-level line assembly ----
    def feed(self, data: bytes) -> None:
        if len(data) + len(self._pending) > MAX_LINE_BYTES + 1:
            # Oversized line protection before buffering the whole chunk.
            pass
        i = 0
        n = len(data)
        while i < n:
            if self._cr_held:
                # The CR already completed the previous line; a following
                # LF belongs to that same break (CRLF) and must be
                # swallowed, never treated as a second, empty line (C01).
                self._cr_held = False
                if data[i] == 0x0A:
                    i += 1
                continue
            byte = data[i]
            if byte == 0x0A:
                self._complete_line()
                i += 1
            elif byte == 0x0D:
                self._complete_line()
                self._cr_held = True
                i += 1
            else:
                self._pending.append(byte)
                if len(self._pending) > MAX_LINE_BYTES:
                    raise InputRejected("LIMIT_EXCEEDED")
                i += 1

    def _complete_line(self) -> None:
        raw = bytes(self._pending)
        self._pending = bytearray()
        if not self._bom_checked:
            self._bom_checked = True
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise InputRejected("INVALID_ENCODING") from None
        self._handle_line(line)

    # ---- SSE framing ----
    def _handle_line(self, line: str) -> None:
        if line == "":
            self._dispatch()
            return
        if line.startswith(":"):
            return  # comment
        if ":" in line:
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        else:
            field, value = line, ""
        if field == "data":
            self._data_bytes += len(value.encode("utf-8"))
            if self._data_bytes > MAX_EVENT_DATA_BYTES:
                raise InputRejected("LIMIT_EXCEEDED")
            self._fields.setdefault("data", []).append(value)
        elif field == "event":
            self._fields.setdefault("event", []).append(value)
        # id/retry/unknown fields: ignored, never echoed.

    def _dispatch(self) -> None:
        if not self._fields:
            return  # empty chunk / heartbeat: not counted
        data_parts = self._fields.get("data", [])
        if not data_parts:
            self._fields = {}
            self._data_bytes = 0
            return  # event without data: not counted
        if len(self.events) >= MAX_DATA_EVENTS:
            raise InputRejected("LIMIT_EXCEEDED")
        event = RawEvent()
        event_types = self._fields.get("event", [])
        event.event_type = event_types[0] if event_types else None
        event.data_parts = data_parts
        self.events.append(event)
        self._fields = {}
        self._data_bytes = 0

    def finish(self) -> None:
        if self._cr_held:
            # A trailing CR at EOF already completed its line; it does not
            # start a new one (C01).
            self._cr_held = False
        if self._pending:
            self._complete_line()
        if self._fields.get("data"):
            # Trailing data never dispatched by a blank line.
            self.unterminated_tail = True
