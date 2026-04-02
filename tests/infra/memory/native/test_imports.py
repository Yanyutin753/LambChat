import importlib
import os

os.environ["DEBUG"] = "false"


def test_native_backend_remains_importable_from_public_path():
    NativeMemoryBackend = importlib.import_module(
        "src.infra.memory.client.native"
    ).NativeMemoryBackend
    backend = NativeMemoryBackend()
    assert backend.name == "native"


def test_native_backend_is_importable_from_backend_module():
    BackendImpl = importlib.import_module(
        "src.infra.memory.client.native.backend"
    ).NativeMemoryBackend

    backend = BackendImpl()
    assert backend.name == "native"
