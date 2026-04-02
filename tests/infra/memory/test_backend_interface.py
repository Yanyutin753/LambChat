import inspect

from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.hindsight import HindsightBackend
from src.infra.memory.client.memu import MemuBackend
from src.infra.memory.client.native.backend import NativeMemoryBackend


def _signature_shape(method: object) -> list[tuple[str, inspect._ParameterKind, bool]]:
    return [
        (parameter.name, parameter.kind, parameter.default is inspect.Signature.empty)
        for parameter in inspect.signature(method).parameters.values()
    ]


def test_memory_backends_retain_signature_matches_base_contract():
    expected = _signature_shape(MemoryBackend.retain)

    for backend in (MemuBackend, HindsightBackend, NativeMemoryBackend):
        assert _signature_shape(backend.retain) == expected
