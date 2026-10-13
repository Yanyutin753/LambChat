"""Exercise the daemon's real shell wrapper without starting a daemon build."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name == "nt", reason="Portable Bash caller regression; CI proves Windows")
def test_daemon_wrapper_keeps_selected_bash_with_spaces_in_path(tmp_path):
    bash = shutil.which("bash")
    assert bash is not None
    selected_directory = tmp_path / "selected shell with spaces"
    selected_directory.mkdir()
    selected_bash = selected_directory / "bash"
    selected_bash.symlink_to(bash)
    poison_directory = tmp_path / "poison-bin"
    poison_directory.mkdir()
    poison_bash = poison_directory / "bash"
    poison_bash.write_text("#!/bin/sh\nprintf 'wrong PATH interpreter' >&2\nexit 86\n")
    poison_bash.chmod(0o755)

    arguments_file = tmp_path / "wrapper-arguments.json"
    python_stub = poison_directory / "python3"
    python_stub.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, subprocess, sys\n"
        f"pathlib.Path({str(arguments_file)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        # Replace only the build body with a harmless interpreter probe. Preserve
        # the exact executable selected by the real build script's wrapper.
        "raise SystemExit(subprocess.run([sys.argv[2], '-c', "
        "\"printf 'selected-interpreter'\"]).returncode)\n"
    )
    python_stub.chmod(0o755)
    env = {**os.environ, "PATH": str(poison_directory) + os.pathsep + os.environ["PATH"]}
    env.pop("LAMBCHAT_DAEMON_BUILD_WRAPPED", None)
    script = ROOT / "client/scripts/build-daemon.sh"
    result = subprocess.run(
        [str(selected_bash), str(script), "literal argument"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "selected-interpreter"
    assert json.loads(arguments_file.read_text()) == [
        str(ROOT / "scripts/run_validation.py"),
        str(selected_bash),
        str(script),
        "literal argument",
    ]
