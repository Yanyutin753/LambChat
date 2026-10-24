"""Split CI across runners by file, preserving module/class fixture boundaries."""

import argparse
import hashlib


def parse_shard(value):
    try:
        index, count = map(int, value.split("/"))
        if 1 <= index <= count:
            return index, count
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("shard must be INDEX/COUNT with 1 <= INDEX <= COUNT")


def pytest_addoption(parser):
    parser.addoption("--shard", type=parse_shard, help="Run file shard INDEX/COUNT")


def pytest_collection_modifyitems(config, items):
    shard = config.getoption("shard")
    if shard is None:
        return
    index, count = shard
    selected, deselected = [], []
    for item in items:
        file = item.nodeid.split("::", 1)[0]
        bucket = int.from_bytes(hashlib.sha256(file.encode()).digest(), "big") % count
        (selected if bucket == index - 1 else deselected).append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
