"""同步哈希 helper（配合 run_blocking_io 在线程池执行）。"""

from __future__ import annotations

import hashlib


def sha256_hexdigest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
