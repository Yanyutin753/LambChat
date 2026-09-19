"""Kernel config 默认值断言的密闭环境。

进程内某些测试链路会把 `.env` 的值写进 `os.environ`（见
tests/infra/tool 的 document_parse 相关用例之后的环境残留）；
`Settings(_env_file=None)` 只关掉 dotenv、仍读真实环境变量，导致
默认值断言在特定用例顺序下被本地 `.env` 污染而闪挂。这里在本目录
所有测试前清掉全部已定义设置键，保证断言的是类定义默认值。
"""

from __future__ import annotations

import pytest

from src.kernel.config.definitions import SETTING_DEFINITIONS


@pytest.fixture(autouse=True)
def _hermetic_setting_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in SETTING_DEFINITIONS:
        monkeypatch.delenv(key, raising=False)
