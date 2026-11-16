"""Capture private, bounded network evidence without changing host services or rules."""

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

COMMANDS = (
    ("iptables-save",),
    ("nft", "list", "ruleset"),
    ("ip", "route", "show", "table", "all"),
    ("ss", "-s"),
    ("sysctl", "net.netfilter.nf_conntrack_count", "net.netfilter.nf_conntrack_max"),
    ("docker", "ps", "--format", "{{.Names}} {{.Status}}"),
    ("docker", "events", "--since", "10m", "--until", "1s"),
    ("journalctl", "-k", "--since", "-5 min", "-n", "100", "--no-pager"),
    ("journalctl", "-u", "k3s", "--since", "-5 min", "-n", "100", "--no-pager"),
)


def probe(port: int) -> str | None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return None
    except OSError as error:
        return str(error)


def collect(output: Path) -> Path | None:
    failed = {str(port): error for port in (27017, 6379) if (error := probe(port))}
    if not failed:
        return None
    if output.is_symlink():
        raise ValueError("Evidence directory must not be a symlink")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    previous = sorted(output.glob("incident-*.json"), key=lambda path: path.stat().st_mtime)
    if previous and time.time() - previous[-1].stat().st_mtime < 60:
        return None
    report = {"captured_at": time.time(), "hostname": socket.gethostname(), "failed_probes": failed}
    try:
        report["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        report["boot_id"] = None
    commands = []
    for command in COMMANDS:
        entry = {"argv": command}
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, errors="replace", timeout=8, check=False
            )
            entry.update(
                returncode=result.returncode,
                stdout=result.stdout[:524288],
                stderr=result.stderr[:524288],
                truncated=len(result.stdout) > 524288 or len(result.stderr) > 524288,
            )
        except subprocess.TimeoutExpired:
            entry["error"] = "timeout"
        except OSError as error:
            entry["error"] = str(error)
        commands.append(entry)
    report["commands"] = commands
    # Publish only complete snapshots; retention never removes unrelated files.
    with tempfile.NamedTemporaryFile(
        mode="w", dir=output, prefix=".incident-", delete=False
    ) as file:
        temporary = Path(file.name)
        try:
            json.dump(report, file)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    destination = output / f"incident-{time.time_ns()}.json"
    temporary.replace(destination)
    for path in previous[: max(0, len(previous) - 19)]:
        path.unlink()
    return destination


if __name__ == "__main__":
    result = collect(Path("/var/lib/lambchat-incident-evidence"))
    if result:
        print(f"Network incident evidence saved: {result}")
