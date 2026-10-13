import os

import pytest

from scripts.run_validation import validation_slot

os.environ["DEBUG"] = "false"


def pytest_configure(config):
    if getattr(config.option, "numprocesses", None):
        raise pytest.UsageError("LambChat validation requires a single pytest worker")


def pytest_sessionstart(session):
    session.validation_slot = validation_slot()
    session.validation_slot.__enter__()


def pytest_sessionfinish(session, exitstatus):
    session.validation_slot.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def _inprocess_steer_queue():
    """让所有测试使用进程内 SteerQueue，避免依赖真实 Redis。"""
    import src.infra.task.steer as steer_module

    original = steer_module._steer_queue
    steer_module._steer_queue = steer_module.SteerQueue(redis=None)
    yield
    steer_module._steer_queue = original
