"""Unit tests for RFC 6587 TCP stream framing."""

from app.syslog.framing import TcpFrameDecoder


class TestNewlineFraming:
    def test_single_frame(self):
        decoder = TcpFrameDecoder()
        assert decoder.feed(b"<134>hello world\n") == [b"<134>hello world"]

    def test_crlf_and_multiple_frames(self):
        decoder = TcpFrameDecoder()
        frames = decoder.feed(b"<134>one\r\n<134>two\n")
        assert frames == [b"<134>one", b"<134>two"]

    def test_partial_frame_across_chunks(self):
        decoder = TcpFrameDecoder()
        assert decoder.feed(b"<134>par") == []
        assert decoder.feed(b"tial") == []
        assert decoder.feed(b" message\n") == [b"<134>partial message"]

    def test_oversized_stream_without_newline_is_discarded(self):
        decoder = TcpFrameDecoder(max_bytes=64)
        decoder.feed(b"x" * 65)
        assert decoder.errors == 1
        assert decoder.buffered == 0


class TestOctetCountedFraming:
    def test_single_frame(self):
        payload = b"<134>counted message"
        frame = str(len(payload)).encode() + b" " + payload
        decoder = TcpFrameDecoder()
        assert decoder.feed(frame) == [payload]

    def test_frames_split_across_chunks(self):
        payload = b"<134>counted message"
        frame = str(len(payload)).encode() + b" " + payload
        decoder = TcpFrameDecoder()
        assert decoder.feed(frame[:5]) == []
        assert decoder.feed(frame[5:]) == [payload]

    def test_multiple_frames_in_one_chunk(self):
        first = b"<134>first"
        second = b"<85>second"
        blob = (
            str(len(first)).encode() + b" " + first
            + str(len(second)).encode() + b" " + second
        )
        assert TcpFrameDecoder().feed(blob) == [first, second]

    def test_invalid_count_is_discarded(self):
        decoder = TcpFrameDecoder(max_bytes=100)
        decoder.feed(b"999999 nope")
        assert decoder.errors == 1
        assert decoder.buffered == 0

    def test_mixed_styles_across_decoders(self):
        decoder = TcpFrameDecoder()
        payload = b"<134>x"
        frames = decoder.feed(str(len(payload)).encode() + b" " + payload + b"\n<134>y\n")
        assert frames == [payload, b"<134>y"]
