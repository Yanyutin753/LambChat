"""Check the capacity fixture's ownership, time range and long-body realism."""

from datetime import datetime, timezone

from scripts.benchmark_memory_six_months import memory


def test_capacity_records_keep_realistic_metadata_and_deterministic_dense_vectors():
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    long = memory(50, now, 1536)
    other = memory(50, now, 1536, owner="other-owner")
    short = memory(179, now, 1536)

    assert long["embedding"] == other["embedding"]
    assert len(long["embedding"]) == 1536
    assert all(value != 0 for value in long["embedding"])
    assert long["user_id"] != other["user_id"]
    assert long["memory_id"] != other["memory_id"]
    assert len(long["content"]) > 5000 and len(long["summary"]) <= 100
    assert (now - short["updated_at"]).days == 179
    assert long["scope"] == "project" and long["project_id"] == "project-0"


def test_capacity_runner_imports_without_unix_resource_module(monkeypatch):
    import runpy
    import sys
    from pathlib import Path

    monkeypatch.setitem(sys.modules, "resource", None)
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/benchmark_memory_six_months.py")
    )
    assert module["peak_rss"]() is None
