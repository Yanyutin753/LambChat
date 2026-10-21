"""Physical Windows release acceptance; invoke through run_validation.py."""

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPERS = REPO / "scripts/release_tests"
GITHUB = "Yanyutin753/LambChat"


def release_core(tag):
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-dev\.([1-9]\d{0,2}))?", tag)
    if not match or (match[2] and int(match[2]) > 998):
        raise ValueError("An explicit stable or dev release tag is required")
    return match[1]


def check_asset(path, asset):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if path.stat().st_size != asset["size"] or digest != asset["sha256"]:
        raise ValueError("Release asset size/SHA256 mismatch")


def check_report(report, tag, sha, run_id):
    if (report.get("tag"), report.get("sha"), report.get("run_id")) != (tag, sha, run_id):
        raise ValueError("Native evidence belongs to another release or run")
    env = report.get("environment", {})
    if (
        env.get("tauri") is not True
        or env.get("priorToken") is not False
        or env.get("origin") != "http://tauri.localhost"
        or "Edg/" not in env.get("userAgent", "")
    ):
        raise ValueError("Evidence must come from the isolated native Windows WebView")
    expected = {
        "real-native-direct",
        "real-native-storage-failure",
        *["real-native-route" + path for path in ["/chat", "/settings", "/files"]],
    }
    cases = report.get("cases", [])
    if len(cases) != 5 or {c.get("case") for c in cases} != expected:
        raise ValueError("Native evidence is incomplete or duplicated")
    for case in cases:
        counters = (
            ["pageErrors", "missingChunks"]
            if case["case"].startswith("real-native-route")
            else ["pageErrors", "galleryProxies", "viewerProxies", "credentialLeaks"]
        )
        if any(type(case.get(field)) is not int for field in counters):
            raise ValueError("Native result counters must be integers")
        if case.get("passed") is not True or case.get("pageErrors") != 0:
            raise ValueError("Native case failed")
        if case["case"].startswith("real-native-route"):
            if case.get("missingChunks") != 0:
                raise ValueError("Packaged frontend chunks are missing")
        else:
            proxies = 0 if case["case"] == "real-native-direct" else 1
            if (
                case.get("galleryProxies") != proxies
                or case.get("viewerProxies") != proxies
                or case.get("privateAuthenticatedBlob") is not True
                or case.get("credentialLeaks") != 0
            ):
                raise ValueError("Native direct/fallback/private-image checks failed")


def run(args, *, log=None, input=None, timeout=300):
    if log:
        with log.open("w") as stream:
            subprocess.run(
                args,
                input=input,
                text=True,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=True,
            )
        return ""
    return subprocess.check_output(
        args, input=input, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def ssh(host, args, **kwargs):
    return run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, shlex.join(args)], **kwargs
    )


def windows_ps(host, source):
    prefix = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
    encoded = base64.b64encode((prefix + source).encode("utf-16-le")).decode()
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            "powershell",
            "-NoProfile",
            "-EncodedCommand",
            encoded,
        ],
        timeout=60,
    ).strip()


def copy_to(host, files, destination):
    run(["scp", "-q", *map(str, files), host + ":" + destination + "/"], timeout=180)


def copy_from(host, source, destination):
    run(["scp", "-q", host + ":" + source, str(destination)], timeout=40)


def options(*, require_windows=True):
    config_path = Path(
        os.environ.get(
            "LAMBCHAT_RELEASE_TEST_CONFIG", Path.home() / ".config/lambchat/release-tests.json"
        )
    )
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    parser = argparse.ArgumentParser(
        description=__doc__
        if require_windows
        else "Automated production release regression; native checks are optional"
    )
    parser.add_argument("tag")
    parser.add_argument("--windows-ssh", default=config.get("windows_ssh"))
    parser.add_argument("--server-ssh", default=config.get("server_ssh", "yang"))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--sevenzip", default=config.get("sevenzip") or shutil.which("7zz") or shutil.which("7z")
    )
    args = parser.parse_args()
    release_core(args.tag)
    for host in [args.windows_ssh, args.server_ssh] if require_windows else [args.server_ssh]:
        if not host or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", host):
            parser.error("Configure windows_ssh/server_ssh as SSH aliases or user@host")
    return args


def check_production_report(rows):
    if len(rows) < 39 or any(row.get("ok") is not True for row in rows):
        raise ValueError("Production regression failed or returned incomplete evidence")
    required = (
        {f"T{n}-" for n in [1, 2, 3, 4, 5, 6, 8, 9, 11, 13]}
        | {f"R{n}-" for n in [1, 2, 3, 4, 5, 6, "7a", "7b"]}
        | {f"W{n}-" for n in [1, 3, 4, 5, 7]}
        | {"N1-", "N1:", "N2-", "N2:"}
        | {f"I{n}-" for n in range(1, 13)}
    )
    identifiers = []
    for row in rows:
        name = row.get("test")
        match = re.match(r"[TRWNI]\d+[a-z]?[-:]", name) if isinstance(name, str) else None
        if not match:
            raise ValueError("Production regression case has no stable identifier")
        identifiers.append(match[0])
    if len(set(identifiers)) != len(identifiers) or not required.issubset(identifiers):
        raise ValueError("Production regression has duplicate or missing required cases")
    return len(rows)


def production_suite(host, root, remote_root):
    capture = (
        "import subprocess,shutil;result=subprocess.run(['bash','/root/disttest/run-all.sh']);shutil.copyfile('/root/disttest-results.json',"
        + repr(remote_root + "/production-results.jsonl")
        + ");raise SystemExit(result.returncode)"
    )
    ssh(
        host,
        ["python3", remote_root + "/run_validation.py", "python3", "-c", capture],
        log=root / "production-regression.log",
        timeout=900,
    )
    copy_from(host, remote_root + "/production-results.jsonl", root / "production-results.jsonl")
    rows = [
        json.loads(line)
        for line in (root / "production-results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return {"passed": True, "cases": check_production_report(rows)}


def main(*, server_suite=False):
    args = options()
    core = release_core(args.tag)
    run_id = uuid.uuid4().hex
    root = args.output or Path.home() / ".cache/lambchat/release-tests" / args.tag / run_id
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(root, 0o700)
    report = {
        "tag": args.tag,
        "run_id": run_id,
        "passed": False,
        "mac_gui": "not run; optional",
    }
    win_root = server_root = None
    tunnel = None
    controller = None
    controller_log = None
    error = None
    cleanup_errors = []
    python = None

    def interrupted(_signum, _frame):
        raise KeyboardInterrupt("Release acceptance interrupted")

    prior_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        bundled = (
            Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
        )
        node = str(bundled) if bundled.is_file() else shutil.which("node")
        if not node or not Path(node).is_file():
            raise RuntimeError("Node.js is required for existing Playwright CDP checks")
        if not args.sevenzip or not Path(args.sevenzip).is_file():
            raise RuntimeError(
                "Configure sevenzip with the official 7zz/7z executable for NSIS payload verification"
            )
        release = json.loads(run(["gh", "api", f"repos/{GITHUB}/releases/tags/{args.tag}"]))
        if release["draft"]:
            raise ValueError("Release assets are not published")
        sha = json.loads(run(["gh", "api", f"repos/{GITHUB}/commits/{args.tag}"]))["sha"]
        asset_name = f"LambChat-{args.tag}-Windows-x64-setup.exe"
        print(f"Preparing exact signed release {args.tag} ({sha[:12]})", flush=True)
        run(
            [
                "gh",
                "release",
                "download",
                args.tag,
                "--repo",
                GITHUB,
                "--dir",
                str(root),
                "-p",
                "release-security.json",
                "-p",
                "release-security.json.sig",
                "-p",
                asset_name,
            ]
        )
        payload = (root / "release-security.json").read_bytes()
        signature = (root / "release-security.json.sig").read_bytes()
        sys.path.insert(0, str(REPO / "client"))
        from lambchat_sandbox.release_signature import verify_release

        verify_release(
            payload, signature, version=core, asset_name=asset_name, current_version="0.0.0"
        )
        manifest = json.loads(payload)
        if manifest["commit"] != sha:
            raise ValueError("Signed source does not match release tag")
        asset = manifest["assets"][asset_name]
        check_asset(root / asset_name, asset)
        run(
            [
                args.sevenzip,
                "x",
                str(root / asset_name),
                "-o" + str(root / "expected"),
                "lambchat.exe",
                "-r",
                "-y",
            ],
            log=root / "nsis-extraction.log",
        )
        executables = [
            p
            for p in (root / "expected").rglob("*")
            if p.is_file() and p.name.lower() == "lambchat.exe"
        ]
        if len(executables) != 1:
            raise ValueError(
                "Expected exactly one main executable inside the verified NSIS installer"
            )
        with executables[0].open("rb") as stream:
            main_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        report["sha"] = sha
        candidate = {
            "tag": args.tag,
            "core": core,
            "sha": sha,
            "run_id": run_id,
            "asset_name": asset_name,
            **asset,
            "main_sha256": main_sha256,
            "daemon_sha256": manifest["assets"]["lambchat-daemon-x86_64-pc-windows-msvc.exe"][
                "sha256"
            ],
        }
        (root / "candidate.json").write_text(json.dumps(candidate))
        # Check connectivity before replaying the paid production regression suite.
        windows_ps(args.windows_ssh, "Write-Output $env:COMPUTERNAME")
        server_root = "/root/disttest/native-release-" + run_id
        ssh(args.server_ssh, ["mkdir", "-m", "700", server_root])
        server_files = [
            HELPERS / "native_fixture.py",
            HELPERS / "image_loading.py",
            REPO / "scripts/run_validation.py",
        ]
        copy_to(args.server_ssh, server_files, server_root)
        transferred = json.loads(
            ssh(
                args.server_ssh,
                [
                    "python3",
                    "-c",
                    "import hashlib,json,pathlib;print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in pathlib.Path("
                    + repr(server_root)
                    + ").iterdir() if f.is_file()}))",
                ],
            )
        )
        for file in server_files:
            assert transferred[file.name] == hashlib.sha256(file.read_bytes()).hexdigest(), (
                "Transferred server source changed"
            )
        if server_suite:
            print("Running existing production deployment regression", flush=True)
            report["production_suite"] = production_suite(args.server_ssh, root, server_root)
        remote = json.loads(
            windows_ps(
                args.windows_ssh,
                "$p=Join-Path $env:TEMP 'lambchat-release-"
                + run_id
                + "';New-Item -ItemType Directory -Path $p|Out-Null;@{path=$p;python=(Get-Command python.exe).Source}|ConvertTo-Json -Compress",
            )
        )
        win_root, python = remote["path"], remote["python"]
        win_files = [
            root / asset_name,
            root / "candidate.json",
            HELPERS / "windows_device.py",
            REPO / "scripts/run_validation.py",
        ]
        copy_to(args.windows_ssh, win_files, win_root.replace("\\", "/"))
        transferred = json.loads(
            windows_ps(
                args.windows_ssh,
                "$r=@{};Get-ChildItem '"
                + win_root.replace("'", "''")
                + "' -File|ForEach-Object {$r[$_.Name]=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()};$r|ConvertTo-Json -Compress",
            )
        )
        for file in win_files:
            with file.open("rb") as stream:
                assert (
                    transferred[file.name] == hashlib.file_digest(stream, "sha256").hexdigest()
                ), "Transferred Windows source or asset changed"

        command = subprocess.list2cmdline(
            [
                python,
                "-u",
                win_root + "\\run_validation.py",
                python,
                "-u",
                win_root + "\\windows_device.py",
                "run",
            ]
        )
        controller_log = (root / "windows-device.log").open("w")
        controller = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", args.windows_ssh, command],
            stdout=controller_log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 300
        while "READY native acceptance" not in (root / "windows-device.log").read_text():
            if controller.poll() is not None:
                raise RuntimeError("Windows controller failed; inspect windows-device.log")
            if time.monotonic() > deadline:
                raise TimeoutError("Windows installation or interactive startup timed out")
            time.sleep(1)
        print(
            "PASS physical Windows installation, data preservation and isolated WebView startup",
            flush=True,
        )
        copy_from(
            args.windows_ssh,
            win_root.replace("\\", "/") + "/environment.json",
            root / "device.json",
        )
        copy_from(
            args.windows_ssh, win_root.replace("\\", "/") + "/install.json", root / "install.json"
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        tunnel = subprocess.Popen(
            [
                "ssh",
                "-N",
                "-o",
                "BatchMode=yes",
                "-o",
                "ControlPath=none",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=15",
                "-L",
                f"127.0.0.1:{port}:127.0.0.1:19325",
                args.windows_ssh,
            ],
            stdout=subprocess.DEVNULL,
            stderr=(root / "tunnel.log").open("w"),
        )
        for _ in range(20):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            if tunnel.poll() is not None:
                raise RuntimeError("SSH WebView tunnel failed")
            time.sleep(0.2)
        else:
            raise RuntimeError("SSH WebView tunnel did not become ready")
        ssh(
            args.server_ssh,
            [
                "python3",
                server_root + "/run_validation.py",
                "python3",
                "-u",
                server_root + "/native_fixture.py",
                "prepare",
            ],
            log=root / "fixture-prepare.log",
            timeout=240,
        )
        copy_from(args.server_ssh, server_root + "/metadata.json", root / "metadata.json")
        (root / "metadata.json").chmod(0o600)
        env = os.environ.copy()
        bundled_modules = Path(node).parent.parent / "node_modules"
        if bundled_modules.exists():
            env["NODE_PATH"] = str(bundled_modules) + (
                os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else ""
            )
        subprocess.run(
            [node, str(HELPERS / "windows-webview.mjs"), str(root), f"http://127.0.0.1:{port}"],
            env=env,
            check=True,
            timeout=360,
        )
        native = json.loads((root / "native.json").read_text())
        check_report(native, args.tag, sha, run_id)
        report["native"] = native
        report["device"] = json.loads((root / "device.json").read_text())
        report["installation"] = json.loads((root / "install.json").read_text())
        report["passed"] = True
    except BaseException as exc:
        error = exc
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait(timeout=5)
        if win_root:
            try:
                if controller and controller.poll() is None:
                    if report["passed"]:
                        windows_ps(
                            args.windows_ssh,
                            "New-Item -ItemType File -Path '"
                            + win_root.replace("'", "''")
                            + "\\accepted'|Out-Null",
                        )
                    windows_ps(
                        args.windows_ssh,
                        "New-Item -ItemType File -Path '"
                        + win_root.replace("'", "''")
                        + "\\finish'|Out-Null",
                    )
                    controller.wait(timeout=90)
                if controller and controller.returncode != 0:
                    raise RuntimeError(
                        "Windows controller or cleanup failed; inspect windows-device.log"
                    )
            except Exception as exc:
                cleanup_errors.append("Windows cleanup: " + str(exc))
        if controller_log:
            controller_log.close()
        if server_root:
            try:
                ssh(
                    args.server_ssh,
                    [
                        "python3",
                        server_root + "/run_validation.py",
                        "python3",
                        "-u",
                        server_root + "/native_fixture.py",
                        "cleanup",
                    ],
                    log=root / "fixture-cleanup.log",
                    timeout=90,
                )
            except Exception as exc:
                cleanup_errors.append("Fixture cleanup: " + str(exc))
        (root / "metadata.json").unlink(missing_ok=True)
        report["cleanup_errors"] = cleanup_errors
        report["passed"] = report["passed"] and not cleanup_errors
        (root / "report.json").write_text(json.dumps(report, indent=2))
        signal.signal(signal.SIGTERM, prior_sigterm)
    print(f"Report: {root / 'report.json'}", flush=True)
    if error or cleanup_errors:
        print("FAIL release acceptance; inspect the private report/logs", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"PASS {args.tag}: physical Windows 5/5; Mac native checks are optional",
        flush=True,
    )


if __name__ == "__main__":
    main()
