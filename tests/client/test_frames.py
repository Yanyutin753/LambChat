"""流式帧编解码：自洽 torture + 服务端/client 两侧字节级互锁。"""

import struct

import pytest

from lambchat_sandbox import frames as client_frames


def _server_frames():
    from src.infra.sandbox.relay import _frames as server_frames

    return server_frames


def test_encode_parse_roundtrip_boundaries():
    """空帧、二进制含零字节、恰好上限帧——roundtrip 逐字节一致。"""
    for ftype in (
        client_frames.FRAME_META,
        client_frames.FRAME_DATA,
        client_frames.FRAME_EOF,
        client_frames.FRAME_ERROR,
    ):
        for payload in (b"", b"\x00\x01\xff", bytes(range(256)) * 4):
            wire = client_frames.encode_frame(ftype, payload)
            parsed = client_frames.try_parse_frame(wire)
            assert parsed == (ftype, payload, b"")


def test_parse_partial_frames_wait_for_more():
    """截断的头部/载荷返回 None，补齐后成功——流式缓冲的增量语义。"""
    wire = client_frames.encode_frame(client_frames.FRAME_DATA, b"abcdef")
    assert client_frames.try_parse_frame(wire[:3]) is None
    assert client_frames.try_parse_frame(wire[:8]) is None
    assert client_frames.try_parse_frame(wire) == (client_frames.FRAME_DATA, b"abcdef", b"")


def test_parse_multiple_frames_with_rest():
    """连续多帧：一帧 + 剩余缓冲原样返回。"""
    first = client_frames.encode_frame(client_frames.FRAME_META, b"{}")
    second = client_frames.encode_frame(client_frames.FRAME_DATA, b"xy")
    ftype, payload, rest = client_frames.try_parse_frame(first + second)
    assert (ftype, payload) == (client_frames.FRAME_META, b"{}")
    assert rest == second


def test_oversized_frame_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        client_frames.try_parse_frame(
            struct.pack(">BI", client_frames.FRAME_DATA, client_frames.FRAME_PAYLOAD_MAX + 1)
        )


def test_client_server_codec_interlock():
    """两侧常量与编码字节级一致——防漂移互锁（对齐 _cmd_quote 模式）。"""
    server = _server_frames()
    assert client_frames.FRAME_META == server.FRAME_META == 0x01
    assert client_frames.FRAME_DATA == server.FRAME_DATA == 0x02
    assert client_frames.FRAME_EOF == server.FRAME_EOF == 0x03
    assert client_frames.FRAME_ERROR == server.FRAME_ERROR == 0x04
    assert client_frames.FRAME_PAYLOAD_MAX == server.FRAME_PAYLOAD_MAX
    assert client_frames._HEADER_SIZE == server._HEADER_SIZE == 5

    payload = bytes(range(256)) * 16
    assert client_frames.encode_frame(0x02, payload) == server.encode_frame(0x02, payload)
