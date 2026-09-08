"""hitl_resume 载荷携带 run 用量锚点（issue：审批恢复后只记最后一段）。

build_hitl_resume_payload 从审批 metadata.resume_context 还原
run_started_at / prior_usage，恢复执行据此累计 token 与工作时长。
"""

from types import SimpleNamespace

from src.infra.task.hitl import build_hitl_resume_payload


def _approval(resume_context: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        id="ap1",
        message="确认执行",
        metadata={
            "run_id": "run_20260908134828_3cf0b70a",
            "trace_id": "trace_1",
            "interrupt_id": "i1",
            "tool_call_id": "tc1",
            "resume_context": resume_context or {},
        },
    )


def test_payload_carries_run_anchor_and_prior_usage():
    prior = {"input_tokens": 23478, "output_tokens": 1019, "total_tokens": 24497}
    payload = build_hitl_resume_payload(
        _approval({"run_started_at": 1757336908.8, "prior_usage": prior}),
        {"approved": True},
    )

    assert payload["run_started_at"] == 1757336908.8
    assert payload["prior_usage"] == prior
    # 既有字段保持不变
    assert payload["approval_id"] == "ap1"
    assert payload["resume_value"] == {"i1": {"approved": True}}
    assert payload["approval_resolved"]["status"] == "approved"


def test_payload_without_resume_context_keeps_none_carry():
    payload = build_hitl_resume_payload(_approval(None), {"approved": False})

    assert payload["run_started_at"] is None
    assert payload["prior_usage"] is None
    assert payload["goal_started_at"] is None
    assert payload["approval_resolved"]["status"] == "rejected"
