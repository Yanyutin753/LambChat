from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from src.infra.channel import pubsub as channel_pubsub
from src.infra.llm import pubsub as llm_pubsub
from src.infra.memory import distributed as memory_distributed
from src.infra.settings import pubsub as settings_pubsub
from src.infra.settings.service import SettingsService
from src.infra.task.constants import MODEL_CONFIG_CHANNEL, SETTINGS_CHANNEL
from src.infra.tool import cache_pubsub, mcp_global
from src.kernel.extensions import PluginManifest, PluginRuntime


class _FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "pubsub_cls"),
    [
        (llm_pubsub, llm_pubsub.ModelConfigPubSub),
        (settings_pubsub, settings_pubsub.SettingsPubSub),
        (channel_pubsub, channel_pubsub.ChannelConfigPubSub),
        (cache_pubsub, cache_pubsub.ToolCachePubSub),
        (mcp_global, mcp_global.MCPGlobalCachePubSub),
    ],
)
async def test_pubsub_handlers_offload_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    pubsub_cls: Callable[[], Any],
) -> None:
    calls: list[Callable[..., Any]] = []

    async def fake_run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(module, "run_blocking_io", fake_run_blocking_io)

    pubsub = pubsub_cls()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message({"data": json.dumps({"instance_id": "instance-a"})})

    assert calls == [json.loads]


@pytest.mark.asyncio
async def test_memory_pubsub_offloads_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Callable[..., Any]] = []

    async def fake_run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(memory_distributed, "run_blocking_io", fake_run_blocking_io)

    pubsub = memory_distributed.MemoryPubSub()

    await pubsub._handle_message({"data": json.dumps({})})

    assert calls == [json.loads]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "publish_func", "channel", "kwargs"),
    [
        (llm_pubsub, llm_pubsub.publish_model_config_changed, MODEL_CONFIG_CHANNEL, {}),
        (
            channel_pubsub,
            channel_pubsub.publish_channel_config_changed,
            channel_pubsub.CHANNEL_CONFIG_CHANNEL,
            {
                "user_id": "user-1",
                "channel_type": "feishu",
                "channel_instance_id": "chan-1",
                "action": "updated",
            },
        ),
        (
            cache_pubsub,
            cache_pubsub.publish_tool_cache_invalidation,
            cache_pubsub.TOOL_CACHE_INVALIDATION_CHANNEL,
            {"cache": "env_var_prompt", "user_id": "user-1"},
        ),
        (
            memory_distributed,
            memory_distributed.publish_memory_invalidation,
            memory_distributed.MEMORY_INVALIDATION_CHANNEL,
            {"user_id": "user-1"},
        ),
        (
            mcp_global,
            mcp_global.invalidate_global_cache,
            mcp_global.MCP_CACHE_INVALIDATE_CHANNEL,
            {"user_id": "user-1"},
        ),
    ],
)
async def test_pubsub_publishers_offload_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    publish_func: Callable[..., Any],
    channel: str,
    kwargs: dict[str, Any],
) -> None:
    calls: list[Callable[..., Any]] = []
    fake_redis = _FakeRedisClient()

    async def fake_run_blocking_io(func: Callable[..., Any], *args: Any, **call_kwargs: Any) -> Any:
        calls.append(func)
        return func(*args, **call_kwargs)

    monkeypatch.setattr(module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(module, "get_redis_client", lambda: fake_redis)

    if module is llm_pubsub:
        pubsub = llm_pubsub.ModelConfigPubSub()
        pubsub._instance_id = "instance-a"
        monkeypatch.setattr(llm_pubsub, "get_model_config_pubsub", lambda: pubsub)
        await publish_func()
    elif module is channel_pubsub:
        pubsub = channel_pubsub.ChannelConfigPubSub()
        pubsub._instance_id = "instance-a"
        monkeypatch.setattr(channel_pubsub, "get_channel_config_pubsub", lambda: pubsub)
        await publish_func(**kwargs)
    elif module is cache_pubsub:
        pubsub = cache_pubsub.ToolCachePubSub()
        pubsub._instance_id = "instance-a"
        monkeypatch.setattr(cache_pubsub, "get_tool_cache_pubsub", lambda: pubsub)
        await publish_func(kwargs["cache"], user_id=kwargs["user_id"])
    elif module is mcp_global:
        pubsub = mcp_global.MCPGlobalCachePubSub()
        pubsub._instance_id = "instance-a"
        monkeypatch.setattr(mcp_global, "get_mcp_cache_pubsub", lambda: pubsub)
        await publish_func(kwargs["user_id"])
    else:
        await publish_func(kwargs["user_id"])

    assert calls == [json.dumps]
    assert fake_redis.published[0][0] == channel


@pytest.mark.asyncio
async def test_settings_service_publish_change_offloads_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Callable[..., Any]] = []
    fake_redis = _FakeRedisClient()

    async def fake_run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        calls.append(func)
        return func(*args, **kwargs)

    class _FakeSettingsPubSub:
        instance_id = "instance-a"

    monkeypatch.setattr("src.infra.settings.service.run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "src.infra.settings.pubsub.get_settings_pubsub",
        lambda: _FakeSettingsPubSub(),
    )

    await SettingsService._publish_change("APP_NAME", "LambChat")

    assert calls == [json.dumps]
    assert fake_redis.published[0][0] == SETTINGS_CHANNEL


@pytest.mark.asyncio
async def test_channel_pubsub_uses_manifest_declared_connector_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    class _FakeManager:
        @classmethod
        def get_instance(cls):
            return cls()

        async def reload_user(self, user_id: str, instance_id: str | None = None) -> None:
            calls.append((user_id, instance_id))

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="alternate_feishu_connector",
                name="Alternate Feishu Connector",
                version="1.0.0",
                api_version="v1",
                frontend={
                    "channel_connectors": [
                        {
                            "id": "alternate_feishu_connector:feishu",
                            "channel_type": "feishu",
                        }
                    ]
                },
            )
        ]
    )
    runtime.disable_plugin("alternate_feishu_connector")

    monkeypatch.setattr(
        channel_pubsub.get_registry(),
        "get_manager_class",
        lambda channel_type: _FakeManager,
    )
    pubsub = channel_pubsub.ChannelConfigPubSub()
    pubsub._instance_id = "instance-a"
    pubsub.set_plugin_runtime(runtime)

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "user_id": "user-1",
                    "channel_type": "feishu",
                    "channel_instance_id": "bot-1",
                }
            )
        }
    )

    assert calls == []
