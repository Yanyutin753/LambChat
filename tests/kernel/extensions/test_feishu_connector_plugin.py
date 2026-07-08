from src.kernel.extensions import (
    FEISHU_CONNECTOR_ID,
    FEISHU_CONNECTOR_PLUGIN_ID,
    PluginDryRunAction,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_feishu_connector_plugin_manifest,
    build_uninstall_dry_run,
)


def test_feishu_connector_manifest_declares_channel_connector() -> None:
    manifest = build_feishu_connector_plugin_manifest()

    assert manifest.id == FEISHU_CONNECTOR_PLUGIN_ID
    assert manifest.name == "Feishu Connector"
    assert [connector.id for connector in manifest.frontend.channel_connectors] == [
        FEISHU_CONNECTOR_ID
    ]
    assert manifest.frontend.channel_connectors[0].channel_type == "feishu"
    assert manifest.frontend.channel_connectors[0].panel_renderer == (
        "feishu_connector.FeishuPanel"
    )
    assert [(effect.action, effect.effect) for effect in manifest.runtime_effects] == [
        ("enable", "start_feishu_connector"),
        ("disable", "stop_feishu_connector"),
    ]
    assert manifest.enabled_by_default is True
    assert manifest.core is False


def test_feishu_connector_runtime_guards_connector_state() -> None:
    runtime = PluginRuntime([build_feishu_connector_plugin_manifest()])
    state = runtime.get_state(FEISHU_CONNECTOR_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.ENABLED
    assert [record.resource_id for record in runtime.channel_connectors()] == [
        FEISHU_CONNECTOR_ID
    ]
    assert runtime.ensure_channel_connector_available(FEISHU_CONNECTOR_ID).plugin_id == (
        FEISHU_CONNECTOR_PLUGIN_ID
    )

    runtime.disable_plugin(FEISHU_CONNECTOR_PLUGIN_ID)

    assert runtime.channel_connectors() == []


def test_feishu_connector_resources_and_dry_run_are_non_destructive() -> None:
    runtime = PluginRuntime([build_feishu_connector_plugin_manifest()])
    resources = runtime.resource_ledger.list(plugin_id=FEISHU_CONNECTOR_PLUGIN_ID)
    resource_keys = {(resource.resource_type, resource.resource_id) for resource in resources}

    assert (PluginResourceType.CHANNEL_CONNECTOR, FEISHU_CONNECTOR_ID) in resource_keys
    assert (
        PluginResourceType.DB_DOCUMENT,
        "user_channel_configs.feishu",
    ) in resource_keys
    assert (PluginResourceType.LISTENER, "feishu_connector:channel-config-change-listener") in resource_keys

    dry_run = build_uninstall_dry_run(
        plugin_id=FEISHU_CONNECTOR_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    actions_by_id = {resource.resource_id: resource.action for resource in dry_run.resources}

    assert actions_by_id[FEISHU_CONNECTOR_ID] is PluginDryRunAction.KEEP
    assert actions_by_id["user_channel_configs.feishu"] is PluginDryRunAction.KEEP
    assert actions_by_id["feishu_connector:channel-config-change-listener"] is (
        PluginDryRunAction.MANUAL_REVIEW
    )
    assert actions_by_id["revealed-files/feishu-delivery"] is (
        PluginDryRunAction.FORBID_DELETE
    )
