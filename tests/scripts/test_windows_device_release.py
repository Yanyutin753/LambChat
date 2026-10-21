"""Release acceptance must reject stale reports and untrusted candidate bytes."""

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/test_windows_device.py"


def load_runner():
    assert SCRIPT.exists(), "Persistent Windows release acceptance entry is missing"
    spec = importlib.util.spec_from_file_location("windows_device_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("tag", ["v2.15.3-dev.5", "v2.16.0", "v3.0.0-dev.12"])
def test_accepts_explicit_stable_and_dev_release_tags(tag):
    assert load_runner().release_core(tag) == tag[1:].split("-dev.")[0]


@pytest.mark.parametrize(
    "tag", ["latest", "main", "v2.15.3-dev.0", "v2.15.3-dev.999", "v2.15.3;id", "v2.15.3\n"]
)
def test_rejects_unpinned_or_unsafe_release_tags(tag):
    with pytest.raises(ValueError):
        load_runner().release_core(tag)


def test_candidate_size_and_digest_must_both_match(tmp_path):
    runner = load_runner()
    candidate = tmp_path / "setup.exe"
    candidate.write_bytes(b"signed candidate")
    asset = {"size": 16, "sha256": hashlib.sha256(b"signed candidate").hexdigest()}
    runner.check_asset(candidate, asset)
    candidate.write_bytes(b"changed bytes!!!")
    with pytest.raises(ValueError):
        runner.check_asset(candidate, asset)
    candidate.write_bytes(b"signed candidate\n")
    with pytest.raises(ValueError):
        runner.check_asset(candidate, asset)


def good_report():
    return {
        "tag": "v2.15.3-dev.5",
        "sha": "a" * 40,
        "run_id": "run-current",
        "environment": {
            "tauri": True,
            "priorToken": False,
            "origin": "http://tauri.localhost",
            "userAgent": "Edg/155.0",
        },
        "cases": [
            {
                "case": "real-native-direct",
                "passed": True,
                "galleryProxies": 0,
                "viewerProxies": 0,
                "privateAuthenticatedBlob": True,
                "credentialLeaks": 0,
                "pageErrors": 0,
            },
            {
                "case": "real-native-storage-failure",
                "passed": True,
                "galleryProxies": 1,
                "viewerProxies": 1,
                "privateAuthenticatedBlob": True,
                "credentialLeaks": 0,
                "pageErrors": 0,
            },
            *[
                {
                    "case": "real-native-route" + route,
                    "passed": True,
                    "missingChunks": 0,
                    "pageErrors": 0,
                }
                for route in ["/settings", "/files", "/chat"]
            ],
        ],
    }


def test_accepts_complete_current_native_report():
    load_runner().check_report(good_report(), "v2.15.3-dev.5", "a" * 40, "run-current")


@pytest.mark.parametrize(
    "mutation",
    [
        "tag",
        "sha",
        "run",
        "missing",
        "duplicate",
        "false",
        "numeric_true",
        "proxy",
        "auth",
        "leak",
        "origin",
        "browser",
        "existing_login",
        "chunk",
        "boolean_count",
        "float_count",
    ],
)
def test_incomplete_or_stale_native_evidence_fails_closed(mutation):
    report = copy.deepcopy(good_report())
    if mutation in {"tag", "sha"}:
        report[mutation] = "old"
    elif mutation == "run":
        report["run_id"] = "previous"
    elif mutation == "missing":
        report["cases"].pop()
    elif mutation == "duplicate":
        report["cases"][-1] = report["cases"][-2]
    elif mutation in {"false", "numeric_true"}:
        report["cases"][0]["passed"] = False if mutation == "false" else 1
    elif mutation == "proxy":
        report["cases"][0]["galleryProxies"] = 1
    elif mutation == "auth":
        report["cases"][0]["privateAuthenticatedBlob"] = False
    elif mutation == "leak":
        report["cases"][1]["credentialLeaks"] = 1
    elif mutation == "origin":
        report["environment"]["origin"] = "https://lambchat.com"
    elif mutation == "browser":
        report["environment"]["tauri"] = False
    elif mutation == "existing_login":
        report["environment"]["priorToken"] = True
    elif mutation == "chunk":
        report["cases"][-1]["missingChunks"] = 1
    elif mutation == "boolean_count":
        report["cases"][0]["pageErrors"] = False
    elif mutation == "float_count":
        report["cases"][0]["galleryProxies"] = 0.0
    with pytest.raises(ValueError):
        load_runner().check_report(report, "v2.15.3-dev.5", "a" * 40, "run-current")


def test_missing_windows_configuration_fails_instead_of_skipping(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMBCHAT_RELEASE_TEST_CONFIG", str(tmp_path / "absent.json"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "v2.15.3-dev.5"])
    with pytest.raises(SystemExit) as exc:
        load_runner().options()
    assert exc.value.code == 2


def test_automated_release_checks_do_not_require_windows_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMBCHAT_RELEASE_TEST_CONFIG", str(tmp_path / "absent.json"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "v2.15.3-dev.5"])
    assert load_runner().options(require_windows=False).server_ssh == "yang"


@pytest.mark.parametrize("count,bad", [(0, None), (38, None), (39, False), (39, 1)])
def test_partial_failed_or_uncertified_automated_results_are_not_passes(count, bad):
    rows = [{"test": str(i), "ok": True} for i in range(count)]
    if rows and bad is not None:
        rows[-1]["ok"] = bad
    with pytest.raises(ValueError):
        load_runner().check_production_report(rows)


def test_complete_automated_results_pass_without_native_evidence():
    assert load_runner().check_production_report(complete_production_report()) == 39


def complete_production_report():
    names = [
        "T1-load",
        "T2-auth",
        "T3-session",
        "T4-queue",
        "T5-sse",
        "T6-history",
        "T8-websocket",
        "T9-upload",
        "T11-isolation",
        "T13-health",
        "R1-cancel",
        "R2-steer",
        "R3-replay",
        "R4-models",
        "R5-notifications",
        "R6-files",
        "R7a-schedule-create",
        "R7b-schedule-execute",
        "W1-errors",
        "W3-websockets",
        "W4-sharing",
        "W5-skills",
        "W7-resources",
        "N1-complete",
        "N1: body present",
        "N2-steer",
        "N2: body present",
        *[f"I{i}-image" for i in range(1, 13)],
    ]
    return [{"test": name, "ok": True} for name in names]


@pytest.mark.parametrize("mutation", ["duplicate", "anonymous", "missing_image", "missing_api"])
def test_production_report_cannot_fill_required_coverage_with_other_successes(mutation):
    rows = complete_production_report()
    if mutation == "duplicate":
        rows[-1] = rows[-2].copy()
    elif mutation == "anonymous":
        rows[-1].pop("test")
    elif mutation == "missing_image":
        rows[-1]["test"] = "I13-unrelated"
    else:
        rows[0]["test"] = "T14-unrelated"
    with pytest.raises(ValueError):
        load_runner().check_production_report(rows)


def test_default_release_entry_never_invokes_native_hardware(tmp_path, monkeypatch):
    runner = load_runner()

    def native_forbidden(**_kwargs):
        raise AssertionError("Default release checks must not start native hardware tests")

    monkeypatch.setattr(runner, "main", native_forbidden)
    monkeypatch.setitem(sys.modules, "test_windows_device", runner)
    path = SCRIPT.with_name("run_release_regression.py")
    spec = importlib.util.spec_from_file_location("automated_release_entry", path)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)

    def options(**kwargs):
        assert kwargs == {"require_windows": False}
        return SimpleNamespace(
            tag="v2.15.3-dev.5", server_ssh="production", output=tmp_path / "report"
        )

    calls = []

    def ssh(host, args):
        assert host == "production"
        calls.append(args)
        if "-c" in args:
            return hashlib.sha256(
                (runner.REPO / "scripts/run_validation.py").read_bytes()
            ).hexdigest()
        return ""

    monkeypatch.setattr(entry, "options", options)
    monkeypatch.setattr(entry, "ssh", ssh)
    monkeypatch.setattr(entry, "copy_to", lambda *_args: None)
    monkeypatch.setattr(entry, "production_suite", lambda *_args: {"passed": True, "cases": 39})
    entry.main()
    import json

    report = json.loads((tmp_path / "report/report.json").read_text())
    assert report["passed"] is True
    assert report["scope"] == "automated production regression"
    assert "optional" in report["native_tests"]
    assert len(calls) == 2
