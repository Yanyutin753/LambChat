from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts"


def test_workflow_stream_helper_retries_once_after_unauthorized_response() -> None:
    source = API_SOURCE.read_text(encoding="utf-8")

    assert "refreshAccessToken" in source
    assert "redirectToLogin" in source
    assert "response.status === 401 && !hasRetried" in source
    assert "return streamWorkflowRunEvents(workflowId, runId, handlers, options, true)" in source
    assert "response.status === 401" in source
    assert "Workflow event stream unauthorized" in source
    assert "getValidAccessToken" in source
    assert "Authorization" in source


def test_workflow_stream_helper_preserves_structured_backend_error_codes() -> None:
    source = API_SOURCE.read_text(encoding="utf-8")

    assert "await workflowStreamErrorMessage(response)" in source
    assert "async function workflowStreamErrorMessage(response: Response)" in source
    assert 'const fallback = `Workflow event stream failed: ${response.status}`' in source
    assert "await response.json().catch(() => null)" in source
    assert '"detail" in payload' in source
    assert '"error" in detail' in source
    assert '"error" in payload' in source
