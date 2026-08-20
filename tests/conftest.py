import os

import pytest

os.environ["DEBUG"] = "false"


@pytest.fixture(autouse=True)
def _inprocess_steer_queue():
    """让所有测试使用进程内 SteerQueue，避免依赖真实 Redis。"""
    import src.infra.task.steer as steer_module

    original = steer_module._steer_queue
    steer_module._steer_queue = steer_module.SteerQueue(redis=None)
    yield
    steer_module._steer_queue = original
