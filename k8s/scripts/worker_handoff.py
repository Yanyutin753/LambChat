"""Keep accepting new work while retiring workers finish their existing jobs."""

import copy
import time
import uuid
from contextlib import contextmanager

REQUEST = "/tmp/lambchat-worker.drain"
ACK = "/tmp/lambchat-worker.drained"


def _job(document, name):
    template = copy.deepcopy(document["spec"]["template"])
    # A Job's own selector controls this pod. API Services and the worker
    # Deployment must not select the temporary consumer.
    template["metadata"] = {"labels": {"lambchat-release-worker": name}}
    spec = template["spec"]
    spec["restartPolicy"] = "Never"
    spec["containers"][0].setdefault("env", []).append(
        {"name": "LAMBCHAT_RETIRE_AFTER_DRAIN", "value": "1"}
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name},
        "spec": {"backoffLimit": 0, "ttlSecondsAfterFinished": 300, "template": template},
    }


def _request(kube, pod, token):
    kube("exec", pod, "--", "sh", "-ec", 'printf "%s" "$1" > "$2"', "sh", token, REQUEST)


def _pods(kube):
    return {p["metadata"]["name"]: p for p in kube("get", "pods", "-o", "json")["items"]}


@contextmanager
def protect_worker_change(kube, document, retiring):
    """Start capacity first. Request retirement before allowing Kubernetes to send TERM."""
    for pod in retiring:
        kube(
            "exec",
            pod,
            "--",
            "grep",
            "-q",
            "set_release_drain",
            "/app/src/infra/task/worker_main.py",
        )
    token = uuid.uuid4().hex
    name = document["metadata"]["name"] + "-handoff-" + token[:8]
    kube("create", "-f", "-", payload=_job(document, name))
    bridge = None
    requested = []
    try:
        selector = f"job-name={name}"
        end = time.monotonic() + 180
        while time.monotonic() < end:
            pods = kube("get", "pods", "-l", selector, "-o", "json")["items"]
            if pods:
                bridge = pods[0]["metadata"]["name"]
                break
            time.sleep(1)
        if bridge is None:
            raise RuntimeError(f"handoff Job {name} did not start")
        kube("wait", "--for=condition=Ready", "pod/" + bridge, "--timeout=180s")
        for pod in retiring:
            requested.append(pod)
            _request(kube, pod, token)
        # One shared deadline bounds total time even for a large worker deployment.
        end = time.monotonic() + 600
        for pod in requested:
            kube(
                "exec",
                pod,
                "--",
                "sh",
                "-ec",
                'for i in $(seq 1 "$3"); do [ "$(cat "$1" 2>/dev/null)" = "$2" ] && exit 0; sleep 1; done; exit 1',
                "sh",
                ACK,
                token,
                str(max(1, int(end - time.monotonic()))),
            )
        yield
    finally:
        # Resume survivors after a failed patch. A retiring pod keeps its
        # admission fence until it exits, even if another worker is ready.
        live = _pods(kube)
        for pod in requested:
            if pod in live and not live[pod]["metadata"].get("deletionTimestamp"):
                kube("exec", pod, "--", "rm", "-f", REQUEST)
        if bridge and bridge in live and live[bridge]["status"].get("phase") == "Running":
            _request(kube, bridge, token)
        elif not bridge:
            raise RuntimeError(f"inspect handoff Job {name} before retrying")
