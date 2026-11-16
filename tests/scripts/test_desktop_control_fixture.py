"""The native fixture must finish its real owner before checking terminal UI."""

import importlib.util
from pathlib import Path
from unittest.mock import patch


async def test_fixture_finishes_after_final_resume_without_starting_another_request(monkeypatch):
    source = Path(__file__).parents[2] / "scripts/release_tests/desktop-control-fixture.py"
    spec = importlib.util.spec_from_file_location("desktop_control_fixture", source)
    module = importlib.util.module_from_spec(spec)
    with patch("asyncio.run", side_effect=lambda coroutine: coroutine.close()):
        spec.loader.exec_module(module)

    class Control:
        paused = False
        requests = 0

        def __init__(self):
            self.bindings = []
            self.finishes = []

        async def bind(self, session, run, authority):
            self.bindings.append(run)
            return True

        async def execute(self, operation, observe):
            self.requests += 1
            self.paused = True
            return {"error": "desktop_control_paused"}

        async def finish(self, reason):
            self.finishes.append((self.requests, self.paused, reason))

    control = Control()

    async def resume_after_yield(_seconds):
        control.paused = False

    monkeypatch.setattr(module, "local_control", lambda: control)
    monkeypatch.setattr(module.asyncio, "sleep", resume_after_yield)
    await module.main()

    assert control.requests == 20
    assert control.bindings == ["run-0", "run-1", "run-2", "run-3"]
    assert control.finishes[-1] == (20, False, "completed")
