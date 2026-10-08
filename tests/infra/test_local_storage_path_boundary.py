from types import SimpleNamespace

import pytest

from src.infra.storage.s3.backends.local import LocalStorageBackend


def test_storage_rejects_sibling_with_matching_directory_prefix(tmp_path):
    backend = LocalStorageBackend(SimpleNamespace(storage_path=str(tmp_path / "uploads")))
    with pytest.raises(ValueError, match="path traversal"):
        backend._get_file_path("../uploads-private/secret.txt")
    assert backend._get_file_path("image/a.png") == tmp_path / "uploads/image/a.png"
