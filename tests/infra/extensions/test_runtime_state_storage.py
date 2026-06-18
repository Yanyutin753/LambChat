import pytest

from src.infra.extensions import InMemoryPluginRuntimeStateStorage
from src.kernel.extensions import PluginRuntimeStatus


@pytest.mark.asyncio
async def test_in_memory_plugin_runtime_state_storage_tracks_overrides_and_audit() -> None:
    storage = InMemoryPluginRuntimeStateStorage()

    override = await storage.set_override(
        plugin_id="feedback",
        status=PluginRuntimeStatus.DISABLED,
        updated_by="admin-1",
        reason="maintenance",
    )
    await storage.append_audit(
        plugin_id="feedback",
        action="disable",
        previous_status=PluginRuntimeStatus.ENABLED,
        next_status=PluginRuntimeStatus.DISABLED,
        actor_user_id="admin-1",
        actor_username="admin",
        reason="maintenance",
    )

    assert override.plugin_id == "feedback"
    assert override.status is PluginRuntimeStatus.DISABLED
    assert override.updated_by == "admin-1"
    assert await storage.get_override("feedback") == override
    assert await storage.list_overrides() == [override]

    audit = await storage.list_audit(plugin_id="feedback")
    assert len(audit) == 1
    assert audit[0].action == "disable"
    assert audit[0].previous_status is PluginRuntimeStatus.ENABLED
    assert audit[0].next_status is PluginRuntimeStatus.DISABLED
