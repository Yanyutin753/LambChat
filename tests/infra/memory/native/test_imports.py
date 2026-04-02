import importlib
import os

os.environ["DEBUG"] = "false"


def test_native_backend_remains_importable_from_public_path():
    native_memory_backend_cls = importlib.import_module(
        "src.infra.memory.client.native"
    ).NativeMemoryBackend
    backend = native_memory_backend_cls()
    assert backend.name == "native"


def test_native_backend_is_importable_from_backend_module():
    backend_impl = importlib.import_module(
        "src.infra.memory.client.native.backend"
    ).NativeMemoryBackend

    backend = backend_impl()
    assert backend.name == "native"
