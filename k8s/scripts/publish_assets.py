"""Retain build assets across releases on the current single-node deployment."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import uuid

CACHE_PATH = "/data/lambchat-k8s/static-assets"
ASSET_PATH = "/app/static/assets"
PYTHON = "/app/.venv/bin/python"

# Never extract tar paths directly, and publish each immutable file atomically.
_MERGE_SCRIPT = """
import os
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

root = Path(sys.argv[1])
if root.is_symlink() or not root.is_dir():
    raise ValueError('asset destination must be an existing directory')
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|*') as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or '\\\\' in member.name:
            raise ValueError('unsafe asset path: ' + member.name)
        if member.isdir():
            continue
        if not member.isfile() or not path.parts or path.suffix.lower() in {'.html', '.htm'}:
            raise ValueError('only regular build assets may be published: ' + member.name)
        parent = root
        for part in path.parts[:-1]:
            parent = parent / part
            if parent.is_symlink():
                raise ValueError('asset parent cannot be a symlink')
            parent.mkdir(exist_ok=True)
        destination = root.joinpath(*path.parts)
        if destination.is_symlink():
            raise ValueError('asset destination cannot be a symlink')
        data = archive.extractfile(member).read()
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != data:
                raise ValueError('immutable asset collision: ' + member.name)
            continue
        descriptor, temporary = tempfile.mkstemp(prefix='.asset-', dir=parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                os.fchmod(output.fileno(), 0o644)
                output.write(data)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != data:
                    raise ValueError('immutable asset collision: ' + member.name)
        finally:
            os.unlink(temporary)
"""


def _kubectl(namespace: str, *args: str, data: bytes | None = None) -> bytes:
    command = shlex.split(os.environ.get("KUBECTL", "kubectl"))
    return subprocess.run(
        [*command, "-n", namespace, *args],
        input=data,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout


def publish_assets(namespace: str, image: str, targets: list[tuple[str, str]]) -> str:
    """Merge old and new /assets into the retained cache before rolling APIs."""
    nodes = json.loads(_kubectl(namespace, "get", "nodes", "-o", "json"))["items"]
    if len(nodes) != 1:
        raise RuntimeError("Static asset hostPath publication requires a single-node cluster")
    node_name = nodes[0]["metadata"]["name"]
    mounted_targets = set()
    for pod_name, container_name in targets:
        pod = json.loads(_kubectl(namespace, "get", "pod", pod_name, "-o", "json"))
        if pod["spec"].get("nodeName") != node_name:
            raise RuntimeError("Static asset publication requires all targets on the single node")
        containers = [
            container
            for container in pod["spec"]["containers"]
            if container["name"] == container_name
        ]
        if len(containers) != 1:
            raise RuntimeError(f"Asset container not found in pod {pod_name}")
        volumes = {
            volume["name"]
            for volume in pod["spec"].get("volumes", [])
            if volume.get("hostPath", {}).get("path") == CACHE_PATH
        }
        if any(
            mount["name"] in volumes
            and mount.get("mountPath") == ASSET_PATH
            and mount.get("readOnly") is True
            and not mount.get("subPath")
            and not mount.get("subPathExpr")
            for mount in containers[0].get("volumeMounts", [])
        ):
            mounted_targets.add((pod_name, container_name))

    publisher = "lambchat-asset-publisher-" + uuid.uuid4().hex[:12]
    document = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": publisher, "namespace": namespace},
        "spec": {
            "nodeName": node_name,
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "publisher",
                    "image": image,
                    "command": ["/bin/sleep", "600"],
                    "securityContext": {"runAsUser": 0},
                    "volumeMounts": [{"name": "assets", "mountPath": "/cache"}],
                }
            ],
            "volumes": [
                {
                    "name": "assets",
                    "hostPath": {"path": CACHE_PATH, "type": "DirectoryOrCreate"},
                }
            ],
        },
    }
    try:
        _kubectl(namespace, "create", "-f", "-", data=json.dumps(document).encode())
        _kubectl(namespace, "wait", "--for=condition=Ready", f"pod/{publisher}", "--timeout=120s")
        for pod_name, container_name in [*targets, (publisher, "publisher")]:
            content = _kubectl(
                namespace,
                "exec",
                pod_name,
                "-c",
                container_name,
                "--",
                "tar",
                "-C",
                ASSET_PATH,
                "-cf",
                "-",
                ".",
            )
            _kubectl(
                namespace,
                "exec",
                "-i",
                publisher,
                "-c",
                "publisher",
                "--",
                PYTHON,
                "-c",
                _MERGE_SCRIPT,
                "/cache",
                data=content,
            )
        retained = _kubectl(
            namespace,
            "exec",
            publisher,
            "-c",
            "publisher",
            "--",
            "tar",
            "-C",
            "/cache",
            "-cf",
            "-",
            ".",
        )
        for pod_name, container_name in targets:
            if (pod_name, container_name) not in mounted_targets:
                _kubectl(
                    namespace,
                    "exec",
                    "-i",
                    pod_name,
                    "-c",
                    container_name,
                    "--",
                    PYTHON,
                    "-c",
                    _MERGE_SCRIPT,
                    ASSET_PATH,
                    data=retained,
                )
    finally:
        _kubectl(namespace, "delete", "pod", publisher, "--ignore-not-found=true", "--wait=false")
    return CACHE_PATH
