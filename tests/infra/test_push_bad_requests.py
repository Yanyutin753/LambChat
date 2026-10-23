from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.push.storage import PushSubscriptionStorage
from src.kernel.schemas.push_subscription import PushSubscription


async def test_repeated_bad_request_retires_only_the_same_subscription_version():
    storage = PushSubscriptionStorage()
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(
            side_effect=[{"bad_request_count": 1}, {"bad_request_count": 2}, None]
        ),
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
    )
    storage._collection = collection
    sub = PushSubscription(
        id="id",
        user_id="owner",
        endpoint="https://push/secret",
        keys={"p256dh": "key", "auth": "auth"},
        created_at=datetime(2026, 10, 23),
    )
    assert await storage.record_bad_request(sub) is False
    collection.delete_one.assert_not_awaited()
    assert await storage.record_bad_request(sub) is True
    query = collection.delete_one.call_args.args[0]
    assert query["user_id"] == "owner" and query["keys"] == sub.keys.model_dump()
    assert query["created_at"] == sub.created_at
    assert query["bad_request_count"] == {"$gte": 2}
    assert await storage.record_bad_request(sub) is False
    assert collection.delete_one.await_count == 1


async def test_subscription_status_is_scoped_to_the_current_user():
    storage = PushSubscriptionStorage()
    collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
    storage._collection = collection
    assert await storage.has_subscription("owner", "https://push/secret") is False
    assert collection.find_one.call_args.args[0] == {
        "user_id": "owner",
        "endpoint": "https://push/secret",
    }


async def test_push_manager_records_400_without_immediate_unscoped_deletion(monkeypatch):
    import pywebpush
    from pywebpush import WebPushException
    from requests import Response

    from src.infra.push import manager as module

    sub = PushSubscription(
        id="id",
        user_id="owner",
        endpoint="https://push/secret",
        keys={"p256dh": "key", "auth": "auth"},
        created_at=datetime(2026, 10, 23),
    )
    manager = module.PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[sub])
    manager.storage.record_bad_request = AsyncMock(return_value=False)
    manager.storage.delete_by_endpoint = AsyncMock()
    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            VAPID_PUBLIC_KEY="test",
            VAPID_PRIVATE_KEY="test",
            VAPID_SUBJECT="mailto:test@example.test",
        ),
    )

    def bad_request(**kwargs):
        response = Response()
        response.status_code = 400
        raise WebPushException("bad subscription", response=response)

    monkeypatch.setattr(pywebpush, "webpush", bad_request)
    assert await manager.send_push_to_user("owner", {"title": "test"}) == 0
    manager.storage.record_bad_request.assert_awaited_once_with(sub)
    manager.storage.delete_by_endpoint.assert_not_awaited()
