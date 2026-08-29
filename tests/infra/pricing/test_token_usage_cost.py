"""token:usage 事件金额集成测试：presenter 事件字段 + processor 计算 + usage_logs 落库。"""

import asyncio
from types import SimpleNamespace

from src.infra.pricing.calculator import CostBreakdown, PriceRates
from src.infra.writer.present import create_presenter


def _breakdown() -> CostBreakdown:
    return CostBreakdown(
        input_usd=0.008, output_usd=0.015, cache_read_usd=0.0006, cache_write_usd=0.001
    )


class TestPresentTokenUsageCost:
    def test_cost_fields_included_when_priced(self):
        presenter = create_presenter(session_id="s1", agent_id="a", agent_name="A")
        event = presenter.present_token_usage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            duration=1.0,
            model_id="model-1",
            model="openai/gpt-4o",
            cost=_breakdown(),
            rates=PriceRates(input=2.5, output=10, cache_read=1.25),
        )
        data = event["data"]
        assert data["cost_usd"] == _breakdown().total_usd
        assert data["cost_breakdown"]["input"] == 0.008
        assert data["cost_breakdown"]["total"] == _breakdown().total_usd
        assert data["cost_rates"]["input"] == 2.5
        assert data["cost_rates"]["cache_read"] == 1.25
        assert data["cost_rates"]["cache_write"] is None

    def test_cost_fields_absent_when_unpriced(self):
        presenter = create_presenter(session_id="s1", agent_id="a", agent_name="A")
        event = presenter.present_token_usage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            duration=1.0,
        )
        assert "cost_usd" not in event["data"]
        assert "cost_breakdown" not in event["data"]
        assert "cost_rates" not in event["data"]


class TestProcessorEmitsCost:
    def _make_processor(self):
        from src.infra.agent.events.processor import AgentEventProcessor

        processor = AgentEventProcessor.__new__(AgentEventProcessor)
        processor.total_input_tokens = 1_000_000
        processor.total_output_tokens = 100_000
        processor.total_tokens = 1_100_000
        processor.total_cache_creation_tokens = 0
        processor.total_cache_read_tokens = 200_000
        processor._token_usage_emitted = False

        captured: dict = {}

        class _FakePresenter:
            def present_token_usage(self, **kwargs):
                captured.update(kwargs)
                return {"event": "token:usage", "data": dict(kwargs)}

        async def _emit(event):
            captured["emitted"] = event

        processor.presenter = _FakePresenter()
        processor._presenter_emit = _emit
        return processor, captured

    def test_computes_cost_via_pricing_service(self, monkeypatch):
        from src.infra.agent.events import processor as processor_module

        processor, captured = self._make_processor()

        async def _fake_compute(**kwargs):
            assert kwargs["model_value"] == "openai/gpt-4o"
            assert kwargs["model_config_id"] == "model-1"
            assert kwargs["input_tokens"] == 1_000_000
            assert kwargs["cache_read_tokens"] == 200_000
            return _breakdown(), PriceRates(input=2.5, output=10), "models_dev"

        monkeypatch.setattr(processor_module, "compute_usage_cost", _fake_compute)
        emitted = asyncio.run(
            processor.emit_token_usage(duration=2.0, model_id="model-1", model="openai/gpt-4o")
        )
        assert emitted is True
        assert captured["cost"] == _breakdown()
        assert captured["rates"].input == 2.5

    def test_pricing_failure_does_not_break_event(self, monkeypatch):
        from src.infra.agent.events import processor as processor_module

        processor, captured = self._make_processor()

        async def _boom(**kwargs):
            raise RuntimeError("pricing down")

        monkeypatch.setattr(processor_module, "compute_usage_cost", _boom)
        emitted = asyncio.run(
            processor.emit_token_usage(duration=2.0, model_id="model-1", model="openai/gpt-4o")
        )
        assert emitted is True
        assert "cost" not in captured or captured.get("cost") is None


class TestUsageLogCost:
    def _storage(self):
        from src.infra.usage.storage import UsageStorage

        class _FakeCollection:
            def __init__(self):
                self.saved: dict = {}

            async def update_one(self, query, update, **kwargs):
                self.saved.update(update["$set"])
                return SimpleNamespace(modified_count=1)

            async def create_index(self, *a, **kw):
                return None

        storage = UsageStorage()
        fake = _FakeCollection()
        storage._collection = fake

        async def _no_metadata(_session_id):
            return {}

        storage._get_session_metadata = _no_metadata
        return storage, fake

    def test_persists_cost_usd(self):
        storage, fake = self._storage()
        ok = asyncio.run(
            storage.upsert_usage_log_from_trace_metadata(
                {
                    "trace_id": "t1",
                    "session_id": "s1",
                    "user_id": "u1",
                    "status": "completed",
                },
                {
                    "model": "gpt-4o",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "total_tokens": 1500,
                    "cost_usd": 0.0246,
                    "cost_breakdown": {"total": 0.0246},
                },
            )
        )
        assert ok is True
        assert fake.saved["cost_usd"] == 0.0246
        assert fake.saved["cost_available"] is True

    def test_unpriced_logs_cost_zero_and_unavailable(self):
        storage, fake = self._storage()
        asyncio.run(
            storage.upsert_usage_log_from_trace_metadata(
                {
                    "trace_id": "t2",
                    "session_id": "s1",
                    "user_id": "u1",
                    "status": "completed",
                },
                {"model": "mystery", "input_tokens": 10, "output_tokens": 5},
            )
        )
        assert fake.saved["cost_usd"] == 0.0
        assert fake.saved["cost_available"] is False
