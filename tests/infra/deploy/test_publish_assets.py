from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REAL_RUN = subprocess.run
CACHE_PATH = "/data/lambchat-k8s/static-assets"


@pytest.fixture
def assets():
    path = Path(__file__).resolve().parents[3] / "k8s/scripts/publish_assets.py"
    assert path.exists(), "the deployment asset publisher must be versioned"
    spec = importlib.util.spec_from_file_location("lambchat_publish_assets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        directory = tarfile.TarInfo(".")
        directory.type = tarfile.DIRTYPE
        tar.addfile(directory)
        for name, content, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.REGTYPE:
                item.size = len(content)
                tar.addfile(item, io.BytesIO(content))
            else:
                item.linkname = content.decode()
                tar.addfile(item)
    return output.getvalue()


class Cluster:
    def __init__(self, root, *, nodes=1, fail_wait=False):
        self.nodes = nodes
        self.fail_wait = fail_wait
        self.calls = []
        self.created = None
        self.deleted = False
        self.override_archive = None
        self.written_pods = []
        self.cache = root / "cache"
        self.old = root / "old"
        self.new = root / "new"
        for directory in (self.cache, self.old, self.new):
            directory.mkdir()
        (self.cache / "retained-11111111.js").write_bytes(b"retained")
        (self.old / "old-22222222.js").write_bytes(b"old")
        (self.new / "new-33333333.js").write_bytes(b"new")

    def pod(self, name):
        return {
            "metadata": {"name": name},
            "spec": {
                "nodeName": "node-1",
                "volumes": [{"name": "assets", "hostPath": {"path": CACHE_PATH}}],
                "containers": [
                    {
                        "name": "api",
                        "volumeMounts": (
                            [
                                {
                                    "name": "assets",
                                    "mountPath": "/app/static/assets",
                                    "readOnly": True,
                                }
                            ]
                            if name == "mounted-old"
                            else []
                        ),
                    }
                ],
            },
            "status": {"phase": "Running"},
        }

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        assert argv[:5] == ["k3s", "kubectl", "--request-timeout=20s", "-n", "testing"]
        args = argv[5:]
        if args[:2] == ["get", "nodes"]:
            result = {"items": [{"metadata": {"name": f"node-{i + 1}"}} for i in range(self.nodes)]}
            return subprocess.CompletedProcess(argv, 0, json.dumps(result).encode(), b"")
        if args[:2] == ["get", "pod"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.pod(args[2])).encode(), b"")
        if args[0] in {"apply", "create"}:
            self.created = json.loads(kwargs["input"])
            return subprocess.CompletedProcess(argv, 0, b"created", b"")
        if args[0] == "wait":
            if self.fail_wait:
                raise subprocess.CalledProcessError(1, argv, stderr=b"publisher did not start")
            return subprocess.CompletedProcess(argv, 0, b"ready", b"")
        if args[:2] == ["delete", "pod"]:
            self.deleted = True
            return subprocess.CompletedProcess(argv, 0, b"deleted", b"")
        if args[0] == "exec":
            before, command = args[1 : args.index("--")], args[args.index("--") + 1 :]
            pod = next(value for value in before if value not in {"-i", "-c", "api", "publisher"})
            publisher = self.created and pod == self.created["metadata"]["name"]
            if command[0] == "tar":
                source = command[command.index("-C") + 1]
                assert source in {"/app/static/assets", "/cache"}
                directory = (
                    self.cache
                    if source == "/cache" or pod == "mounted-old"
                    else self.new
                    if publisher
                    else self.old
                )
                data = (
                    self.override_archive
                    if pod == "unmounted-old" and self.override_archive
                    else archive(
                        [
                            (
                                "./" + str(path.relative_to(directory)),
                                path.read_bytes(),
                                tarfile.REGTYPE,
                            )
                            for path in sorted(directory.rglob("*"))
                            if path.is_file()
                        ]
                    )
                )
                return subprocess.CompletedProcess(argv, 0, data, b"")
            assert command[0].endswith("python") and command[1] == "-c"
            destination = command[3]
            assert destination in {"/cache", "/app/static/assets"}
            directory = self.cache if destination == "/cache" else self.old
            self.written_pods.append(pod)
            return REAL_RUN(
                [sys.executable, "-c", command[2], str(directory)],
                input=kwargs["input"],
                capture_output=True,
                check=True,
            )
        raise AssertionError(f"unexpected kubectl operation: {args}")


@pytest.fixture
def cluster(assets, monkeypatch, tmp_path):
    instance = Cluster(tmp_path)
    monkeypatch.setenv("KUBECTL", "k3s kubectl --request-timeout=20s")
    monkeypatch.setattr(assets.subprocess, "run", instance)
    return instance


def publish(assets):
    return assets.publish_assets(
        "testing",
        "ghcr.io/example/lambchat:new",
        [("unmounted-old", "api"), ("mounted-old", "api")],
    )


def test_publication_retains_old_hashes_adds_new_assets_and_backfills_only_unmounted_pods(
    assets, cluster
):
    assert publish(assets) == CACHE_PATH
    expected = {
        "retained-11111111.js": b"retained",
        "old-22222222.js": b"old",
        "new-33333333.js": b"new",
    }
    assert {path.name: path.read_bytes() for path in cluster.cache.iterdir()} == expected
    assert all(path.stat().st_mode & 0o444 == 0o444 for path in cluster.cache.iterdir())
    assert {path.name: path.read_bytes() for path in cluster.old.iterdir()} == expected
    assert "unmounted-old" in cluster.written_pods
    assert "mounted-old" not in cluster.written_pods
    assert cluster.deleted


def test_publisher_has_only_the_target_image_and_single_node_cache_mount(assets, cluster):
    publish(assets)
    pod = cluster.created
    spec = pod["spec"]
    assert spec["nodeName"] == "node-1"
    assert spec["automountServiceAccountToken"] is False
    assert spec["restartPolicy"] == "Never"
    assert spec.get("hostNetwork", False) is False
    assert spec["volumes"] == [
        {"name": "assets", "hostPath": {"path": CACHE_PATH, "type": "DirectoryOrCreate"}}
    ]
    (container,) = spec["containers"]
    assert container["image"] == "ghcr.io/example/lambchat:new"
    assert "sleep" in " ".join(container["command"])
    assert container.get("securityContext", spec.get("securityContext", {}))["runAsUser"] == 0
    for key in ("env", "envFrom", "imagePullSecrets", "serviceAccountName"):
        assert not spec.get(key)
        assert not container.get(key)
    assert container["volumeMounts"] == [{"name": "assets", "mountPath": "/cache"}]


def test_multinode_cluster_is_rejected_before_creating_or_writing_anything(assets, cluster):
    cluster.nodes = 2
    with pytest.raises(RuntimeError, match="(?i)single.node|multi.node"):
        publish(assets)
    assert cluster.created is None
    assert cluster.written_pods == []


def test_publisher_is_deleted_when_startup_fails(assets, cluster):
    cluster.fail_wait = True
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        publish(assets)
    assert cluster.deleted


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside.js", tarfile.REGTYPE),
        ("/tmp/outside.js", tarfile.REGTYPE),
        ("linked.js", tarfile.SYMTYPE),
        ("linked.js", tarfile.LNKTYPE),
        ("index.html", tarfile.REGTYPE),
    ],
)
def test_unsafe_asset_archives_are_rejected_and_publisher_is_deleted(assets, cluster, name, kind):
    cluster.override_archive = archive(
        [(name, b"/private/secret" if kind != tarfile.REGTYPE else b"unsafe", kind)]
    )
    with pytest.raises((RuntimeError, subprocess.CalledProcessError, ValueError)):
        publish(assets)
    assert cluster.deleted
    assert not (cluster.cache.parent / "outside.js").exists()
    assert not (cluster.cache / "index.html").exists()
    assert not (cluster.cache / "linked.js").exists()


def test_different_content_at_an_existing_hash_is_rejected_without_overwriting_cache(
    assets, cluster
):
    existing = cluster.cache / "old-22222222.js"
    existing.write_bytes(b"previous immutable contents")
    with pytest.raises((RuntimeError, subprocess.CalledProcessError, ValueError)):
        publish(assets)
    assert existing.read_bytes() == b"previous immutable contents"
    assert cluster.deleted


def test_nested_build_assets_and_identical_existing_hashes_are_preserved(assets, cluster):
    (cluster.cache / "old-22222222.js").write_bytes(b"old")
    fonts = cluster.new / "fonts"
    fonts.mkdir()
    (fonts / "text-55555555.woff2").write_bytes(b"font")

    publish(assets)

    assert (cluster.cache / "fonts/text-55555555.woff2").read_bytes() == b"font"
    assert (cluster.old / "fonts/text-55555555.woff2").read_bytes() == b"font"
    assert (cluster.cache / "old-22222222.js").read_bytes() == b"old"


def test_existing_cache_symlinks_cannot_redirect_asset_writes(assets, cluster, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (cluster.cache / "nested").symlink_to(outside, target_is_directory=True)
    cluster.override_archive = archive([("nested/escape-44444444.js", b"unsafe", tarfile.REGTYPE)])
    with pytest.raises((RuntimeError, subprocess.CalledProcessError, ValueError)):
        publish(assets)
    assert list(outside.iterdir()) == []
    assert cluster.deleted
