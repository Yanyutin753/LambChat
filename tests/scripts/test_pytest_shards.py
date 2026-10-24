import argparse
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_shards_cover_every_test_once_and_keep_file_fixtures_together():
    from scripts.pytest_shard import pytest_collection_modifyitems

    original = [
        SimpleNamespace(nodeid=f"tests/test_{file}.py::test_{case}")
        for file in range(40)
        for case in range(3)
    ]
    seen = []
    for index in range(1, 5):
        items = original.copy()
        config = SimpleNamespace(getoption=lambda _: (index, 4), hook=Mock())
        pytest_collection_modifyitems(config, items)
        assert items
        selected = [item.nodeid for item in items]
        seen.extend(selected)
        for file in {nodeid.split("::")[0] for nodeid in selected}:
            assert sum(nodeid.startswith(file + "::") for nodeid in selected) == 3
        deselected = config.hook.pytest_deselected.call_args.kwargs["items"]
        assert len(items) + len(deselected) == len(original)
        reversed_items = list(reversed(original))
        pytest_collection_modifyitems(config, reversed_items)
        assert [item.nodeid for item in reversed_items] == list(reversed(selected))
    assert sorted(seen) == sorted(item.nodeid for item in original)


def test_default_run_does_not_deselect_tests():
    from scripts.pytest_shard import pytest_collection_modifyitems

    items = [SimpleNamespace(nodeid="tests/test_one.py::test_one")]
    config = SimpleNamespace(getoption=lambda _: None, hook=Mock())
    pytest_collection_modifyitems(config, items)
    assert len(items) == 1
    config.hook.pytest_deselected.assert_not_called()


@pytest.mark.parametrize("value", ["0/4", "5/4", "1/0", "1/-1", "1", "x/4", "1/2/3"])
def test_invalid_shard_is_rejected(value):
    from scripts.pytest_shard import parse_shard

    with pytest.raises(argparse.ArgumentTypeError):
        parse_shard(value)


def test_valid_shard_is_one_based():
    from scripts.pytest_shard import parse_shard

    assert parse_shard("1/4") == (1, 4)
    assert parse_shard("4/4") == (4, 4)
