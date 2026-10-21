#!/usr/bin/env python3
"""Roll a checked image through the existing host-network API slots and worker."""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from publish_assets import publish_assets

_MISSING = object()
_CONTAINER = "/spec/template/spec/containers/0"


def kubectl(namespace, *args, payload=None):
    result = subprocess.run(
        [*shlex.split(os.environ.get("KUBECTL", "kubectl")), "-n", namespace, *args],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # kubectl errors can echo submitted spec/env values; keep them off public logs.
        raise RuntimeError(f"kubectl {' '.join(args[:3])} failed (exit={result.returncode})")
    return json.loads(result.stdout) if args[0] == "get" else result.stdout


@contextmanager
def deployment_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("deployment lock is busy") from error
        yield


def _value(document, path):
    current = document
    for key in path.strip("/").split("/"):
        if isinstance(current, list):
            current = current[int(key)]
        elif key in current:
            current = current[key]
        else:
            return _MISSING
    return current


def inverse_patch(document, patch, current=None):
    inverse = []
    for operation in reversed(patch):
        value = _value(document, operation["path"])
        if current is not None and _value(current, operation["path"]) == value:
            continue
        inverse.append(
            {"op": "remove", "path": operation["path"]}
            if value is _MISSING
            else {"op": "add", "path": operation["path"], "value": copy.deepcopy(value)}
        )
    return inverse


def _patch(values):
    return [{"op": "add", "path": path, "value": value} for path, value in values.items()]


def _probe(probe):
    # Match API defaults so exact ownership checks do not mistake them for external edits.
    for field, default in (
        ("timeoutSeconds", 1),
        ("periodSeconds", 10),
        ("successThreshold", 1),
        ("failureThreshold", 3),
    ):
        probe.setdefault(field, default)
    if "httpGet" in probe:
        probe["httpGet"].setdefault("scheme", "HTTP")
    return probe


def _port(document, ports):
    containers = document["spec"]["template"]["spec"]["containers"]
    if len(containers) != 1:
        raise RuntimeError("API slot must have one application container")
    current = next(
        (p["containerPort"] for p in containers[0].get("ports", []) if p.get("name") == "http"),
        None,
    )
    configured = next(
        (e.get("value") for e in containers[0].get("env", []) if e["name"] == "PORT"), None
    )
    if current not in ports or configured != str(current):
        raise RuntimeError("API http port and PORT must agree with the configured slot")
    return ports[1] if current == ports[0] else ports[0]


def api_patch(document, image, ports, assets_path):
    port = _port(document, ports)
    spec = document["spec"]["template"]["spec"]
    container = spec["containers"][0]
    env = copy.deepcopy(container["env"])
    next(e for e in env if e["name"] == "PORT")["value"] = str(port)
    bound = copy.deepcopy(container["ports"])
    http_port = next(p for p in bound if p.get("name") == "http")
    http_port["containerPort"] = port
    if "hostPort" in http_port:
        http_port["hostPort"] = port
    for item in bound:
        item.setdefault("protocol", "TCP")
    lifecycle = copy.deepcopy(container.get("lifecycle", {}))
    lifecycle["preStop"] = {"exec": {"command": ["/bin/sh", "-c", "sleep 10"]}}
    mounts = [m for m in container.get("volumeMounts", []) if m["name"] != "lambchat-assets"]
    if any(m["mountPath"] == "/app/static/assets" for m in mounts):
        raise RuntimeError("an unrelated volume already owns the static assets path")
    mounts.append({"name": "lambchat-assets", "mountPath": "/app/static/assets", "readOnly": True})
    volumes = [v for v in spec.get("volumes", []) if v["name"] != "lambchat-assets"]
    volumes.append(
        {"name": "lambchat-assets", "hostPath": {"path": assets_path, "type": "Directory"}}
    )
    liveness = copy.deepcopy(
        container.get("livenessProbe", {"httpGet": {"path": "/health", "port": "http"}})
    )
    for probe_type in ("httpGet", "tcpSocket"):
        if probe_type in liveness:
            liveness[probe_type]["port"] = "http"
    return _patch(
        {
            "/spec/strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
            },
            "/spec/minReadySeconds": 5,
            "/spec/template/spec/terminationGracePeriodSeconds": 150,
            "/spec/template/spec/volumes": volumes,
            f"{_CONTAINER}/image": image,
            f"{_CONTAINER}/env": env,
            f"{_CONTAINER}/ports": bound,
            f"{_CONTAINER}/lifecycle": lifecycle,
            f"{_CONTAINER}/volumeMounts": mounts,
            f"{_CONTAINER}/livenessProbe": _probe(liveness),
            f"{_CONTAINER}/readinessProbe": _probe(
                {
                    "httpGet": {"path": "/ready", "port": "http"},
                    "periodSeconds": 2,
                    "timeoutSeconds": 2,
                    "failureThreshold": 3,
                }
            ),
            f"{_CONTAINER}/startupProbe": _probe(
                {
                    "httpGet": {"path": "/ready", "port": "http"},
                    "periodSeconds": 2,
                    "timeoutSeconds": 2,
                    "failureThreshold": 90,
                }
            ),
        }
    )


def worker_patch(document, image):
    if len(document["spec"]["template"]["spec"]["containers"]) != 1:
        raise RuntimeError("worker must have one application container")
    probe = {
        "exec": {
            "command": [
                "/app/.venv/bin/python",
                "-c",
                "import os,time;from pathlib import Path;p=Path('/tmp/lambchat-worker.ready');"
                "assert 0<=time.time()-p.stat().st_mtime<30;os.kill(int(p.read_text()),0)",
            ]
        },
        "periodSeconds": 5,
        "timeoutSeconds": 2,
        "failureThreshold": 3,
    }
    return _patch(
        {
            "/spec/strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
            },
            "/spec/minReadySeconds": 5,
            "/spec/template/spec/terminationGracePeriodSeconds": 300,
            f"{_CONTAINER}/image": image,
            f"{_CONTAINER}/readinessProbe": _probe(probe),
            f"{_CONTAINER}/startupProbe": _probe({**probe, "failureThreshold": 60}),
        }
    )


def _require_ready(document):
    count = document["spec"].get("replicas", 1)
    status = document.get("status", {})
    if (
        count < 1
        or status.get("observedGeneration", 0) < document["metadata"]["generation"]
        or any(
            status.get(key, 0) < count
            for key in ("readyReplicas", "availableReplicas", "updatedReplicas")
        )
    ):
        raise RuntimeError(f"deployment {document['metadata']['name']} is not fully ready")


def service_probe(route):
    port = next(p["nodePort"] for p in route["ports"] if p.get("targetPort") == "http")
    origin = f"http://127.0.0.1:{port}"

    def fetch(path):
        with urllib.request.urlopen(origin + path, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Service HTTP probe did not return 200")
            return response.read(512 * 1024), response.headers.get("Content-Type", "")

    try:
        ready, _ = fetch("/ready")
        if json.loads(ready).get("status") != "ready":
            raise RuntimeError("Service is not ready")
        html, content_type = fetch("/")
        assets = re.findall(rb"""(?:src|href)=["'](/assets/[^"']+\.js)["']""", html)
        if "text/html" not in content_type or not assets:
            raise RuntimeError("Service HTML has no JavaScript asset")
        for asset in set(assets):
            body, content_type = fetch(asset.decode("utf-8"))
            if "javascript" not in content_type or body.lstrip().startswith(b"<"):
                raise RuntimeError("Service asset probe returned invalid JavaScript")
    except (OSError, ValueError) as error:
        raise RuntimeError("Service HTTP probe failed") from error


def _owned_pods(document, pods, replicasets):
    owners = {
        rs["metadata"]["name"]
        for rs in replicasets
        if any(
            owner.get("uid") == document["metadata"]["uid"]
            for owner in rs["metadata"].get("ownerReferences", [])
        )
    }
    return [
        p
        for p in pods
        if any(o.get("name") in owners for o in p["metadata"].get("ownerReferences", []))
        and p.get("status", {}).get("phase") not in ("Succeeded", "Failed")
    ]


def _check_port(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("0.0.0.0", port))
    except OSError as error:
        raise RuntimeError(f"standby port {port} is unavailable on this host") from error


def deploy(namespace, apis, worker, service, image):
    names = [name for name, _ports in apis] + [worker]
    if len(set(names)) != len(names):
        raise RuntimeError("deployment names must be distinct")
    documents = {
        name: kubectl(namespace, "get", "deployment", name, "-o", "json") for name in names
    }
    for document in documents.values():
        _require_ready(document)
    route = kubectl(namespace, "get", "service", service, "-o", "json")["spec"]
    if not any(p.get("targetPort") == "http" for p in route["ports"]):
        raise RuntimeError("Service must use the named http targetPort")
    pods = kubectl(namespace, "get", "pods", "-o", "json")["items"]
    replicasets = kubectl(namespace, "get", "replicasets", "-o", "json")["items"]
    old_pods = {}
    for name, document in documents.items():
        old_pods[name] = _owned_pods(document, pods, replicasets)
        if not old_pods[name] or any(
            p["metadata"].get("deletionTimestamp")
            or not any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in p.get("status", {}).get("conditions", [])
            )
            for p in old_pods[name]
        ):
            raise RuntimeError(f"deployment {name} has missing, terminating or unready pods")
    for name, ports in apis:
        document = documents[name]
        if document["spec"].get("replicas", 1) != 1 or not document["spec"]["template"]["spec"].get(
            "hostNetwork"
        ):
            raise RuntimeError("each API slot must be a single hostNetwork replica")
        if not route.get("selector") or any(
            document["spec"]["template"]["metadata"]["labels"].get(k) != v
            for k, v in route["selector"].items()
        ):
            raise RuntimeError(f"Service does not select API slot {name}")
        alternate = _port(document, ports)
        nodes = {p["spec"]["nodeName"] for p in old_pods[name]}
        if any(
            p["spec"].get("nodeName") in nodes
            and p["spec"].get("hostNetwork")
            and p.get("status", {}).get("phase") not in ("Succeeded", "Failed")
            and any(
                bound.get("containerPort") == alternate
                for c in p["spec"]["containers"]
                for bound in c.get("ports", [])
            )
            for p in pods
        ):
            raise RuntimeError(f"standby port {alternate} is already declared on the API node")
        _check_port(alternate)
    service_probe(route)
    targets = [
        (
            p["metadata"]["name"],
            documents[name]["spec"]["template"]["spec"]["containers"][0]["name"],
        )
        for name, _ports in apis
        for p in old_pods[name]
    ]
    cache = publish_assets(namespace, image, targets)
    patches = {name: api_patch(documents[name], image, ports, cache) for name, ports in apis}
    patches[worker] = worker_patch(documents[worker], image)
    changed = []

    def apply(name, patch, generation):
        fence = {"op": "test", "path": "/metadata/generation", "value": generation}
        kubectl(
            namespace,
            "patch",
            "deployment",
            name,
            "--type=json",
            "--patch-file=/dev/stdin",
            payload=[fence, *patch],
        )
        kubectl(namespace, "rollout", "status", f"deployment/{name}", "--timeout=600s")
        observed = kubectl(namespace, "get", "deployment", name, "-o", "json")
        _require_ready(observed)
        if any(_value(observed, op["path"]) != op.get("value", _MISSING) for op in patch):
            raise RuntimeError(f"deployment {name} changed while rolling")
        return observed

    try:
        for name in names:
            print(f"Rolling {name}", flush=True)
            changed.append(name)
            observed = apply(name, patches[name], documents[name]["metadata"]["generation"])
            if observed["spec"]["template"] != documents[name]["spec"]["template"]:
                kubectl(
                    namespace,
                    "wait",
                    "--for=delete",
                    *[f"pod/{p['metadata']['name']}" for p in old_pods[name]],
                    "--timeout=360s",
                )
            service_probe(route)
    except (Exception, KeyboardInterrupt) as error:
        failures = []
        for name in reversed(changed):
            try:
                current = kubectl(namespace, "get", "deployment", name, "-o", "json")
                for operation in patches[name]:
                    actual = _value(current, operation["path"])
                    if actual != operation["value"] and actual != _value(
                        documents[name], operation["path"]
                    ):
                        raise RuntimeError(
                            f"deployment {name} has an external change at {operation['path']}"
                        )
                restore = inverse_patch(documents[name], patches[name], current)
                template = [op for op in restore if op["path"].startswith("/spec/template/")]
                controls = [op for op in restore if not op["path"].startswith("/spec/template/")]
                before = _owned_pods(
                    current,
                    kubectl(namespace, "get", "pods", "-o", "json")["items"],
                    kubectl(namespace, "get", "replicasets", "-o", "json")["items"],
                )
                old_names = {p["metadata"]["name"] for p in old_pods[name]}
                retiring = [
                    f"pod/{p['metadata']['name']}"
                    for p in before
                    if p["metadata"]["name"] not in old_names
                ]
                if template:
                    safe = _patch(
                        {
                            "/spec/strategy": {
                                "type": "RollingUpdate",
                                "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
                            }
                        }
                    )
                    current = apply(name, safe + template, current["metadata"]["generation"])
                if controls:
                    current = apply(name, controls, current["metadata"]["generation"])
                _require_ready(kubectl(namespace, "get", "deployment", name, "-o", "json"))
                if retiring:
                    kubectl(namespace, "wait", "--for=delete", *retiring, "--timeout=360s")
            except Exception:
                failures.append(name)
        try:
            service_probe(route)
        except Exception:
            failures.append(service)
        if failures:
            raise RuntimeError(
                f"release failed; rollback incomplete for {', '.join(failures)}"
            ) from error
        raise
    print("All deployments are ready; previous pods have exited", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tag", help="explicit main-YYYYMMDD-HHMMSS or develop-YYYYMMDD-HHMMSS image tag"
    )
    parser.add_argument("--namespace", default="lambchat")
    parser.add_argument("--api", action="append", metavar="DEPLOYMENT:PORT1:PORT2")
    parser.add_argument("--worker", default="lambchat-worker")
    parser.add_argument("--service", default="lambchat")
    args = parser.parse_args()

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupt)
    if not re.fullmatch(r"(?:main|develop)-\d{8}-\d{6}", args.tag) or (
        args.namespace == "lambchat" and not args.tag.startswith("main-")
    ):
        parser.error("use an explicit release tag; production only accepts main tags")
    apis = []
    for value in args.api or ["lambchat-a:8011:8013", "lambchat-b:8012:8014"]:
        try:
            name, first, second = value.split(":")
            ports = (int(first), int(second))
            if not name or ports[0] == ports[1] or any(not 1 <= p <= 65535 for p in ports):
                raise ValueError
        except ValueError:
            parser.error("--api requires DEPLOYMENT:PORT1:PORT2 with two distinct valid ports")
        apis.append((name, ports))
    with deployment_lock("/data/lambchat-k8s/deployment.lock"):
        deploy(
            args.namespace,
            apis,
            args.worker,
            args.service,
            f"ghcr.io/yanyutin753/lambchat:{args.tag}",
        )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
    except KeyboardInterrupt:
        raise SystemExit("deployment interrupted") from None
