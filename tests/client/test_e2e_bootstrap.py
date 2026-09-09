from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_e2e_bootstrap_uses_configured_server_host_and_port() -> None:
    source = (ROOT / "scripts/e2e_local_sandbox.py").read_text(encoding="utf-8")

    assert "parsed = urlsplit(SERVER)" in source
    assert '"--host",\n                parsed.hostname' in source
    assert '"--port",\n                str(port)' in source
