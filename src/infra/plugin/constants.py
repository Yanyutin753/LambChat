"""插件中心 MongoDB 集合与限额常量。"""

PLUGIN_COLLECTION = "plugins"
PLUGIN_FILES_COLLECTION = "plugin_files"
PLUGIN_INSTALLS_COLLECTION = "plugin_installs"

# 单插件技能文件数上限（与 skill marketplace 对齐）
PLUGIN_FILES_PER_SKILL_LIMIT = 100
# 单技能文件大小上限（512KB，与 skill 路由对齐）
PLUGIN_FILE_MAX_CHARS = 512 * 1024
# 列表/扫描上限
PLUGIN_LIST_LIMIT = 50
PLUGIN_TAG_SCAN_LIMIT = 1000
PLUGIN_TAG_LIST_LIMIT = 200
# 迁移扫描上限（与 legacy skill 迁移对齐）
PLUGIN_MIGRATION_SCAN_LIMIT = 500
