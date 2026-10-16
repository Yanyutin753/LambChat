import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location(
    "release_mutability", Path("scripts/check_release_mutability.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "code,body,error,allowed",
    [
        (0, {"assets": [{"name": "dev-latest.json"}]}, "", False),
        (0, {"assets": [{"name": "package.deb"}]}, "", True),
        (1, {}, "gh: Not Found (HTTP 404)", True),
        (1, {}, "gh: Forbidden (HTTP 403)", False),
    ],
)
def test_mutability_gate_rejects_published_tags_and_unverifiable_state(code, body, error, allowed):
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], code, json.dumps(body), error),
    ):
        if allowed:
            module.check_release_mutability("v2.15.2-dev.3", "owner/repo")
        else:
            with pytest.raises(RuntimeError, match="published|verify"):
                module.check_release_mutability("v2.15.2-dev.3", "owner/repo")


@pytest.mark.parametrize("actual", ["a" * 40, "b" * 40])
def test_release_source_must_match_requested_tag(actual):
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, json.dumps({"sha": actual}), ""),
    ):
        if actual == "a" * 40:
            module.check_release_source("v2.15.2-dev.3", "owner/repo", "a" * 40)
        else:
            with pytest.raises(RuntimeError, match="source"):
                module.check_release_source("v2.15.2-dev.3", "owner/repo", "a" * 40)


@pytest.mark.parametrize("gate", ["source", "mutability"])
def test_release_gates_decode_utf8_on_windows(gate):
    payload = json.dumps({"sha": "a" * 40, "assets": [], "body": "发布门禁"}, ensure_ascii=False)
    run = subprocess.run

    def github_response(_command, **kwargs):
        kwargs.setdefault("encoding", "cp1252")
        return run(
            [sys.executable, "-c", f"import sys; sys.stdout.buffer.write({payload.encode()!r})"],
            **kwargs,
        )

    with patch("subprocess.run", side_effect=github_response):
        if gate == "source":
            module.check_release_source("v2.15.2-dev.4", "owner/repo", "a" * 40)
        else:
            module.check_release_mutability("v2.15.2-dev.4", "owner/repo")
