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
    Permission.MCP_WRITE_STDIO.value: {
        "label": "创建STDIO类型MCP",
        "description": "创建stdio传输类型的MCP服务",
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
            Permission.MCP_WRITE_STDIO.value,
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
