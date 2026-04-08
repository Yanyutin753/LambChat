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
    Permission.MCP_WRITE_SANDBOX.value: {
        "label": "创建Sandbox类型MCP",
        "description": "创建Sandbox传输类型的MCP服务（在沙箱内运行）",
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
            Permission.MCP_WRITE_SANDBOX.value,
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
        "name": "环境变量",
        "permissions": [
            Permission.ENVVAR_READ.value,
            Permission.ENVVAR_WRITE.value,
            Permission.ENVVAR_DELETE.value,
        ],
    },
]


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
