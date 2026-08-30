"""
统一错误码与业务异常。

唯一事实源：后端所有错误（REST 与 SSE）都从这里取码；
前端 ``backendErrors.<camelCase(code)>`` locale key 与此目录对齐，
跨栈一致性由 ``frontend/src/i18n/__tests__/backendErrorCodeCoverage.test.ts`` 守门。

枚举成员值为三元组 ``(snake_case 码名, 默认 HTTP 状态码, 英文兜底消息)``。
新增错误码时必须同步五语 locale，否则 CI 挂测试。
"""

from enum import Enum
from typing import Any


class ErrorCode(Enum):
    # ---------- common：通用兜底 ----------
    INTERNAL_ERROR = ("internal_error", 500, "Internal server error")
    VALIDATION_ERROR = ("validation_error", 422, "Request validation failed")
    UNAUTHORIZED = ("unauthorized", 401, "Authentication required")
    FORBIDDEN = ("forbidden", 403, "Permission denied")
    NOT_FOUND = ("not_found", 404, "Resource not found")
    BAD_REQUEST = ("bad_request", 400, "Bad request")
    CONFLICT = ("conflict", 409, "Request conflict")
    TOO_MANY_REQUESTS = ("too_many_requests", 429, "Too many requests, please try again later")
    PAYLOAD_TOO_LARGE = ("payload_too_large", 413, "Request payload too large")
    EVENT_PAYLOAD_TOO_LARGE = ("event_payload_too_large", 413, "Event payload too large")
    SERVICE_UNAVAILABLE = ("service_unavailable", 503, "Service unavailable")

    # ---------- auth：认证与账户 ----------
    AUTH_MISSING = ("auth_missing", 401, "Authentication credentials not provided")
    UNAUTHENTICATED = ("unauthenticated", 401, "Unauthenticated user")
    INVALID_TOKEN = ("invalid_token", 401, "Invalid token")
    INVALID_CREDENTIALS = ("invalid_credentials", 401, "Invalid username or password")
    REFRESH_TOKEN_MISSING = ("refresh_token_missing", 401, "Refresh token missing")
    REFRESH_TOKEN_INVALID = ("refresh_token_invalid", 401, "Invalid refresh token")
    INVALID_TOKEN_PAYLOAD = ("invalid_token_payload", 401, "Invalid token payload")
    REGISTRATION_CLOSED = ("registration_closed", 403, "Registration is closed")
    TURNSTILE_FAILED = ("turnstile_failed", 400, "Human verification failed, please try again")
    EMAIL_VERIFICATION_REQUIRED = (
        "email_verification_required",
        403,
        "Please verify your email before logging in",
    )
    EMAIL_NOT_VERIFIED = ("email_not_verified", 403, "Email not verified")
    ACCOUNT_NOT_ACTIVE = ("account_not_active", 403, "Account is not active, please verify your email first")
    EMAIL_RATE_LIMITED = ("email_rate_limited", 429, "Too many requests for this email, please try again later")
    EMAIL_SERVICE_DISABLED = ("email_service_disabled", 503, "Email service is not enabled")
    INVALID_RESET_TOKEN = ("invalid_reset_token", 400, "Invalid reset token")
    RESET_TOKEN_EXPIRED = ("reset_token_expired", 400, "Reset token has expired")
    INVALID_VERIFICATION_TOKEN = ("invalid_verification_token", 400, "Invalid or expired verification token")
    OAUTH_INVALID_STATE = ("oauth_invalid_state", 400, "Invalid OAuth state. Please try logging in again")
    OAUTH_FAILED = ("oauth_failed", 400, "OAuth authentication failed")
    OAUTH_URL_FAILED = ("oauth_url_failed", 500, "Failed to create authorization URL")

    # ---------- user / role：用户与角色 ----------
    USER_NOT_FOUND = ("user_not_found", 404, "User not found")
    ROLE_NOT_FOUND = ("role_not_found", 404, "Role not found")
    CANNOT_CHANGE_OWN_ROLE_PERMISSIONS = (
        "cannot_change_own_role_permissions",
        403,
        "Cannot change permissions of your own role",
    )
    APPROVAL_NOT_FOUND = ("approval_not_found", 404, "Approval request not found")
    APPROVAL_ALREADY_HANDLED = ("approval_already_handled", 400, "Approval request already handled")
    PERMISSION_MISSING = ("permission_missing", 403, "Missing permission: {{permission}}")

    # ---------- session：会话 ----------
    SESSION_NOT_FOUND = ("session_not_found", 404, "Session not found")
    MESSAGE_NOT_FOUND = ("message_not_found", 404, "Message not found")
    SESSION_DELETE_IN_PROGRESS = ("session_delete_in_progress", 409, "Session deletion is in progress")
    SESSION_ACCESS_DENIED = ("session_access_denied", 403, "No permission to access this session")
    SESSION_ERROR = ("session_error", 500, "Session operation failed")
    INVALID_SESSION_STATUS = ("invalid_session_status", 422, "Status must be active or archived")

    # ---------- project：项目 ----------
    PROJECT_NOT_FOUND = ("project_not_found", 404, "Project not found")
    MOVE_FAILED = ("move_failed", 500, "Move failed")
    MOVE_FAVORITE_SYNC_FAILED = ("move_favorite_sync_failed", 500, "Failed to sync favorite state after move")
    CANNOT_CREATE_FAVORITES_PROJECT = ("cannot_create_favorites_project", 400, "Cannot create a favorites project")
    CANNOT_DELETE_FAVORITES_PROJECT = ("cannot_delete_favorites_project", 400, "Cannot delete a favorites project")

    # ---------- 通用操作失败 ----------
    DELETE_FAILED = ("delete_failed", 500, "Delete failed")
    UPDATE_FAILED = ("update_failed", 500, "Update failed")
    FAVORITE_UPDATE_FAILED = ("favorite_update_failed", 500, "Failed to update favorite state")

    # ---------- share：分享 ----------
    SHARE_NO_PERMISSION = ("share_no_permission", 403, "No permission to share this session")
    SHARE_OWN_ONLY = ("share_own_only", 403, "You can only share your own sessions")
    SHARE_PARTIAL_NEEDS_RUN_IDS = ("share_partial_needs_run_ids", 400, "Partial shares require run_ids")
    SHARE_VIEW_OWN_ONLY = ("share_view_own_only", 403, "You can only view shares of your own sessions")
    SHARE_NOT_FOUND = ("share_not_found", 404, "Share not found")
    SHARE_DELETE_OWN_ONLY = ("share_delete_own_only", 403, "You can only delete shares you created")
    SHARE_EXPIRED_OR_MISSING = ("share_expired_or_missing", 404, "Share not found or expired")
    SHARE_LOGIN_REQUIRED = ("share_login_required", 401, "Login required to view this share")
    SHARE_SOURCE_MISSING = ("share_source_missing", 404, "The original session no longer exists")

    # ---------- persona：人设预设 ----------
    PERSONA_PRESET_NOT_FOUND = ("persona_preset_not_found", 404, "Persona preset not found")
    PERSONA_PRESET_NO_EDIT_PERMISSION = ("persona_preset_no_edit_permission", 403, "No permission to edit this persona preset")
    PERSONA_PRESET_NO_DELETE_PERMISSION = ("persona_preset_no_delete_permission", 403, "No permission to delete this persona preset")
    PERSONA_PRESET_NO_ADMIN_PERMISSION = ("persona_preset_no_admin_permission", 403, "No admin permission for this persona preset")

    # ---------- channel：渠道实例 ----------
    CHANNEL_INSTANCE_NOT_FOUND = ("channel_instance_not_found", 404, "Channel instance not found")
    CHANNEL_INSTANCE_DISABLED = ("channel_instance_disabled", 400, "Channel instance is disabled")
    INSTANCE_NAME_REQUIRED = ("instance_name_required", 400, "Instance name is required")

    # ---------- envvar：环境变量 ----------
    INVALID_ENV_KEY_FORMAT = (
        "invalid_env_key_format",
        400,
        "Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$",
    )

    # ---------- file / upload：文件与上传 ----------
    INVALID_FILE_ID = ("invalid_file_id", 400, "Invalid file ID format")
    ZIP_REQUIRED = ("zip_required", 400, "File must be a ZIP archive")
    FILE_READ_FAILED = ("file_read_failed", 500, "Failed to read file content")
    INVALID_FILE_PATH = ("invalid_file_path", 400, "Invalid file path")
    FILE_NOT_FOUND = ("file_not_found", 404, "File not found")
    EMPTY_FILE = ("empty_file", 400, "Empty file")
    FILE_UPLOAD_NO_PERMISSION = ("file_upload_no_permission", 403, "No permission to upload {{category}} files")
    FILE_TOO_LARGE = ("file_too_large", 413, "File size exceeds maximum of {{max}}MB")
    AVATAR_TOO_LARGE = ("avatar_too_large", 413, "Avatar file size exceeds maximum of 2MB")
    UPLOAD_DUPLICATE_CONFLICT = ("upload_duplicate_conflict", 409, "Upload failed: duplicate record conflict")
    FILE_URL_FAILED = ("file_url_failed", 500, "Failed to generate file URL")

    # ---------- skill / marketplace：技能与市场 ----------
    SKILL_NOT_FOUND = ("skill_not_found", 404, "Skill not found")
    SKILL_ERROR = ("skill_error", 500, "Skill operation failed")
    SKILL_DEACTIVATED = ("skill_deactivated", 403, "This skill has been deactivated")
    SKILL_FILE_REQUIRED = ("skill_file_required", 400, "Skill must have at least one file")
    PUBLISH_SKILL_FAILED = ("publish_skill_failed", 500, "Failed to publish skill")
    MARKETPLACE_SKILL_NAME_REQUIRED = ("marketplace_skill_name_required", 400, "Marketplace skill name is required")
    MARKETPLACE_SYNC_ROLLED_BACK = (
        "marketplace_sync_rolled_back",
        500,
        "Failed to sync files, marketplace entry rolled back",
    )
    MARKETPLACE_SYNC_FAILED = ("marketplace_sync_failed", 500, "Failed to sync files to marketplace")
    MARKETPLACE_SKILL_NO_FILES = ("marketplace_skill_no_files", 404, "Marketplace skill has no files")
    ONLY_CREATOR_CAN_UPDATE = ("only_creator_can_update", 403, "Only the creator can update")
    ONLY_CREATOR_CAN_TOGGLE_TOOLS = ("only_creator_can_toggle_tools", 403, "Only the creator can toggle tools on this server")
    REPOSITORY_OR_BRANCH_NOT_FOUND = ("repository_or_branch_not_found", 404, "Repository or branch not found")
    NO_SKILLS_FOUND_IN_REPOSITORY = ("no_skills_found_in_repository", 404, "No skills found in repository")

    # ---------- settings / notification ----------
    SETTING_NOT_FOUND = ("setting_not_found", 404, "Setting not found")
    NOTIFICATION_NOT_FOUND = ("notification_not_found", 404, "Notification not found")

    # ---------- memory：记忆 ----------
    MEMORY_BACKEND_UNAVAILABLE = ("memory_backend_unavailable", 503, "Memory backend not available")
    MEMORY_NOT_FOUND = ("memory_not_found", 404, "Memory not found")
    MEMORY_IDS_REQUIRED = ("memory_ids_required", 400, "memory_ids must be a non-empty list")
    MEMORY_DELETE_LIMIT = ("memory_delete_limit", 400, "Cannot delete more than 100 memories at once")

    # ---------- mcp / model：MCP 与模型 ----------
    MCP_SERVER_EXISTS = ("mcp_server_exists", 409, "Server '{{name}}' already exists")
    TARGET_USER_REQUIRED = (
        "target_user_required",
        400,
        "target_user_id is required to identify the user server",
    )
    TARGET_OWNER_REQUIRED = (
        "target_owner_required",
        400,
        "target_user_id is required to specify the new owner",
    )
    INVALID_DISABLED_TOOLS = ("invalid_disabled_tools", 400, "Invalid disabled_tools: must be a list of strings")
    INVALID_PINNED_MODEL_IDS = ("invalid_pinned_model_ids", 400, "Invalid pinned_model_ids: must be a list of strings")
    TOO_MANY_PINNED_MODELS = ("too_many_pinned_models", 400, "Too many pinned models: maximum 10 allowed")
    MODELS_REQUIRED = ("models_required", 400, "models must be a non-empty list")
    MODEL_FALLBACK_SELF = ("model_fallback_self", 400, "A model cannot be its own fallback")
    MODEL_NOT_FOUND = ("model_not_found", 404, "Model not found")
    MODEL_DISABLED = ("model_disabled", 400, "Model is disabled")
    MODEL_NOT_ALLOWED = ("model_not_allowed", 403, "Model not allowed")

    # ---------- team：团队 ----------
    TEAM_NOT_FOUND = ("team_not_found", 404, "Team not found")
    TEAM_MEMBER_MODEL_UNAVAILABLE = ("team_member_model_unavailable", 400, "Team member model unavailable")

    # ---------- chat / agent：对话与执行 ----------
    INVALID_ATTACHMENTS = ("invalid_attachments", 400, "Invalid attachments")
    AGENT_ERROR = ("agent_error", 500, "Agent execution failed")
    LLM_ERROR = ("llm_error", 500, "LLM call failed")
    TOOL_ERROR = ("tool_error", 500, "Tool execution failed")

    # ---------- infra：基础设施 ----------
    CONFIGURATION_ERROR = ("configuration_error", 500, "Configuration error")
    STORAGE_ERROR = ("storage_error", 500, "Storage operation failed")

    # ---------- task：后台任务 ----------
    TASK_CANCELLED = ("task_cancelled", 409, "Task cancelled")
    TASK_SERVER_RESTART = ("task_server_restart", 409, "Interrupted by server restart")
    TASK_EXPIRED = ("task_expired", 410, "Task expired")

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def status(self) -> int:
        return self.value[1]

    @property
    def default_message(self) -> str:
        return self.value[2]

    @classmethod
    def from_code(cls, code: str) -> "ErrorCode":
        for member in cls:
            if member.code == code:
                return member
        raise ValueError(f"Unknown error code: {code}")


class AppError(Exception):
    """统一业务异常。

    - ``code``：必填，错误码唯一来源。
    - ``args``：前端 i18n 插值参数（如 ``{"name": "xxx"}``）。
    - ``message``：可选英文兜底原文；动态错误（``str(exc)``）经此透传。
    """

    def __init__(
        self,
        code: ErrorCode,
        *,
        args: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.error_code = code
        self.args_data = args or {}
        self.message = message if message is not None else code.default_message
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return self.error_code.status
