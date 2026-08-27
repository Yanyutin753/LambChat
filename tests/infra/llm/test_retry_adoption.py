from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/api/routes/session.py",
        "src/agents/core/recommendations.py",
        "src/infra/agent/middleware/main_agent_context.py",
        "src/infra/agent/middleware/subagent_activity.py",
        "src/infra/memory/client/native/backend.py",
        "src/infra/memory/client/native/summaries.py",
    ],
)
def test_direct_model_calls_use_shared_retry_helper(relative_path: str) -> None:
    source = Path(relative_path).read_text()

    assert "ainvoke_with_retry(" in source
    assert ".ainvoke(" not in source
