"""
权限相关的 Pydantic 模型
"""

from typing import TypedDict

from pydantic import BaseModel

from src.kernel.types import Permission


class PermissionInfo(BaseModel):
    """单个权限信息"""

    value: str
    label: str
    description: str = ""


class PermissionGroup(BaseModel):
    """权限分组"""

    name: str
    permissions: list[PermissionInfo]


class PermissionsResponse(BaseModel):
    """权限列表响应"""

    groups: list[PermissionGroup]
    all_permissions: list[PermissionInfo]


class PermissionGroupConfig(TypedDict):
    """权限分组配置"""

    name: str
    permissions: list[str]


# 权限元数据配置
PERMISSION_METADATA: dict[str, dict[str, str]] = {
    # Chat
    Permission.CHAT_READ.value: {
        "label": "读取聊天",
        "description": "查看聊天消息",
    },
    Permission.CHAT_WRITE.value: {
        "label": "发送消息",
        "description": "发送聊天消息",
    },
    # Session
    Permission.SESSION_READ.value: {
        "label": "读取会话",
        "description": "查看会话列表和内容",
    },
    Permission.SESSION_WRITE.value: {
        "label": "创建/更新会话",
        "description": "创建和修改会话",
    },
    Permission.SESSION_DELETE.value: {
        "label": "删除会话",
        "description": "删除会话",
    },
    Permission.SESSION_ADMIN.value: {
        "label": "管理所有会话",
        "description": "查看和管理所有用户的会话（管理员权限）",
    },
    Permission.SESSION_SHARE.value: {
        "label": "分享会话",
        "description": "创建和管理会话分享链接",
    },
    # Skill
    Permission.SKILL_READ.value: {
        "label": "读取技能",
        "description": "查看技能列表和内容",
    },
    Permission.SKILL_WRITE.value: {
        "label": "创建/更新技能",
        "description": "创建和修改技能",
    },
    Permission.SKILL_DELETE.value: {
        "label": "删除技能",
        "description": "删除技能",
    },
    Permission.SKILL_ADMIN.value: {
        "label": "管理技能",
        "description": "管理技能的完整权限",
    },
    # User
    Permission.USER_READ.value: {
        "label": "读取用户",
        "description": "查看用户列表和信息",
    },
    Permission.USER_WRITE.value: {
        "label": "创建/更新用户",
        "description": "创建和修改用户",
    },
    Permission.USER_DELETE.value: {
        "label": "删除用户",
        "description": "删除用户",
    },
    # Role
    Permission.ROLE_MANAGE.value: {
        "label": "管理角色",
        "description": "管理角色和权限分配",
    },
    # Settings
    Permission.SETTINGS_MANAGE.value: {
        "label": "管理系统设置",
        "description": "修改系统配置",
    },
    # MCP
    Permission.MCP_READ.value: {
        "label": "读取MCP配置",
        "description": "查看MCP服务配置",
    },
    Permission.MCP_WRITE_SSE.value: {
        "label": "创建SSE类型MCP",
        "description": "创建SSE传输类型的MCP服务",
    },
    Permission.MCP_WRITE_HTTP.value: {
        "label": "创建HTTP类型MCP",
        "description": "创建HTTP/streamable_http传输类型的MCP服务",
    },
    Permission.MCP_DELETE.value: {
        "label": "删除MCP配置",
        "description": "删除MCP服务配置",
    },
    Permission.MCP_ADMIN.value: {
        "label": "管理MCP服务",
        "description": "管理MCP服务的完整权限",
    },
    # File
    Permission.FILE_UPLOAD.value: {
        "label": "上传文件",
        "description": "上传文件和头像",
    },
    Permission.FILE_UPLOAD_IMAGE.value: {
        "label": "上传图片",
        "description": "允许上传图片文件（jpg, png, gif 等）",
    },
    Permission.FILE_UPLOAD_VIDEO.value: {
        "label": "上传视频",
        "description": "允许上传视频文件（mp4, webm 等）",
    },
    Permission.FILE_UPLOAD_AUDIO.value: {
        "label": "上传音频",
        "description": "允许上传音频文件（mp3, wav 等）",
    },
    Permission.FILE_UPLOAD_DOCUMENT.value: {
        "label": "上传文档",
        "description": "允许上传文档文件（pdf, word, excel 等）",
    },
    # Avatar
    Permission.AVATAR_UPLOAD.value: {
        "label": "上传头像",
        "description": "允许上传和删除用户头像",
    },
    # Feedback
    Permission.FEEDBACK_WRITE.value: {
        "label": "提交反馈",
        "description": "允许提交消息反馈（点赞/点踩）",
    },
    Permission.FEEDBACK_READ.value: {
        "label": "查看反馈",
        "description": "查看反馈列表和统计",
    },
    Permission.FEEDBACK_ADMIN.value: {
        "label": "管理反馈",
        "description": "删除和管理所有用户反馈",
    },
    # Agent
    Permission.AGENT_READ.value: {
        "label": "读取智能体",
        "description": "查看智能体配置和状态",
    },
    Permission.AGENT_ADMIN.value: {
        "label": "管理智能体",
        "description": "创建、修改和删除智能体配置（管理员权限）",
    },
    # Team
    Permission.TEAM_READ.value: {
        "label": "查看团队",
        "description": "查看自己的智能体团队",
    },
    Permission.TEAM_WRITE.value: {
        "label": "管理团队",
        "description": "创建和修改自己的智能体团队",
    },
    Permission.TEAM_DELETE.value: {
        "label": "删除团队",
        "description": "删除自己的智能体团队",
    },
    # Model
    Permission.MODEL_ADMIN.value: {
        "label": "管理模型",
        "description": "管理角色可用的模型分配（管理员权限）",
    },
    # Channel - Generic
    Permission.CHANNEL_READ.value: {
        "label": "查看渠道",
        "description": "查看渠道配置和连接状态",
    },
    Permission.CHANNEL_WRITE.value: {
        "label": "配置渠道",
        "description": "创建和修改渠道配置",
    },
    Permission.CHANNEL_DELETE.value: {
        "label": "删除渠道",
        "description": "删除渠道配置",
    },
    # Marketplace
    Permission.MARKETPLACE_READ.value: {
        "label": "浏览商店",
        "description": "查看和浏览技能商店",
    },
    Permission.MARKETPLACE_PUBLISH.value: {
        "label": "发布技能",
        "description": "发布和更新商店中的技能",
    },
    Permission.MARKETPLACE_ADMIN.value: {
        "label": "管理商店",
        "description": "管理技能商店（激活/停用/删除任意技能）",
    },
    # Persona Preset
    Permission.PERSONA_PRESET_READ.value: {
        "label": "浏览角色预设",
        "description": "查看角色广场和自己的角色预设",
    },
    Permission.PERSONA_PRESET_WRITE.value: {
        "label": "管理个人角色预设",
        "description": "创建、编辑、删除自己的角色预设副本",
    },
    Permission.PERSONA_PRESET_ADMIN.value: {
        "label": "管理全局角色预设",
        "description": "创建、发布、归档和删除全局角色预设",
    },
    # Scheduled Task
    Permission.SCHEDULED_TASK_READ.value: {
        "label": "读取定时任务",
        "description": "查看定时任务、运行历史和任务会话",
    },
    Permission.SCHEDULED_TASK_WRITE.value: {
        "label": "管理定时任务",
        "description": "创建、编辑、暂停、恢复和手动执行定时任务",
    },
    Permission.SCHEDULED_TASK_DELETE.value: {
        "label": "删除定时任务",
        "description": "删除自己的定时任务",
    },
    # Notification
    Permission.NOTIFICATION_MANAGE.value: {
        "label": "管理通知",
        "description": "创建、编辑、删除系统通知公告",
    },
    # Usage
    Permission.USAGE_READ.value: {
        "label": "查看用量统计",
        "description": "查看自己的模型调用和 Token 用量统计",
    },
    Permission.USAGE_ADMIN.value: {
        "label": "管理用量统计",
        "description": "查看所有用户的模型调用和 Token 用量统计",
    },
    # Environment Variables
    Permission.ENVVAR_READ.value: {
        "label": "读取环境变量",
        "description": "查看用户环境变量",
    },
    Permission.ENVVAR_WRITE.value: {
        "label": "管理环境变量",
        "description": "创建和更新用户环境变量",
    },
    Permission.ENVVAR_DELETE.value: {
        "label": "删除环境变量",
        "description": "删除用户环境变量",
    },
}

# 权限分组配置
PERMISSION_GROUPS_CONFIG: list[PermissionGroupConfig] = [
    {
        "name": "聊天",
        "permissions": [
            Permission.CHAT_READ.value,
            Permission.CHAT_WRITE.value,
        ],
    },
    {
        "name": "会话",
        "permissions": [
            Permission.SESSION_READ.value,
            Permission.SESSION_WRITE.value,
            Permission.SESSION_DELETE.value,
            Permission.SESSION_ADMIN.value,
            Permission.SESSION_SHARE.value,
        ],
    },
    {
        "name": "技能",
        "permissions": [
            Permission.SKILL_READ.value,
            Permission.SKILL_WRITE.value,
            Permission.SKILL_DELETE.value,
            Permission.SKILL_ADMIN.value,
        ],
    },
    {
        "name": "用户管理",
        "permissions": [
            Permission.USER_READ.value,
            Permission.USER_WRITE.value,
            Permission.USER_DELETE.value,
        ],
    },
    {
        "name": "角色管理",
        "permissions": [
            Permission.ROLE_MANAGE.value,
        ],
    },
    {
        "name": "系统设置",
        "permissions": [
            Permission.SETTINGS_MANAGE.value,
        ],
    },
    {
        "name": "MCP服务",
        "permissions": [
            Permission.MCP_READ.value,
            Permission.MCP_WRITE_SSE.value,
            Permission.MCP_WRITE_HTTP.value,
            Permission.MCP_DELETE.value,
            Permission.MCP_ADMIN.value,
        ],
    },
    {
        "name": "文件上传",
        "permissions": [
            Permission.FILE_UPLOAD.value,
            Permission.FILE_UPLOAD_IMAGE.value,
            Permission.FILE_UPLOAD_VIDEO.value,
            Permission.FILE_UPLOAD_AUDIO.value,
            Permission.FILE_UPLOAD_DOCUMENT.value,
        ],
    },
    {
        "name": "头像",
        "permissions": [
            Permission.AVATAR_UPLOAD.value,
        ],
    },
    {
        "name": "反馈",
        "permissions": [
            Permission.FEEDBACK_WRITE.value,
            Permission.FEEDBACK_READ.value,
            Permission.FEEDBACK_ADMIN.value,
        ],
    },
    {
        "name": "智能体",
        "permissions": [
            Permission.AGENT_READ.value,
            Permission.AGENT_ADMIN.value,
        ],
    },
    {
        "name": "智能体团队",
        "permissions": [
            Permission.TEAM_READ.value,
            Permission.TEAM_WRITE.value,
            Permission.TEAM_DELETE.value,
        ],
    },
    {
        "name": "模型管理",
        "permissions": [
            Permission.MODEL_ADMIN.value,
        ],
    },
    {
        "name": "渠道管理",
        "permissions": [
            Permission.CHANNEL_READ.value,
            Permission.CHANNEL_WRITE.value,
            Permission.CHANNEL_DELETE.value,
        ],
    },
    {
        "name": "技能商店",
        "permissions": [
            Permission.MARKETPLACE_READ.value,
            Permission.MARKETPLACE_PUBLISH.value,
            Permission.MARKETPLACE_ADMIN.value,
        ],
    },
    {
        "name": "角色预设",
        "permissions": [
            Permission.PERSONA_PRESET_READ.value,
            Permission.PERSONA_PRESET_WRITE.value,
            Permission.PERSONA_PRESET_ADMIN.value,
        ],
    },
    {
        "name": "定时任务",
        "permissions": [
            Permission.SCHEDULED_TASK_READ.value,
            Permission.SCHEDULED_TASK_WRITE.value,
            Permission.SCHEDULED_TASK_DELETE.value,
        ],
    },
    {
        "name": "通知公告",
        "permissions": [
            Permission.NOTIFICATION_MANAGE.value,
        ],
    },
    {
        "name": "用量统计",
        "permissions": [
            Permission.USAGE_READ.value,
            Permission.USAGE_ADMIN.value,
        ],
    },
    {
        "name": "环境变量",
        "permissions": [
            Permission.ENVVAR_READ.value,
            Permission.ENVVAR_WRITE.value,
            Permission.ENVVAR_DELETE.value,
        ],
    },
]

# Split duties have explicit metadata; legacy values remain parseable only for migration.
PERMISSION_METADATA.update(
    {
        "system:admin": {
            "label": "系统最高管理",
            "description": "委派授权和管理受保护账户；不绕过个人数据所有权",
        },
        "user:create": {"label": "创建用户", "description": "创建账户，不包含角色分配和凭据管理"},
        "user:status": {"label": "启停账户", "description": "启用或停用授权范围内的账户"},
        "user:reset_password": {
            "label": "重置用户凭据",
            "description": "重置授权范围内用户密码或修改恢复邮箱",
        },
        "user:assign_roles": {
            "label": "分配用户角色",
            "description": "在明确委派范围内分配用户角色",
        },
        "role:read": {"label": "查看角色", "description": "查看角色目录和授权配置"},
        "role:write": {
            "label": "维护角色",
            "description": "创建角色和维护角色属性，不包含授予权限",
        },
        "role:delete": {"label": "删除角色", "description": "删除可管理的非系统角色"},
        "role:grant": {
            "label": "委派角色权限",
            "description": "在明确可授予范围内调整角色权限和委派范围",
        },
        "settings:read": {"label": "查看系统配置", "description": "查看掩码后的管理配置"},
        "settings:security": {
            "label": "修改安全配置",
            "description": "修改认证、账户、安全和敏感配置",
        },
        "settings:reset": {"label": "重置系统配置", "description": "重置配置或从环境导入配置"},
        "mcp:system_read": {
            "label": "查看系统 MCP",
            "description": "查看系统 MCP 配置的非敏感信息",
        },
        "mcp:system_delete": {"label": "删除系统 MCP", "description": "删除系统共享 MCP 服务"},
        "mcp:policy_manage": {
            "label": "管理 MCP 授权",
            "description": "配置工具策略、可用角色和配额",
        },
        "mcp:export": {
            "label": "导出 MCP 凭据",
            "description": "导出可访问范围内含密钥的 MCP 配置",
        },
        "file:read": {"label": "查看个人文件", "description": "查看和下载自己的文件及文件库"},
        "file:delete": {"label": "删除个人文件", "description": "删除自己的未被引用文件"},
        "agent:config_read": {"label": "查看智能体配置", "description": "查看智能体管理目录和配置"},
        "agent:assign": {"label": "分配智能体", "description": "管理角色可用的智能体范围"},
        "model:read": {"label": "查看模型配置", "description": "查看隐藏凭据的模型管理配置"},
        "model:delete": {"label": "删除模型", "description": "删除模型配置并清理引用"},
        "model:assign": {"label": "分配模型", "description": "管理角色模型白名单和显式无限制状态"},
        "pricing:manage": {"label": "管理计费价格", "description": "同步计费价格或补算历史费用"},
        "project:read": {"label": "查看个人项目", "description": "查看自己的项目目录"},
        "project:write": {"label": "维护个人项目", "description": "创建或修改自己的项目"},
        "project:delete": {
            "label": "删除个人项目",
            "description": "删除自己的项目，连带会话还需会话删除权限",
        },
        "memory:read": {"label": "查看个人记忆", "description": "查看或召回自己的记忆"},
        "memory:write": {"label": "维护个人记忆", "description": "创建、编辑或导入自己的记忆"},
        "memory:delete": {"label": "删除个人记忆", "description": "删除自己的记忆"},
        "memory:export": {"label": "导出个人记忆", "description": "导出自己的记忆内容"},
        "sandbox:read": {"label": "查看个人沙箱", "description": "查看自己的设备和沙箱文件"},
        "sandbox:execute": {"label": "使用个人沙箱", "description": "在自己的沙箱执行工具和代码"},
        "sandbox:manage": {
            "label": "管理个人设备",
            "description": "配对、管理或移除自己的沙箱设备",
        },
        "persona_preset:delete": {
            "label": "删除个人角色预设",
            "description": "删除自己的角色预设副本",
        },
        "envvar:reveal": {"label": "显示变量明文", "description": "显示自己的已保存环境变量明文"},
        "notification:read": {"label": "查看通知管理", "description": "查看全局通知列表"},
        "notification:delete": {"label": "删除系统通知", "description": "删除全局通知公告"},
        "usage:quota_manage": {
            "label": "管理用量额度",
            "description": "修改角色预算、重置额度或发放重置卡",
        },
    }
)

for _permission, _label in {
    "user:write": "编辑用户资料",
    "model:admin": "维护模型配置",
    "agent:admin": "维护智能体目录",
    "mcp:admin": "维护系统 MCP 配置",
    "usage:admin": "查看全局用量",
    "settings:manage": "维护普通系统配置",
    "feedback:admin": "删除反馈",
    "notification:manage": "编辑系统通知",
    "envvar:read": "查看环境变量名称",
}.items():
    PERMISSION_METADATA[_permission]["label"] = _label

RETIRED_PERMISSIONS = {"chat:read", "session:admin", "skill:admin", "role:manage"}

for _value, _metadata in PERMISSION_METADATA.items():
    if _value in {
        "user:write",
        "model:admin",
        "agent:admin",
        "mcp:admin",
        "usage:admin",
        "settings:manage",
    }:
        _metadata["description"] = {
            "user:write": "编辑用户资料，不含凭据、启停和角色分配",
            "model:admin": "创建和修改模型配置，不含授权分配、删除或计费",
            "agent:admin": "维护智能体目录，不含角色授权",
            "mcp:admin": "维护系统 MCP 连接配置，不含授权策略或凭据导出",
            "usage:admin": "查看所有用户用量，不含额度重置和发卡",
            "settings:manage": "修改非安全类普通配置，不含敏感配置和全量重置",
        }[_value]

_EXTRA_GROUP_NAMES = {
    "system": "系统管理",
    "user": "用户管理",
    "role": "角色管理",
    "settings": "系统设置",
    "mcp": "MCP服务",
    "file": "文件上传",
    "agent": "智能体",
    "model": "模型管理",
    "pricing": "计费管理",
    "project": "个人项目",
    "memory": "个人记忆",
    "sandbox": "个人沙箱",
    "persona_preset": "角色预设",
    "envvar": "环境变量",
    "notification": "通知公告",
    "usage": "用量统计",
}

for _value in [
    "system:admin",
    "user:create",
    "user:status",
    "user:reset_password",
    "user:assign_roles",
    "role:read",
    "role:write",
    "role:delete",
    "role:grant",
    "settings:read",
    "settings:security",
    "settings:reset",
    "mcp:system_read",
    "mcp:system_delete",
    "mcp:policy_manage",
    "mcp:export",
    "file:read",
    "file:delete",
    "agent:config_read",
    "agent:assign",
    "model:read",
    "model:delete",
    "model:assign",
    "pricing:manage",
    "project:read",
    "project:write",
    "project:delete",
    "memory:read",
    "memory:write",
    "memory:delete",
    "memory:export",
    "sandbox:read",
    "sandbox:execute",
    "sandbox:manage",
    "persona_preset:delete",
    "envvar:reveal",
    "notification:read",
    "notification:delete",
    "usage:quota_manage",
]:
    _name = _EXTRA_GROUP_NAMES[_value.split(":", 1)[0]]
    _group = next((group for group in PERMISSION_GROUPS_CONFIG if group["name"] == _name), None)
    if _group is None:
        _group = {"name": _name, "permissions": []}
        PERMISSION_GROUPS_CONFIG.append(_group)
    _group["permissions"].append(_value)


def get_permissions_response() -> PermissionsResponse:
    """
    获取权限列表响应

    Returns:
        PermissionsResponse: 包含所有权限分组和权限列表
    """
    # 构建权限分组
    groups: list[PermissionGroup] = []
    all_permissions: list[PermissionInfo] = []

    for group_config in PERMISSION_GROUPS_CONFIG:
        group_permissions: list[PermissionInfo] = []
        for perm_value in group_config["permissions"]:
            if perm_value in RETIRED_PERMISSIONS:
                continue
            metadata = PERMISSION_METADATA.get(perm_value, {})
            perm_info = PermissionInfo(
                value=perm_value,
                label=metadata.get("label", perm_value),
                description=metadata.get("description", ""),
            )
            group_permissions.append(perm_info)
            all_permissions.append(perm_info)

        groups.append(
            PermissionGroup(
                name=group_config["name"],
                permissions=group_permissions,
            )
        )

    return PermissionsResponse(
        groups=groups,
        all_permissions=all_permissions,
    )
