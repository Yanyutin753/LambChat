import importlib.util
import json
import subprocess
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
