"""流式传输二进制帧编解码（daemon 侧）。

帧格式（HTTP body 与 Redis list item 同构，一个 item = 一个完整帧）::

    frame := type(1B) length(4B 大端) payload(length B)

    0x01 meta   JSON ``{"size": N}``（首帧，文件总字节数）
    0x02 data   裸文件字节（可重复）
    0x03 eof    length=0，正常收尾
    0x04 error  JSON ``{"error": "..."}``（终态，替代数据流）

选裸字节而非 base64+NDJSON：base64 让线上字节膨胀 33%（带宽受限链路上
直接慢 1/3），且两端每块一次 json/b64 编解码的 CPU 开销随文件线性放大。

与服务端 ``src/infra/sandbox/relay/_frames.py`` 字节级同则——两侧用同一组
torture 用例互锁（tests/client/test_frames.py），防漂移。
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

#: 单帧 payload 上限：data 帧默认 4MiB，留一倍余量给异常大的帧直接拒绝
FRAME_PAYLOAD_MAX = 8 * 1024 * 1024


def encode_frame(ftype: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(ftype, len(payload)) + payload


def try_parse_frame(buffer: bytes) -> Optional[tuple[int, bytes, bytes]]:
    """从缓冲区解析一个完整帧；不完整返回 None（等待更多字节）。

    返回 (type, payload, rest)。长度超限抛 ValueError（调用方按协议违规处理）。
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
