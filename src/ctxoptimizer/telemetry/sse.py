"""Incremental Server-Sent Events decoder (WHATWG event-stream grammar).

Byte-buffered so a chunk can split a line or a multi-byte UTF-8 character, and
bounded so a malicious stream cannot grow memory without limit. The decoder only
frames events; provider parsers interpret the JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_LINE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_EVENT_BYTES = 8 * 1024 * 1024


class SSEFrameError(ValueError):
    """Raised when a frame exceeds the configured memory bound."""


@dataclass(frozen=True, slots=True)
class SSEEvent:
    event: str | None
    data: str
    id: str | None = None
    retry: int | None = None


class SSEDecoder:
    """Feed it bytes, receive complete events. Tolerates CR, LF and CRLF."""

    def __init__(
        self,
        *,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES,
    ) -> None:
        self._buffer = bytearray()
        self._event: str | None = None
        self._data: list[str] = []
        self._data_bytes = 0
        self._last_id: str | None = None
        self._retry: int | None = None
        self._first_line = True
        self._max_line = max_line_bytes
        self._max_event = max_event_bytes

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        """Append bytes and return every event completed by this chunk."""
        self._buffer.extend(chunk)
        events: list[SSEEvent] = []
        while True:
            line = self._pop_line()
            if line is None:
                break
            event = self._process_line(line)
            if event is not None:
                events.append(event)
        if len(self._buffer) > self._max_line:
            raise SSEFrameError("SSE line exceeds the configured limit")
        return events

    def finish(self) -> list[SSEEvent]:
        """Flush a trailing partial line and any pending data at EOF."""
        events: list[SSEEvent] = []
        if self._buffer:
            raw = bytes(self._buffer).rstrip(b"\r")
            self._buffer.clear()
            event = self._process_line(raw)
            if event is not None:
                events.append(event)
        event = self._dispatch()
        if event is not None:
            events.append(event)
        return events

    def _pop_line(self) -> bytes | None:
        cr = self._buffer.find(b"\r")
        lf = self._buffer.find(b"\n")
        candidates = [index for index in (cr, lf) if index >= 0]
        if not candidates:
            return None
        index = min(candidates)
        if self._buffer[index] == 13:
            if index + 1 == len(self._buffer):
                return None
            end = index + 2 if self._buffer[index + 1] == 10 else index + 1
        else:
            end = index + 1
        line = bytes(self._buffer[:index])
        del self._buffer[:end]
        return line

    def _process_line(self, raw: bytes) -> SSEEvent | None:
        line = raw.decode("utf-8", errors="replace")
        if self._first_line:
            line = line.removeprefix("\ufeff")
            self._first_line = False
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._data.append(value)
            self._data_bytes += len(value.encode("utf-8"))
            if self._data_bytes > self._max_event:
                raise SSEFrameError("SSE event exceeds the configured limit")
        elif field == "id":
            if "\0" not in value:
                self._last_id = value
        elif field == "retry":
            try:
                self._retry = int(value)
            except ValueError:
                pass
        return None

    def _dispatch(self) -> SSEEvent | None:
        if not self._data and self._event is None:
            self._retry = None
            return None
        event = SSEEvent(
            event=self._event,
            data="\n".join(self._data),
            id=self._last_id,
            retry=self._retry,
        )
        self._event = None
        self._data = []
        self._data_bytes = 0
        self._retry = None
        return event


__all__ = [
    "DEFAULT_MAX_EVENT_BYTES",
    "DEFAULT_MAX_LINE_BYTES",
    "SSEDecoder",
    "SSEEvent",
    "SSEFrameError",
]
