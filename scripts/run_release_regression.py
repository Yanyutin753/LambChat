"""Default release acceptance is automated; native hardware checks are optional."""

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

from test_windows_device import REPO, copy_to, options, production_suite, ssh


def main():
    args = options(require_windows=False)
    run_id = uuid.uuid4().hex
    root = args.output or Path.home() / ".cache/lambchat/release-tests" / args.tag / run_id
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(root, 0o700)
    remote = "/root/disttest/automated-release-" + run_id
    report = {
        "tag": args.tag,
        "run_id": run_id,
        "scope": "automated production regression",
        "passed": False,
        "native_tests": "not requested; optional and not a release gate",
    }
    try:
        ssh(args.server_ssh, ["mkdir", "-m", "700", remote])
        wrapper = REPO / "scripts/run_validation.py"
        copy_to(args.server_ssh, [wrapper], remote)
        digest = ssh(
            args.server_ssh,
            [
                "python3",
                "-c",
                "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path("
                + repr(remote + "/run_validation.py")
                + ").read_bytes()).hexdigest())",
            ],
        ).strip()
        if digest != hashlib.sha256(wrapper.read_bytes()).hexdigest():
            raise ValueError("Transferred validation wrapper changed")
        report["production_suite"] = production_suite(args.server_ssh, root, remote)
        report["passed"] = True
    except subprocess.CalledProcessError as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if error.returncode == 75:
            report["blocked"] = True
            raise SystemExit(75) from None
        raise
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Report: {root / 'report.json'}", flush=True)
    print(
        f"PASS automated release regression: {report['production_suite']['cases']} cases; native tests optional",
        flush=True,
    )


if __name__ == "__main__":
    main()
