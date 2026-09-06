"""流式传输二进制帧编解码（服务端侧）。

帧格式与语义见 client/lambchat_sandbox/frames.py 的模块文档——两侧字节级
同则，tests/client/test_frames.py torture 互锁。本模块只被 sandbox 路由
（解析 daemon 上行流）与 dispatch 流式消费器（解析 Redis list item）使用。
"""

from __future__ import annotations

import struct
from typing import Optional

FRAME_META = 0x01
FRAME_DATA = 0x02
FRAME_EOF = 0x03
FRAME_ERROR = 0x04

_HEADER = struct.Struct(">BI")  # type(1) + length(4)
_HEADER_SIZE = _HEADER.size  # 5

#: 单帧 payload 上限：与 client 侧同值互锁；data 帧默认 4MiB + 余量
FRAME_PAYLOAD_MAX = 8 * 1024 * 1024


def encode_frame(ftype: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(ftype, len(payload)) + payload


def try_parse_frame(buffer: bytes) -> Optional[tuple[int, bytes, bytes]]:
    """从缓冲区解析一个完整帧；不完整返回 None（等待更多字节）。

    返回 (type, payload, rest)。长度超限抛 ValueError（路由按 413 处理）。
    """
    if len(buffer) < _HEADER_SIZE:
        return None
    ftype, length = _HEADER.unpack_from(buffer, 0)
    if length > FRAME_PAYLOAD_MAX:
        raise ValueError(f"frame payload {length} exceeds {FRAME_PAYLOAD_MAX} limit")
    end = _HEADER_SIZE + length
    if len(buffer) < end:
        return None
    return ftype, buffer[_HEADER_SIZE:end], buffer[end:]
