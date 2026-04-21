from pathlib import Path


def test_dev_target_runs_backend_inside_uv_environment() -> None:
    makefile = Path("Makefile").read_text()
    dev_target = makefile.split("\ndev:\n", maxsplit=1)[1].split("\nfrontend-dev:", maxsplit=1)[0]

    assert "uv run python main.py" in dev_target
