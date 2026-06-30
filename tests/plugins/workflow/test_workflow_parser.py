from __future__ import annotations

import hashlib

from src.plugins.workflow.parser import parse_workflow


def test_parse_workflow_maps_supported_nodes_and_edges() -> None:
    payload = {
        "version": "0.3.0",
        "app": {"name": "Demo"},
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {"id": "llm", "type": "llm", "data": {"title": "Think", "model": "gpt"}},
                {"id": "end", "type": "end", "data": {"title": "End"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "llm"},
                {"id": "e2", "source": "llm", "target": "end"},
            ],
        },
    }

    result = parse_workflow(payload, name="Demo")

    graph = result.internal_model["graph"]
    assert result.internal_model["format"] == "lambchat.workflow.v1"
    assert [node["type"] for node in graph["nodes"]] == ["start", "llm", "end"]
    assert [edge["valid"] for edge in graph["edges"]] == [True, True]
    assert result.report["supported_nodes"] == ["end", "llm", "start"]
    assert result.report["unsupported_nodes"] == []
    assert result.report["errors"] == []
    assert result.report["lossless"] is True


def test_parse_workflow_preserves_unsupported_nodes() -> None:
    payload = {
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {
                    "id": "code-1",
                    "type": "code",
                    "data": {
                        "title": "Unsafe Code",
                        "language": "python3",
                        "code": "def main(inputs):\n    return inputs",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "code-1"}],
        }
    }

    result = parse_workflow(payload, name="Unsupported")

    nodes = result.internal_model["graph"]["nodes"]
    assert nodes[1]["type"] == "unsupported"
    assert nodes[1]["supported"] is False
    assert nodes[1]["metadata"] == {
        "unsupported_reason": "blocked_by_policy",
        "source_type": "code",
        "runtime_policy": "blocked_by_policy",
        "policy": "code_execution_disabled",
        "source_present": True,
        "source_bytes": len("def main(inputs):\n    return inputs".encode("utf-8")),
        "language": "python3",
        "source_sha256": hashlib.sha256(
            "def main(inputs):\n    return inputs".encode("utf-8")
        ).hexdigest(),
    }
    assert result.report["unsupported_nodes"] == [
        {
            "id": "code-1",
            "type": "code",
            "title": "Unsafe Code",
            "reason": "blocked_by_policy",
            "metadata": nodes[1]["metadata"],
        }
    ]
    assert result.report["lossless"] is False


def test_parse_workflow_reports_dangling_edges() -> None:
    payload = {
        "graph": {
            "nodes": [{"id": "start", "type": "start"}],
            "edges": [{"id": "dangling", "source": "start", "target": "missing"}],
        }
    }

    result = parse_workflow(payload, name="Dangling")

    assert result.internal_model["graph"]["edges"][0]["valid"] is False
    assert result.internal_model["validation"]["dangling_edge_count"] == 1
    assert result.report["errors"] == ["dangling_edge:dangling:start->missing"]
    assert result.report["lossless"] is False


def test_parse_workflow_reports_entry_and_exit_boundary_edges() -> None:
    payload = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "answer", "type": "answer"},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"id": "back-to-start", "source": "answer", "target": "start"},
                {"id": "end-out", "source": "end", "target": "answer"},
            ],
        }
    }

    result = parse_workflow(payload, name="Boundary")

    assert [edge["valid"] for edge in result.internal_model["graph"]["edges"]] == [
        False,
        False,
    ]
    assert result.internal_model["validation"]["dangling_edge_count"] == 0
    assert result.internal_model["validation"]["boundary_edge_count"] == 2
    assert result.internal_model["validation"]["runnable"] is False
    assert result.report["errors"] == [
        "boundary_edge_targets_entry:back-to-start:answer->start",
        "boundary_edge_starts_from_exit:end-out:end->answer",
    ]
    assert result.report["lossless"] is False
