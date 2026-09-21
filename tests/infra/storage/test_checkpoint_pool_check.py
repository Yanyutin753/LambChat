"""PG checkpointer 连接池必须在 checkout 前做存活检查。

2026-09-21 生产实证：PG 容器重启（装 pg_stat_statements）后，连接池里的
死连接被惰性复用，4 个在途 run 以 "terminating connection due to
administrator command" 报错，持续约 10 分钟才随池自然换血。psycopg_pool
的 ``check=AsyncConnectionPool.check_connection`` 在每次借出连接前做一次
轻量 liveness round-trip（本机 ~0.1ms），可让 PG 重启/漂移对业务完全无感。
"""

from pathlib import Path

from src.infra.storage import checkpoint

SOURCE = Path(checkpoint.__file__).read_text(encoding="utf-8")


def test_pg_pool_checks_connection_before_checkout() -> None:
    assert "check=AsyncConnectionPool.check_connection" in SOURCE
