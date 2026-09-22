from __future__ import annotations

import pytest

from src.infra.email import service as email_service_module
from src.infra.email.service import EmailService
from src.kernel.config import settings


def test_parse_accounts_clamps_configured_accounts(monkeypatch) -> None:
    accounts = [
        {
            "api_key": f"re_key_{index}",
            "email_from": f"noreply-{index}@example.com",
            "email_from_name": "LambChat",
        }
        for index in range(email_service_module.RESEND_ACCOUNTS_MAX + 5)
    ]
    monkeypatch.setattr(settings, "RESEND_ACCOUNTS", accounts, raising=False)

    parsed = EmailService()._parse_accounts()

    assert len(parsed) == email_service_module.RESEND_ACCOUNTS_MAX
    assert parsed[-1]["api_key"] == f"re_key_{email_service_module.RESEND_ACCOUNTS_MAX - 1}"


@pytest.mark.asyncio
async def test_get_accounts_offloads_account_json_parsing(monkeypatch) -> None:
    inside_blocking_io = False
    monkeypatch.setattr(
        settings,
        "RESEND_ACCOUNTS",
        '[{"api_key":"re_key_1","email_from":"noreply@example.com"}]',
        raising=False,
    )

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    def fake_json_loads(value):
        assert inside_blocking_io, "RESEND_ACCOUNTS JSON parsing must be offloaded"
        assert isinstance(value, str)
        return [{"api_key": "re_key_1", "email_from": "noreply@example.com"}]

    monkeypatch.setattr(
        email_service_module, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )
    monkeypatch.setattr(email_service_module.json, "loads", fake_json_loads)

    accounts = await EmailService()._get_accounts()

    assert accounts == [
        {
            "api_key": "re_key_1",
            "email_from": "noreply@example.com",
            "email_from_name": "LambChat",
        }
    ]


@pytest.mark.asyncio
async def test_close_email_service_closes_existing_singleton_without_creating_one() -> None:
    class _FakeHttpClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    EmailService._instance = None

    await email_service_module.close_email_service()

    assert EmailService._instance is None

    service = EmailService()
    http_client = _FakeHttpClient()
    service._http_client = http_client
    EmailService._instance = service

    await email_service_module.close_email_service()

    assert http_client.close_calls == 1
    assert service._http_client is None
    assert EmailService._instance is None
