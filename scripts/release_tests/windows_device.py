"""Windows-side installation and isolated interactive WebView lifecycle."""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def powershell(code):
    encoded = base64.b64encode(
        (
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
            + code
        ).encode("utf-16-le")
    ).decode()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded], capture_output=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-1500:])
    return result.stdout.decode("utf-8", "replace").strip()


def snapshot():
    roots = [Path(os.environ[name]) / "com.lambchat.app" for name in ["LOCALAPPDATA", "APPDATA"]]
    return {
        str(f): (f.stat().st_size, f.stat().st_mtime_ns)
        for root in roots
        if root.exists()
        for f in root.rglob("*")
        if f.is_file()
    }


def install(candidate):
    artifact = ROOT / candidate["asset_name"]
    if (
        artifact.stat().st_size != candidate["size"]
        or hashlib.file_digest(artifact.open("rb"), "sha256").hexdigest() != candidate["sha256"]
    ):
        raise ValueError("Transferred installer does not match signed candidate")
    installed = Path(os.environ["LOCALAPPDATA"]) / "LambChat"
    exe = installed / "LambChat.exe"
    literal = str(exe).replace("'", "''")
    # Do not interrupt a user's running application during unattended acceptance.
    powershell(
        "if(Get-Process LambChat -ErrorAction SilentlyContinue){throw 'LambChat is already running; close it before native acceptance'}"
    )
    before = snapshot()
    (ROOT / "data-before.json").write_text(json.dumps(before))
    states = {}
    for name in ["LOCALAPPDATA", "APPDATA"]:
        path = Path(os.environ[name]) / "com.lambchat.app/.window-state.json"
        states[str(path)] = (
            {
                "content": base64.b64encode(path.read_bytes()).decode(),
                "mtime": path.stat().st_mtime_ns,
                "atime": path.stat().st_atime_ns,
            }
            if path.exists()
            else None
        )
    (ROOT / "window-state-before.json").write_text(json.dumps(states))
    old = None
    if exe.exists():
        old = powershell(f"(Get-Item '{literal}').VersionInfo.ProductVersion")
        if tuple(map(int, old.split("."))) > tuple(map(int, candidate["core"].split("."))):
            raise ValueError("Refusing to downgrade installed application")
        shutil.copytree(installed, ROOT / "before-install")
    result = subprocess.run([str(artifact), "/S", "/D=" + str(installed)], timeout=240)
    if result.returncode:
        raise RuntimeError(f"Native installer failed: {result.returncode}")
    version = powershell(f"(Get-Item '{literal}').VersionInfo.ProductVersion")
    if version != candidate["core"]:
        raise ValueError("Installed application version mismatch")
    if hashlib.file_digest(exe.open("rb"), "sha256").hexdigest() != candidate["main_sha256"]:
        raise ValueError("Installed application differs from the verified NSIS payload")
    daemon = installed / "lambchat-daemon.exe"
    if hashlib.file_digest(daemon.open("rb"), "sha256").hexdigest() != candidate["daemon_sha256"]:
        raise ValueError("Installed daemon differs from signed release")
    actual = (
        subprocess.check_output([str(daemon), "version"], text=True, timeout=40)
        .strip()
        .splitlines()[-1]
    )
    if actual != candidate["core"] or snapshot() != before:
        raise ValueError("Daemon startup or existing application-data preservation failed")
    receipt = {
        "from": old,
        "tag": candidate["tag"],
        "sha": candidate["sha"],
        "core": version,
        "installer_exit": 0,
        "data_files_preserved": len(before),
        "daemon_verified": True,
        "main_exe_sha256": hashlib.file_digest(exe.open("rb"), "sha256").hexdigest(),
    }
    (ROOT / "install.json").write_text(json.dumps(receipt, indent=2))
    print("PASS real-device signed installer, installed daemon and existing data", flush=True)


def launch(candidate):
    profile = ROOT / "webview-profile"
    if profile.exists():
        raise ValueError("Native test profile already exists")
    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--remote-debugging-port=19325 --remote-debugging-address=127.0.0.1"
    )
    env["WEBVIEW2_USER_DATA_FOLDER"] = str(profile)
    env["LAMBCHAT_HOME"] = str(ROOT / "sandbox-home")
    exe = Path(os.environ["LOCALAPPDATA"]) / "LambChat/LambChat.exe"
    with (ROOT / "native-app.log").open("w") as log:
        child = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=subprocess.STDOUT)
        created = powershell(f"(Get-Process -Id {child.pid}).StartTime.ToUniversalTime().Ticks")
        (ROOT / "app-pid.json").write_text(
            json.dumps({"pid": child.pid, "executable": str(exe), "created": created})
        )
        child.wait()


def start():
    task = "LambChat-Native-" + ROOT.name
    path = str(ROOT / "windows_device.py").replace("'", "''")
    code = f"""
if(Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue){{throw 'Task already exists'}}
if(Get-NetTCPConnection -LocalPort 19325 -State Listen -ErrorAction SilentlyContinue){{throw 'Debug port already used'}}
$action=New-ScheduledTaskAction -Execute (Get-Command python.exe).Source -Argument '\"{path}\" launch'
$principal=New-ScheduledTaskPrincipal -UserId ($env:COMPUTERNAME+'\\'+$env:USERNAME) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName '{task}' -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName '{task}'
"""
    powershell(code)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:19325/json/version", timeout=2
            ) as response:
                browser = json.load(response)["Browser"]
            break
        except (OSError, ValueError):
            time.sleep(1)
    else:
        raise RuntimeError("Interactive native WebView did not start")
    root = str(ROOT).replace("'", "''")
    evidence = json.loads(
        powershell(f"""
$record=Get-Content '{root}\\app-pid.json'|ConvertFrom-Json
$app=Get-Process -Id $record.pid
$listener=Get-NetTCPConnection -LocalPort 19325 -State Listen
$command=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($listener.OwningProcess)\").CommandLine
$computer=Get-CimInstance Win32_ComputerSystem
@{{session=$app.SessionId;host_name=$env:COMPUTERNAME;model=$computer.Model;loopback=($listener.LocalAddress -eq '127.0.0.1');isolated_profile=$command.Contains('{root}\\webview-profile')}}|ConvertTo-Json -Compress
""")
    )
    if evidence["session"] < 1 or not evidence["loopback"] or not evidence["isolated_profile"]:
        raise ValueError("Native interactive session, loopback or profile isolation failed")
    if any(word in evidence["model"].lower() for word in ["virtual", "vmware", "kvm"]):
        raise ValueError("This acceptance requires the physical Windows host")
    evidence["browser"] = browser
    (ROOT / "environment.json").write_text(json.dumps(evidence, indent=2))
    print("PASS physical Windows interactive session and isolated loopback WebView", flush=True)


def cleanup():
    root = str(ROOT).replace("'", "''")
    task = "LambChat-Native-" + ROOT.name
    powershell(f"""
$root='{root}'
$recordPath=Join-Path $root 'app-pid.json'
if(Test-Path $recordPath){{
 $record=Get-Content $recordPath|ConvertFrom-Json
 $app=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
 if($app){{if($app.Path -ne $record.executable -or $app.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.created){{throw 'App PID identity mismatch'}};taskkill.exe /PID $record.pid /T /F|Out-Null;Start-Sleep -Seconds 2}}
}}
$listener=Get-NetTCPConnection -LocalPort 19325 -State Listen -ErrorAction SilentlyContinue
if($listener){{
 $command=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($listener.OwningProcess)\").CommandLine
 if($command.Contains($root+'\\webview-profile')){{taskkill.exe /PID $listener.OwningProcess /T /F|Out-Null;Start-Sleep -Seconds 2}}
 else{{throw 'Debug listener belongs to another process'}}
}}
if(Get-NetTCPConnection -LocalPort 19325 -State Listen -ErrorAction SilentlyContinue){{throw 'Debug listener still active'}}
$task=Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue
if($task){{if(-not $task.Actions.Arguments.Contains($root+'\\windows_device.py')){{throw 'Task identity mismatch'}};Unregister-ScheduledTask -TaskName '{task}' -Confirm:$false}}
$profile=Join-Path $root 'webview-profile'
if(Test-Path $profile){{Remove-Item -LiteralPath $profile -Recurse -Force}}
""")
    credential = ROOT / "sandbox-home/pat"
    if credential.exists():
        pat = json.loads(credential.read_text())
        origin = pat["origin"]
        if not origin.startswith("https://"):
            raise ValueError("Temporary pairing must belong to the HTTPS release server")
        config = json.loads((ROOT / "sandbox-home/sandbox.json").read_text())
        machine = config.get("machine_id")
        paths = (["/api/sandbox/machines/" + machine] if machine else []) + [
            "/api/auth/pat/current"
        ]
        for path in paths:
            request = urllib.request.Request(
                origin + path, method="DELETE", headers={"Authorization": "Bearer " + pat["token"]}
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    assert response.status == 200
            except urllib.error.HTTPError as exc:
                if exc.code != 404 or path.endswith("/current"):
                    raise RuntimeError("Temporary pairing cleanup failed") from None
    if (ROOT / "sandbox-home").exists():
        shutil.rmtree(ROOT / "sandbox-home")
    state = ROOT / "window-state-before.json"
    if state.exists():
        for path, saved in json.loads(state.read_text()).items():
            file = Path(path)
            if saved is None:
                file.unlink(missing_ok=True)
            else:
                file.write_bytes(base64.b64decode(saved["content"]))
                os.utime(file, ns=(saved["atime"], saved["mtime"]))
        before = json.loads((ROOT / "data-before.json").read_text())
        if {key: list(value) for key, value in snapshot().items()} != before:
            raise ValueError("Existing application data changed during native acceptance")
    print("PASS native task, listener and temporary login-profile cleanup", flush=True)
    if (ROOT / "accepted").exists():
        if (ROOT / "before-install").exists():
            shutil.rmtree(ROOT / "before-install")
        candidate = json.loads((ROOT / "candidate.json").read_text())
        (ROOT / candidate["asset_name"]).unlink(missing_ok=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "run":
        try:
            candidate = json.loads((ROOT / "candidate.json").read_text())
            install(candidate)
            start()
            print("READY native acceptance", flush=True)
            deadline = time.monotonic() + 600
            while not (ROOT / "finish").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("Native acceptance controller timed out")
                time.sleep(1)
        finally:
            cleanup()
    elif mode == "cleanup":
        cleanup()
    elif mode == "start":
        start()
    elif mode in {"install", "launch"}:
        candidate = json.loads((ROOT / "candidate.json").read_text())
        (install if mode == "install" else launch)(candidate)
    else:
        raise ValueError("Unknown Windows device operation")
