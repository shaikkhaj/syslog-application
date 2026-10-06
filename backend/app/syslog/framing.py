"""RFC 6587 stream framing for the TCP syslog transport.

Two framing styles are supported:

* **non-transparent** — messages are delimited by a newline (most common);
* **octet-counted** — ``LEN SP PAYLOAD`` where ``LEN`` is the payload size.

The decoder is a pure, incrementally-fed state machine so it can be unit
tested without opening sockets. TLS (RFC 5425 style) will reuse this decoder
inside a TLS transport added in a later phase.
"""

from __future__ import annotations


class TcpFrameDecoder:
    """Incrementally extracts syslog frames from a TCP byte stream."""

    def __init__(self, max_bytes: int = 65536) -> None:
        self.max_bytes = max_bytes
        self._buffer = bytearray()
        self.errors = 0

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[bytes]:
        """Append bytes and return every complete frame now available."""
        self._buffer.extend(data)
        frames: list[bytes] = []
        while self._buffer:
            first = self._buffer[0]
            if 48 <= first <= 57:  # '0'-'9' → octet-counted framing
                space_index = self._buffer.find(b" ")
                if space_index == -1:
                    if len(self._buffer) > 12:  # header cannot be this long
                        self._discard("invalid octet-count header")
                    break
                try:
                    count = int(self._buffer[:space_index])
                except ValueError:
                    self._discard("non-numeric octet count")
                    break
                if count <= 0 or count > self.max_bytes:
                    self._discard("octet count out of range")
                    break
                end = space_index + 1 + count
                if len(self._buffer) < end:
                    break  # payload still incomplete
                frames.append(bytes(self._buffer[space_index + 1 : end]))
                del self._buffer[:end]
            else:  # newline-delimited framing
                newline = self._buffer.find(b"\n")
                if newline == -1:
                    if len(self._buffer) > self.max_bytes:
                        self._discard("newline frame exceeds max size")
                    break
                frame = bytes(self._buffer[:newline]).rstrip(b"\r")
                del self._buffer[: newline + 1]
                if frame:
                    frames.append(frame)
        return frames

    def _discard(self, reason: str) -> None:
        self.errors += 1
        self._buffer.clear()
