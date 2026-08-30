"""pricing 分布式支持测试：缓存 TTL 自愈、跨实例失效广播、同步/回填分布式锁。"""

import asyncio

import pytest

from src.infra.pricing import backfill as pricing_backfill
from src.infra.pricing import pubsub as pricing_pubsub
from src.infra.pricing import service as pricing_service
from src.infra.pricing import sync as pricing_sync
from src.infra.pricing.storage import PricingStorage


class _FakePricingCollection:
    def __init__(self, entries=None, fx=None):
        self.docs = {}
        if entries is not None:
            self.docs["models_dev_snapshot"] = {
                "entries": entries,
                "entry_count": len(entries),
                "model_owners": {},
                "source_url": "u",
                "synced_at": "2026-08-30T00:00:00",
            }
        if fx is not None:
            self.docs["fx_rates"] = fx

    async def update_one(self, query, update, **kwargs):
        doc = dict(update.get("$set", {}))
        doc["_id"] = query["_id"]
        self.docs[query["_id"]] = doc
        return None

    async def find_one(self, query, *args, **kwargs):
        doc = self.docs.get(query.get("_id"))
        return None if doc is None else {k: v for k, v in doc.items() if k != "_id"}

    async def create_index(self, *a, **kw):
        return None


def _storage_with(entries=None, fx=None):
    return PricingStorage(collection=_FakePricingCollection(entries=entries, fx=fx))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(pricing_service, "get_pricing_storage", lambda: _storage_with())
    pricing_service.reset_runtime_cache()
    yield
    pricing_service.reset_runtime_cache()


class TestRuntimeCacheTtl:
    def test_cache_expires_after_ttl(self, monkeypatch):
        """其他副本改了 Mongo 后，本地缓存到期要能重新加载（自愈兜底）。"""
        storage = _storage_with(
            entries=[
                {
                    "provider": "p",
                    "model_id": "m",
                    "name": "",
                    "rates": {"input": 1, "output": 2, "cache_read": None, "cache_write": None},
                }
            ]
        )
        monkeypatch.setattr(pricing_service, "get_pricing_storage", lambda: storage)

        async def run():
            idx1 = await pricing_service.get_price_index()
            # 模拟另一副本写入新快照
            storage.collection.docs["models_dev_snapshot"]["entries"] = []
            # TTL 内仍用本地缓存
            idx2 = await pricing_service.get_price_index()
            assert idx2 is idx1
            # 快进 TTL
            pricing_service._advance_cache_clock(pricing_service.CACHE_TTL_SECONDS + 1)
            idx3 = await pricing_service.get_price_index()
            assert idx3 is not idx1
            assert idx3.entry_count == 0

        asyncio.run(run())

    def test_fx_cache_expires_after_ttl(self, monkeypatch):
        storage = _storage_with(fx={"base": "USD", "rates": {"CNY": 7.1}, "rate_count": 1})
        monkeypatch.setattr(pricing_service, "get_pricing_storage", lambda: storage)

        async def run():
            doc1 = await pricing_service.get_fx_rates()
            storage.collection.docs.pop("fx_rates")
            pricing_service._advance_cache_clock(pricing_service.CACHE_TTL_SECONDS + 1)
            doc2 = await pricing_service.get_fx_rates()
            assert doc2 is None and doc1 is not None

        asyncio.run(run())


class TestPricingPubSub:
    def test_incoming_message_resets_runtime_cache(self):
        pub = pricing_pubsub.PricingPubSub()
        pricing_service._runtime_index = object()  # 模拟已有缓存
        asyncio.run(pub._handle_message({"data": '{"instance_id": "other"}'}))
        assert pricing_service._runtime_index is None

    def test_self_message_is_ignored(self):
        pub = pricing_pubsub.PricingPubSub()
        sentinel = object()
        pricing_service._runtime_index = sentinel
        asyncio.run(pub._handle_message({"data": f'{{"instance_id": "{pub.instance_id}"}}'}))
        assert pricing_service._runtime_index is sentinel

    def test_publish_is_best_effort(self, monkeypatch):
        """Redis 挂了不能影响主流程。"""

        class _BoomRedis:
            async def publish(self, *a, **kw):
                raise RuntimeError("redis down")

        import src.infra.storage.redis as redis_module

        monkeypatch.setattr(redis_module, "get_redis_client", lambda: _BoomRedis())
        asyncio.run(pricing_pubsub.publish_pricing_cache_invalidate())  # 不应抛异常


class TestSyncDistributedLock:
    def test_lock_held_by_other_replica_skips_fetch(self, monkeypatch):
        storage = _storage_with()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        async def _contended(lock_key, ttl):
            return None

        async def _release(lock_key, token):
            return None

        monkeypatch.setattr(pricing_sync, "acquire_pricing_lock", _contended)
        monkeypatch.setattr(pricing_sync, "release_pricing_lock", _release)

        def handler(request):
            raise AssertionError("另一副本持锁时不应发起网络同步")

        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _noop_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        assert status["refreshed"] is False
        assert status["lock_contended"] is True

    def test_redis_failure_falls_back_to_sync(self, monkeypatch):
        """单机/Redis 不可用时不能因锁而中断同步。"""
        storage = _storage_with()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        async def _boom(lock_key, ttl):
            raise RuntimeError("redis down")

        async def _release(lock_key, token):
            return None

        monkeypatch.setattr(pricing_sync, "acquire_pricing_lock", _boom)
        monkeypatch.setattr(pricing_sync, "release_pricing_lock", _release)

        def handler(request):
            import httpx

            if "models.dev" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "openai": {
                            "id": "openai",
                            "models": {"gpt-4o": {"cost": {"input": 2.5, "output": 10}}},
                        }
                    },
                )
            return httpx.Response(
                200,
                json={"result": "success", "base_code": "USD", "rates": {"USD": 1}},
            )

        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _noop_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        assert status["refreshed"] is True
        assert status["lock_contended"] is False


class TestBackfillDistributedLock:
    def test_lock_contended_returns_flag(self, monkeypatch):
        async def _contended(lock_key, ttl):
            return None

        async def _release(lock_key, token):
            return None

        monkeypatch.setattr(pricing_backfill, "acquire_pricing_lock", _contended)
        monkeypatch.setattr(pricing_backfill, "release_pricing_lock", _release)
        summary = asyncio.run(pricing_backfill.backfill_usage_costs())
        assert summary.get("lock_contended") is True
        assert summary["scanned"] == 0

    def test_publishes_and_resets_cache_after_successful_sync(self, monkeypatch):
        """写入成功后要清本副本缓存并广播其他副本。"""
        storage = _storage_with()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        async def _acquire(lock_key, ttl):
            return "tok"

        async def _release(lock_key, token):
            return None

        monkeypatch.setattr(pricing_sync, "acquire_pricing_lock", _acquire)
        monkeypatch.setattr(pricing_sync, "release_pricing_lock", _release)

        published = []

        async def _fake_publish():
            published.append(True)

        import src.infra.pricing.pubsub as pubsub_module

        monkeypatch.setattr(pubsub_module, "publish_pricing_cache_invalidate", _fake_publish)
        pricing_service._runtime_index = object()  # 预置脏缓存

        def handler(request):
            import httpx

            if "models.dev" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "openai": {
                            "id": "openai",
                            "models": {"gpt-4o": {"cost": {"input": 2.5, "output": 10}}},
                        }
                    },
                )
            return httpx.Response(
                200,
                json={"result": "success", "base_code": "USD", "rates": {"USD": 1}},
            )

        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _noop_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        assert status["refreshed"] is True
        assert published == [True]
        assert pricing_service._runtime_index is None


def _noop_client(handler):
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
