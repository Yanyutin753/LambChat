from __future__ import annotations

from types import SimpleNamespace

from src.infra.local_filesystem import ensure_local_filesystem_dirs


def test_ensure_local_filesystem_dirs_creates_dirs_for_local_storage(tmp_path) -> None:
    settings = SimpleNamespace(
        LOCAL_STORAGE_PATH=str(tmp_path / "uploads"),
        S3_ENABLED=False,
        S3_PROVIDER="local",
    )

    ensure_local_filesystem_dirs(settings)

    assert (tmp_path / "uploads").is_dir()
    assert (tmp_path / "uploads" / "revealed_files").is_dir()
    assert (tmp_path / "uploads" / "revealed_projects").is_dir()


def test_ensure_local_filesystem_dirs_skips_when_object_storage_is_enabled(tmp_path) -> None:
    settings = SimpleNamespace(
        LOCAL_STORAGE_PATH=str(tmp_path / "uploads"),
        S3_ENABLED=True,
        S3_PROVIDER="minio",
    )

    ensure_local_filesystem_dirs(settings)

    assert not (tmp_path / "uploads").exists()
