from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from src.api import deps
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("failure", [ErrorCode.INVALID_TOKEN, ErrorCode.INTERNAL_ERROR])
async def test_revoked_stream_stops_before_delivering_more_data_and_closes_source(
    monkeypatch, failure
):
    closed = []
    clock = iter([0, 1, 16])
    monkeypatch.setattr(deps, "monotonic", lambda: next(clock))
    monkeypatch.setattr(deps, "_load_user_payload", AsyncMock(side_effect=AppError(failure)))

    async def source():
        try:
            yield "first"
            yield "secret after revocation"
        finally:
            closed.append(True)

    result = [
        chunk
        async for chunk in deps.guard_authenticated_stream(
            source(), TokenPayload(sub="u", username="a")
        )
    ]
    assert result[0] == "first"
    assert len(result) == 2 and "event: error" in result[1]
    assert "secret after revocation" not in "".join(result)
    assert closed == [True]


async def test_stream_stops_at_access_token_expiration(monkeypatch):
    async def source():
        yield "secret"

    user = TokenPayload(sub="u", username="a", exp=utc_now() - timedelta(seconds=1))
    result = [chunk async for chunk in deps.guard_authenticated_stream(source(), user)]
    assert len(result) == 1 and "token_expired" in result[0]
