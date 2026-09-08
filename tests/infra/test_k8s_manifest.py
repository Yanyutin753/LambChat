"""k8s 清单契约：API 与独立 arq worker 分进程部署。

2026-09-09 断联复盘后拆分（此前契约相反：API 内嵌 worker 且无独立
Deployment——内嵌时 agent 任务与 API 共享事件循环，重任务饿死 SSE/沙箱通道
心跳，API 滚动发布还会杀运行中的任务）。本文件锁定新契约：API 关内嵌、
lambchat-worker Deployment 跑 worker_main 入口、Service 不把流量导给 worker。
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_k8s_docs() -> list[dict]:
    return [
        doc
        for doc in yaml.safe_load_all((ROOT / "k8s/lambchat.yaml").read_text())
        if isinstance(doc, dict)
    ]


def _deployment(name: str) -> dict:
    return next(
        doc
        for doc in _load_k8s_docs()
        if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == name
    )


def _env_map(container: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in container.get("env", []):
        if "name" in item and "value" in item:
            result[item["name"]] = item["value"]
    return result


def test_k8s_api_deployment_disables_embedded_arq_worker() -> None:
    """API 进程只服务 HTTP/SSE：TASK_BACKEND=arq 但不内嵌 worker。"""
    container = _deployment("lambchat")["spec"]["template"]["spec"]["containers"][0]
    env = _env_map(container)

    assert env["LAMBCHAT_DISTRIBUTED_MODE"] == "true"
    assert env["TASK_BACKEND"] == "arq"
    assert env["ARQ_EMBEDDED_WORKER"] == "false"


def test_k8s_worker_deployment_runs_standalone_worker_entry() -> None:
    """独立 worker Deployment：跑 worker_main 入口、同样走 arq 队列。"""
    deployment = _deployment("lambchat-worker")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env = _env_map(container)

    assert container["command"] == [
        "/app/.venv/bin/python",
        "-m",
        "src.infra.task.worker_main",
    ]
    assert env["TASK_BACKEND"] == "arq"
    assert env["LAMBCHAT_DISTRIBUTED_MODE"] == "true"
    # worker 不监听 HTTP：不得声明端口
    assert "ports" not in container


def test_k8s_service_selector_excludes_worker_pods() -> None:
    """NodePort Service 只选 API pods——worker 复用同镜像但 label 必须区分，
    否则 worker 会收到 HTTP 流量（无 HTTP 服务，连接直接黑洞）。"""
    service = next(
        doc
        for doc in _load_k8s_docs()
        if doc.get("kind") == "Service" and doc["metadata"]["name"] == "lambchat"
    )
    selector = service["spec"]["selector"]
    worker_labels = _deployment("lambchat-worker")["spec"]["template"]["metadata"]["labels"]

    assert selector == {"app": "lambchat"}
    assert worker_labels == {"app": "lambchat-worker"}
