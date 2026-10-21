from __future__ import annotations

import copy
import importlib.util
import socket
import sys
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture
def updater(monkeypatch):
    directory = Path(__file__).resolve().parents[3] / "k8s/scripts"
    monkeypatch.syspath_prepend(str(directory))
    path = directory / "update.py"
    assert path.exists(), "production updater must be versioned in the repository"
    spec = importlib.util.spec_from_file_location("lambchat_updater", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "service_probe", lambda route: None, raising=False)

    class FreeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            pass

    monkeypatch.setattr(socket, "socket", lambda *args: FreeSocket())
    return module


def deployment(name, port=8011):
    return {
        "metadata": {"name": name, "uid": name, "generation": 1},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "lambchat", "slot": name}},
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
            },
            "template": {
                "metadata": {"labels": {"app": "lambchat", "slot": name}},
                "spec": {
                    "hostNetwork": True,
                    "terminationGracePeriodSeconds": 60,
                    "containers": [
                        {
                            "name": "lambchat",
                            "image": "old-image",
                            "ports": [{"name": "http", "containerPort": port}],
                            "env": [
                                {"name": "PORT", "value": str(port)},
                                {"name": "KEEP", "value": "unchanged"},
                            ],
                            "envFrom": [{"secretRef": {"name": "private-settings"}}],
                            "resources": {"limits": {"memory": "2Gi"}},
                        }
                    ],
                },
            },
        },
        "status": {
            "readyReplicas": 1,
            "updatedReplicas": 1,
            "availableReplicas": 1,
            "observedGeneration": 1,
        },
    }


def apply_patch(document, patch):
    for operation in patch:
        parts = operation["path"].strip("/").split("/")
        parent = document
        for key in parts[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent[key]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation["op"] == "test":
            if parent[key] != operation["value"]:
                raise RuntimeError("JSON patch test rejected stale generation")
            continue
        if operation["op"] == "remove":
            del parent[key]
        else:
            parent[key] = copy.deepcopy(operation["value"])


def test_api_patch_switches_image_and_free_port_together_preserving_other_settings(updater):
    original = deployment("lambchat-a")
    current = copy.deepcopy(original)
    patch = updater.api_patch(current, "new-image", (8011, 8013), "/retained-assets")
    apply_patch(current, patch)
    container = current["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "new-image"
    assert container["ports"] == [{"name": "http", "containerPort": 8013, "protocol": "TCP"}]
    assert container["env"] == [
        {"name": "PORT", "value": "8013"},
        {"name": "KEEP", "value": "unchanged"},
    ]
    assert container["envFrom"] == original["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    assert container["resources"] == {"limits": {"memory": "2Gi"}}
    assert current["spec"]["strategy"]["rollingUpdate"] == {"maxSurge": 1, "maxUnavailable": 0}
    assert current["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 150
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "http",
        "scheme": "HTTP",
    }
    assert container["startupProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "http",
        "scheme": "HTTP",
    }
    assert {
        "name": "lambchat-assets",
        "mountPath": "/app/static/assets",
        "readOnly": True,
    } in container["volumeMounts"]
    assert original == deployment("lambchat-a")


def test_next_api_release_alternates_back_to_original_port(updater):
    current = deployment("lambchat-a", port=8013)
    apply_patch(current, updater.api_patch(current, "new-image", (8011, 8013), "/assets"))
    assert current["spec"]["template"]["spec"]["containers"][0]["ports"][0]["containerPort"] == 8011


def test_explicit_host_port_moves_with_named_container_port(updater):
    current = deployment("lambchat-a")
    port = current["spec"]["template"]["spec"]["containers"][0]["ports"][0]
    port.update({"hostPort": 8011, "protocol": "TCP"})
    apply_patch(current, updater.api_patch(current, "new-image", (8011, 8013), "/assets"))
    assert current["spec"]["template"]["spec"]["containers"][0]["ports"][0] == {
        "name": "http",
        "containerPort": 8013,
        "hostPort": 8013,
        "protocol": "TCP",
    }


def test_inverse_patch_restores_missing_and_existing_fields_exactly(updater):
    original = deployment("lambchat-a")
    current = copy.deepcopy(original)
    patch = updater.api_patch(current, "new-image", (8011, 8013), "/assets")
    inverse = updater.inverse_patch(current, patch)
    apply_patch(current, patch)
    apply_patch(current, inverse)
    assert current == original


class Cluster:
    def __init__(self, failing=None):
        self.documents = {
            name: deployment(name, port)
            for name, port in [
                ("lambchat-a", 8011),
                ("lambchat-b", 8012),
                ("lambchat-worker", 8020),
            ]
        }
        self.failing = failing
        self.patched = []
        self.waited = []
        self.observed_rollouts = []
        self.pods = [
            {
                "metadata": {
                    "name": f"{name}-old",
                    "labels": document["spec"]["template"]["metadata"]["labels"],
                    "ownerReferences": [{"kind": "ReplicaSet", "name": f"{name}-rs"}],
                },
                "spec": {
                    **copy.deepcopy(document["spec"]["template"]["spec"]),
                    "nodeName": "one-node",
                },
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
            }
            for name, document in self.documents.items()
        ]

    def __call__(self, namespace, *args, payload=None):
        assert namespace == "testing"
        if args[:2] == ("get", "deployment"):
            return copy.deepcopy(self.documents[args[2]])
        if args[:2] == ("get", "service"):
            return {"spec": {"selector": {"app": "lambchat"}, "ports": [{"targetPort": "http"}]}}
        if args[:2] == ("get", "pods"):
            return {"items": copy.deepcopy(self.pods)}
        if args[:2] == ("get", "replicasets"):
            return {
                "items": [
                    {"metadata": {"name": f"{name}-rs", "ownerReferences": [{"uid": name}]}}
                    for name in self.documents
                ]
            }
        if args[:2] == ("patch", "deployment"):
            name = args[2]
            apply_patch(self.documents[name], payload)
            self.patched.append(
                (name, self.documents[name]["spec"]["template"]["spec"]["containers"][0]["image"])
            )
            return "patched"
        if args[:2] == ("rollout", "status"):
            name = args[2].split("/")[-1]
            self.observed_rollouts.append((name, copy.deepcopy(self.documents[name])))
            if (
                name == self.failing
                and self.documents[name]["spec"]["template"]["spec"]["containers"][0]["image"]
                == "new-image"
            ):
                raise RuntimeError("injected readiness failure")
            return "ready"
        if args[0] == "wait":
            self.waited.append(args)
            return "deleted"
        raise AssertionError(f"unexpected kubectl arguments: {args}")


@pytest.mark.parametrize("failing", ["lambchat-b", "lambchat-worker"])
def test_failed_release_rolls_back_every_changed_deployment(updater, monkeypatch, failing):
    cluster = Cluster(failing)
    original = copy.deepcopy(cluster.documents)
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    with pytest.raises(RuntimeError, match="injected readiness failure"):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    assert cluster.documents == original
    changed = {name for name, image in cluster.patched if image == "new-image"}
    restored = {name for name, image in cluster.patched if image == "old-image"}
    assert changed == restored


def test_success_waits_for_old_pods_to_exit_before_finishing(updater, monkeypatch):
    cluster = Cluster()
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    updater.deploy(
        "testing",
        [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
        "lambchat-worker",
        "lambchat",
        "new-image",
    )
    assert len(cluster.waited) == 3
    assert all(image == "new-image" for _, image in cluster.patched)


@pytest.mark.parametrize("controls_changed", [False, True])
def test_repeated_image_keeps_unchanged_worker_pods(updater, monkeypatch, controls_changed):
    cluster = Cluster()
    worker = cluster.documents["lambchat-worker"]
    apply_patch(worker, updater.worker_patch(worker, "new-image"))
    if controls_changed:
        worker["spec"]["minReadySeconds"] = 0
    cluster.pods[-1]["spec"].update(copy.deepcopy(worker["spec"]["template"]["spec"]))
    original_template = copy.deepcopy(worker["spec"]["template"])
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    updater.deploy(
        "testing",
        [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
        "lambchat-worker",
        "lambchat",
        "new-image",
    )
    assert worker["spec"]["template"] == original_template
    assert len(cluster.waited) == 2
    assert all("pod/lambchat-worker-old" not in args for args in cluster.waited)
    assert any(name == "lambchat-worker" for name, _ in cluster.observed_rollouts)


def test_rejected_patch_rolls_back_previous_members_without_removing_absent_fields(
    updater, monkeypatch
):
    cluster = Cluster()
    original = copy.deepcopy(cluster.documents)
    rejected = [False]

    def kubectl(namespace, *args, payload=None):
        if args[:3] == ("patch", "deployment", "lambchat-b") and not rejected[0]:
            rejected[0] = True
            raise RuntimeError("injected patch rejection")
        return cluster(namespace, *args, payload=payload)

    monkeypatch.setattr(updater, "kubectl", kubectl)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    with pytest.raises(RuntimeError, match="injected patch rejection"):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    assert cluster.documents == original


def test_rollback_retains_make_before_break_until_old_template_is_ready(updater, monkeypatch):
    cluster = Cluster("lambchat-b")
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    with pytest.raises(RuntimeError, match="injected readiness failure"):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    rollbacks = [
        (name, doc)
        for name, doc in cluster.observed_rollouts
        if doc["spec"]["template"]["spec"]["containers"][0]["image"] == "old-image"
    ]
    for name in ("lambchat-a", "lambchat-b"):
        first_restore = next(doc for candidate, doc in rollbacks if candidate == name)
        assert first_restore["spec"]["strategy"]["rollingUpdate"] == {
            "maxSurge": 1,
            "maxUnavailable": 0,
        }
    assert all(
        doc["spec"]["strategy"]["rollingUpdate"] == {"maxSurge": 0, "maxUnavailable": 1}
        for doc in cluster.documents.values()
    )


def test_undeclared_host_process_using_standby_port_blocks_release(updater, monkeypatch):
    import socket

    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            raise OSError("address already in use")

    cluster = Cluster()
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(
        updater, "publish_assets", lambda *args: pytest.fail("occupied port reached publication")
    )
    monkeypatch.setattr(socket, "socket", lambda *args: OccupiedSocket())
    with pytest.raises(RuntimeError, match="standby port"):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    assert cluster.patched == []


def test_rollback_does_not_overwrite_an_external_environment_change(updater, monkeypatch):
    cluster = Cluster("lambchat-b")

    def kubectl(namespace, *args, payload=None):
        if args[:3] == ("rollout", "status", "deployment/lambchat-b"):
            cluster.documents["lambchat-a"]["spec"]["template"]["spec"]["containers"][0]["env"][1][
                "value"
            ] = "external-change"
        return cluster(namespace, *args, payload=payload)

    monkeypatch.setattr(updater, "kubectl", kubectl)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    with pytest.raises(RuntimeError, match="rollback incomplete.*lambchat-a"):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    assert (
        cluster.documents["lambchat-a"]["spec"]["template"]["spec"]["containers"][0]["env"][1][
            "value"
        ]
        == "external-change"
    )


def test_forward_patch_rejects_spec_changed_after_snapshot(updater, monkeypatch):
    cluster = Cluster()
    changed = [False]

    def kubectl(namespace, *args, payload=None):
        if args[:3] == ("patch", "deployment", "lambchat-b") and not changed[0]:
            changed[0] = True
            cluster.documents["lambchat-b"]["metadata"]["generation"] = 2
            cluster.documents["lambchat-b"]["status"]["observedGeneration"] = 2
            cluster.documents["lambchat-b"]["spec"]["template"]["spec"]["containers"][0]["env"][1][
                "value"
            ] = "external-before-patch"
        return cluster(namespace, *args, payload=payload)

    monkeypatch.setattr(updater, "kubectl", kubectl)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    with pytest.raises(RuntimeError):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    container = cluster.documents["lambchat-b"]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "old-image"
    assert container["env"][1]["value"] == "external-before-patch"


@pytest.mark.parametrize("failing", [None, "lambchat-b", "lambchat-worker"])
def test_kubernetes_probe_defaults_preserve_exact_ownership_checks(updater, monkeypatch, failing):
    cluster = Cluster(failing)
    original = copy.deepcopy(cluster.documents)

    def kubectl(namespace, *args, payload=None):
        result = cluster(namespace, *args, payload=payload)
        if args[:2] == ("patch", "deployment"):
            container = cluster.documents[args[2]]["spec"]["template"]["spec"]["containers"][0]
            for key in ("readinessProbe", "startupProbe", "livenessProbe"):
                if key not in container:
                    continue
                probe = container[key]
                for field, default in [
                    ("timeoutSeconds", 1),
                    ("periodSeconds", 10),
                    ("successThreshold", 1),
                    ("failureThreshold", 3),
                ]:
                    probe.setdefault(field, default)
                if "httpGet" in probe:
                    probe["httpGet"].setdefault("scheme", "HTTP")
        return result

    monkeypatch.setattr(updater, "kubectl", kubectl)
    monkeypatch.setattr(updater, "publish_assets", lambda *args: "/assets")
    if failing:
        with pytest.raises(RuntimeError, match="injected readiness failure"):
            updater.deploy(
                "testing",
                [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
                "lambchat-worker",
                "lambchat",
                "new-image",
            )
        assert cluster.documents == original
    else:
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
        assert all(
            d["spec"]["template"]["spec"]["containers"][0]["image"] == "new-image"
            for d in cluster.documents.values()
        )


@pytest.mark.parametrize("problem", ["unready", "port_in_use"])
def test_failed_preflight_changes_nothing(updater, monkeypatch, problem):
    cluster = Cluster()
    if problem == "unready":
        cluster.documents["lambchat-b"]["status"]["readyReplicas"] = 0
    else:
        occupied = copy.deepcopy(cluster.pods[0])
        occupied["metadata"]["name"] = "other-owner"
        occupied["spec"]["containers"][0]["ports"][0]["containerPort"] = 8013
        cluster.pods.append(occupied)
    monkeypatch.setattr(updater, "kubectl", cluster)
    monkeypatch.setattr(
        updater,
        "publish_assets",
        lambda *args: pytest.fail("preflight must precede asset publication"),
    )
    with pytest.raises(RuntimeError):
        updater.deploy(
            "testing",
            [("lambchat-a", (8011, 8013)), ("lambchat-b", (8012, 8014))],
            "lambchat-worker",
            "lambchat",
            "new-image",
        )
    assert cluster.patched == []


def test_deployment_lock_rejects_concurrent_run_without_waiting(updater, tmp_path):
    with updater.deployment_lock(tmp_path / "deployment.lock"):
        with pytest.raises(RuntimeError, match="busy"):
            with updater.deployment_lock(tmp_path / "deployment.lock"):
                pytest.fail("concurrent deployment entered")


def test_service_probe_rejects_html_returned_for_javascript(monkeypatch):
    # Load separately because rollout tests replace the network probe at its boundary.
    path = Path(__file__).resolve().parents[3] / "k8s/scripts/update.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("lambchat_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    responses = [
        (b'{"status":"ready"}', "application/json"),
        (b'<html><script src="/assets/app-hash.js"></script></html>', "text/html"),
        (b"<html>fallback is not JavaScript</html>", "text/html"),
    ]

    def urlopen(*args, **kwargs):
        body, content_type = responses.pop(0)
        response = BytesIO(body)
        response.headers = {"Content-Type": content_type}
        response.status = 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(RuntimeError, match="asset"):
        module.service_probe({"ports": [{"port": 80, "nodePort": 30080, "targetPort": "http"}]})
