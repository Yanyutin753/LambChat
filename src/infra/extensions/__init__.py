"""Infrastructure adapters for Extension and Plugin Runtime state."""

from src.infra.extensions.plugin_data import PluginDataService, PluginDataSnapshot
from src.infra.extensions.plugin_package_import import (
    PluginPackageImportResult,
    PluginPackageImportService,
)
from src.infra.extensions.plugin_package_integrity import (
    PluginPackageIntegrity,
    build_package_integrity,
)
from src.infra.extensions.plugin_package_lifecycle import (
    ArchivedPluginPackage,
    PluginPackageLifecycleService,
    PluginPackageRestoreResult,
    PluginPackageUninstallResult,
)
from src.infra.extensions.plugin_settings import (
    MASKED_SECRET_VALUE,
    InMemoryPluginSettingsStorage,
    MongoPluginSettingsStorage,
    PluginSettingRecord,
    PluginSettingsResolver,
    PluginSettingsService,
    get_plugin_settings_service,
    get_plugin_settings_storage,
    plugin_owned_system_setting_keys,
)
from src.infra.extensions.runtime_state_storage import (
    InMemoryPluginRuntimeStateStorage,
    MongoPluginRuntimeStateStorage,
    PluginPackageReviewRecord,
    PluginRuntimeAuditRecord,
    PluginRuntimeStateOverride,
    get_plugin_runtime_state_storage,
)

__all__ = [
    "InMemoryPluginRuntimeStateStorage",
    "InMemoryPluginSettingsStorage",
    "MASKED_SECRET_VALUE",
    "MongoPluginRuntimeStateStorage",
    "MongoPluginSettingsStorage",
    "PluginSettingRecord",
    "PluginDataService",
    "PluginDataSnapshot",
    "PluginPackageImportResult",
    "PluginPackageImportService",
    "PluginPackageIntegrity",
    "PluginPackageLifecycleService",
    "PluginPackageUninstallResult",
    "PluginSettingsResolver",
    "PluginSettingsService",
    "ArchivedPluginPackage",
    "PluginPackageRestoreResult",
    "PluginPackageReviewRecord",
    "PluginRuntimeAuditRecord",
    "PluginRuntimeStateOverride",
    "get_plugin_settings_service",
    "get_plugin_settings_storage",
    "get_plugin_runtime_state_storage",
    "build_package_integrity",
    "plugin_owned_system_setting_keys",
]
