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
    METHOD_NOT_ALLOWED = ("method_not_allowed", 405, "Method not allowed")
    BAD_REQUEST = ("bad_request", 400, "Bad request")
    CONFLICT = ("conflict", 409, "Request conflict")
    ADMIN_PERMISSION_REQUIRED = ("admin_permission_required", 403, "Admin permission required")
    BACKFILL_IN_PROGRESS = ("backfill_in_progress", 409, "Another replica is running the backfill")
    TOO_MANY_REQUESTS = ("too_many_requests", 429, "Too many requests, please try again later")
    PAYLOAD_TOO_LARGE = ("payload_too_large", 413, "Request payload too large")
    EVENT_PAYLOAD_TOO_LARGE = ("event_payload_too_large", 413, "Event payload too large")
    SERVICE_UNAVAILABLE = ("service_unavailable", 503, "Service unavailable")

    # ---------- auth：认证与账户 ----------
    AUTH_MISSING = ("auth_missing", 401, "Authentication credentials not provided")
    UNAUTHENTICATED = ("unauthenticated", 401, "Unauthenticated user")
    INVALID_TOKEN = ("invalid_token", 401, "Invalid token")
    TOKEN_EXPIRED = ("token_expired", 401, "Token has expired")
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
    ACCOUNT_NOT_ACTIVE = (
        "account_not_active",
        403,
        "Account is not active, please verify your email first",
    )
    EMAIL_RATE_LIMITED = (
        "email_rate_limited",
        429,
        "Too many requests for this email, please try again later",
    )
    EMAIL_SERVICE_DISABLED = ("email_service_disabled", 503, "Email service is not enabled")
    INVALID_RESET_TOKEN = ("invalid_reset_token", 400, "Invalid reset token")
    RESET_TOKEN_EXPIRED = ("reset_token_expired", 400, "Reset token has expired")
    INVALID_VERIFICATION_TOKEN = (
        "invalid_verification_token",
        400,
        "Invalid or expired verification token",
    )
    OAUTH_INVALID_STATE = (
        "oauth_invalid_state",
        400,
        "Invalid OAuth state. Please try logging in again",
    )
    OAUTH_CALLBACK_INVALID = ("oauth_callback_invalid", 400, "Invalid OAuth callback payload")
    OAUTH_FAILED = ("oauth_failed", 400, "OAuth authentication failed")
    OAUTH_URL_FAILED = ("oauth_url_failed", 500, "Failed to create authorization URL")
    REGISTRATION_SESSION_NOT_FOUND = (
        "registration_session_not_found",
        404,
        "Registration session not found",
    )

    OAUTH_PROVIDER_DISABLED = (
        "oauth_provider_disabled",
        400,
        "OAuth provider '{{provider}}' is not enabled",
    )

    # ---------- sandbox：本地沙箱 PAT 与守护进程 ----------
    PAT_NOT_FOUND = ("pat_not_found", 401, "Personal access token not found or revoked")
    PAT_EXPIRED = ("pat_expired", 401, "Personal access token expired")
    PAT_SCOPE_DENIED = ("pat_scope_denied", 403, "Token missing required scope '{{scope}}'")
    DAEMON_OFFLINE = ("daemon_offline", 409, "Local sandbox daemon is offline")
    SANDBOX_TIMEOUT = ("sandbox_timeout", 504, "Local sandbox call timed out after {{seconds}}s")
    SANDBOX_PAYLOAD_TOO_LARGE = (
        "sandbox_payload_too_large",
        413,
        "Local sandbox payload exceeds limit",
    )

    # ---------- push：推送订阅 ----------
    PUSH_UNAVAILABLE = (
        "push_unavailable",
        503,
        "Push notifications are not available (VAPID key generation failed)",
    )
    PUSH_ENDPOINT_HTTPS_REQUIRED = (
        "push_endpoint_https_required",
        400,
        "Push subscription endpoint must use HTTPS",
    )
    PUSH_SUBSCRIPTION_KEYS_REQUIRED = (
        "push_subscription_keys_required",
        400,
        "Push subscription keys are required",
    )

    # ---------- feedback：反馈 ----------
    FEEDBACK_NOT_FOUND = ("feedback_not_found", 404, "Feedback not found")
    INVALID_FEEDBACK_ID = ("invalid_feedback_id", 400, "Invalid feedback ID format")

    # ---------- user / role：用户与角色 ----------
    USER_NOT_FOUND = ("user_not_found", 404, "User not found")
    USERNAME_EXISTS = ("username_exists", 409, "Username '{{username}}' already exists")
    EMAIL_EXISTS = ("email_exists", 409, "Email '{{email}}' is already registered")
    USERNAME_OR_EMAIL_EXISTS = ("username_or_email_exists", 409, "Username or email already exists")
    INVALID_PROFILE_FIELD_LIST = (
        "invalid_profile_field_list",
        400,
        "Invalid {{field}}: must be a list of strings",
    )
    PROFILE_FIELD_TOO_MANY = (
        "profile_field_too_many",
        400,
        "Too many {{field}}: maximum {{max}} allowed",
    )
    UNSUPPORTED_LANGUAGE = ("unsupported_language", 400, "Unsupported language: {{lang}}")
    INVALID_THEME = (
        "invalid_theme",
        400,
        "Invalid theme: {{theme}}. Must be 'light', 'dark' or 'sepia'",
    )
    ROLE_NOT_FOUND = ("role_not_found", 404, "Role not found")
    ROLE_NAME_EXISTS = ("role_name_exists", 409, "Role name '{{name}}' already exists")
    SYSTEM_ROLE_PROTECTED = (
        "system_role_protected",
        400,
        "System roles cannot be modified or deleted",
    )
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
    SESSION_DELETE_IN_PROGRESS = (
        "session_delete_in_progress",
        409,
        "Session deletion is in progress",
    )
    SESSION_ACCESS_DENIED = ("session_access_denied", 403, "No permission to access this session")
    SESSION_ERROR = ("session_error", 500, "Session operation failed")
    INVALID_SESSION_STATUS = ("invalid_session_status", 422, "Status must be active or archived")
    PIN_UPDATE_FAILED = ("pin_update_failed", 500, "Failed to update pin state")
    BOOKMARK_UPDATE_FAILED = (
        "bookmark_update_failed",
        500,
        "Failed to update bookmark state",
    )
    STEER_CONTENT_REQUIRED = ("steer_content_required", 422, "Steer content must not be empty")
    STEER_SESSION_NOT_RUNNING = (
        "steer_session_not_running",
        409,
        "Session status is {{status}}; only running sessions can be steered",
    )
    INVALID_BEFORE_TRACE_STARTED_AT = (
        "invalid_before_trace_started_at",
        400,
        "Invalid before_trace_started_at",
    )

    # ---------- project：项目 ----------
    PROJECT_NOT_FOUND = ("project_not_found", 404, "Project not found")
    MOVE_FAILED = ("move_failed", 500, "Move failed")
    MOVE_FAVORITE_SYNC_FAILED = (
        "move_favorite_sync_failed",
        500,
        "Failed to sync favorite state after move",
    )
    CANNOT_CREATE_FAVORITES_PROJECT = (
        "cannot_create_favorites_project",
        400,
        "Cannot create a favorites project",
    )
    CANNOT_DELETE_FAVORITES_PROJECT = (
        "cannot_delete_favorites_project",
        400,
        "Cannot delete a favorites project",
    )
    DELETE_PROJECT_SESSIONS_FAILED = (
        "delete_project_sessions_failed",
        500,
        "Failed to delete sessions in project",
    )
    SESSIONS_NOT_IN_PROJECT = (
        "sessions_not_in_project",
        400,
        "Some sessions do not belong to this project",
    )

    # ---------- 通用操作失败 ----------
    DELETE_FAILED = ("delete_failed", 500, "Delete failed")
    UPDATE_FAILED = ("update_failed", 500, "Update failed")
    FAVORITE_UPDATE_FAILED = ("favorite_update_failed", 500, "Failed to update favorite state")

    # ---------- share：分享 ----------
    SHARE_NO_PERMISSION = ("share_no_permission", 403, "No permission to share this session")
    SHARE_OWN_ONLY = ("share_own_only", 403, "You can only share your own sessions")
    SHARE_PARTIAL_NEEDS_RUN_IDS = (
        "share_partial_needs_run_ids",
        400,
        "Partial shares require run_ids",
    )
    SHARE_VIEW_OWN_ONLY = (
        "share_view_own_only",
        403,
        "You can only view shares of your own sessions",
    )
    SHARE_NOT_FOUND = ("share_not_found", 404, "Share not found")
    SHARE_DELETE_OWN_ONLY = ("share_delete_own_only", 403, "You can only delete shares you created")
    SHARE_EXPIRED_OR_MISSING = ("share_expired_or_missing", 404, "Share not found or expired")
    SHARE_LOGIN_REQUIRED = ("share_login_required", 401, "Login required to view this share")
    SHARE_SOURCE_MISSING = ("share_source_missing", 404, "The original session no longer exists")
    SESSION_NOT_IN_SHARE = ("session_not_in_share", 400, "Session is not in this share")
    SHARE_SESSION_ID_REQUIRED = (
        "share_session_id_required",
        400,
        "Session share requires session_id",
    )
    SHARE_EDIT_OWN_ONLY = ("share_edit_own_only", 403, "You can only edit shares you created")
    SHARE_PARTIAL_NEEDS_SESSION_IDS = (
        "share_partial_needs_session_ids",
        400,
        "Partial project shares require session_ids",
    )
    SHARE_PROJECT_NEEDS_PROJECT_ID = (
        "share_project_needs_project_id",
        400,
        "Project share requires project_id",
    )
    SHARE_RUN_IDS_LIMIT = ("share_run_ids_limit", 400, "run_ids cannot exceed {{max}} items")
    SHARE_SESSION_IDS_LIMIT = (
        "share_session_ids_limit",
        400,
        "session_ids cannot exceed {{max}} items",
    )

    # ---------- persona：人设预设 ----------
    PERSONA_PRESET_NOT_FOUND = ("persona_preset_not_found", 404, "Persona preset not found")
    PERSONA_PRESET_NO_EDIT_PERMISSION = (
        "persona_preset_no_edit_permission",
        403,
        "No permission to edit this persona preset",
    )
    PERSONA_PRESET_NO_DELETE_PERMISSION = (
        "persona_preset_no_delete_permission",
        403,
        "No permission to delete this persona preset",
    )
    PERSONA_PRESET_NO_ADMIN_PERMISSION = (
        "persona_preset_no_admin_permission",
        403,
        "No admin permission for this persona preset",
    )
    PERSONA_PRESET_NOT_ALLOWED = (
        "persona_preset_not_allowed",
        403,
        "Persona preset is not allowed",
    )

    # ---------- channel：渠道实例 ----------
    CHANNEL_INSTANCE_NOT_FOUND = ("channel_instance_not_found", 404, "Channel instance not found")
    CHANNEL_INSTANCE_DISABLED = ("channel_instance_disabled", 400, "Channel instance is disabled")
    INSTANCE_NAME_REQUIRED = ("instance_name_required", 400, "Instance name is required")
    CHANNEL_AGENT_UNAVAILABLE = (
        "channel_agent_unavailable",
        400,
        "Agent '{{agent_id}}' is not available",
    )
    CHANNEL_AGENT_NOT_ALLOWED = (
        "channel_agent_not_allowed",
        403,
        "Agent '{{agent_id}}' is not allowed for your role",
    )
    CHANNEL_LARK_UNAVAILABLE = (
        "channel_lark_unavailable",
        400,
        "lark-oapi register_app is unavailable",
    )
    CHANNEL_LIST_LIMIT = (
        "channel_list_limit",
        413,
        "Too many channel configurations to list at once (max {{max}})",
    )
    UNKNOWN_CHANNEL_TYPE = ("unknown_channel_type", 404, "Unknown channel type: {{type}}")
    CHANNEL_TYPE_MISMATCH = (
        "channel_type_mismatch",
        400,
        "Channel type mismatch: expected {{expected}}, got {{actual}}",
    )
    CHANNEL_LIMIT_REACHED = (
        "channel_limit_reached",
        400,
        "Maximum channel limit ({{max}}) reached. Please delete an existing channel first",
    )
    CHANNEL_ERROR = ("channel_error", 400, "Channel operation failed")

    # ---------- envvar：环境变量 ----------
    INVALID_ENV_KEY_FORMAT = (
        "invalid_env_key_format",
        400,
        "Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$",
    )
    ENVVAR_NOT_FOUND = ("envvar_not_found", 404, "Environment variable '{{key}}' not found")
    ENVVAR_ERROR = ("envvar_error", 400, "Environment variable operation failed")

    # ---------- file / upload：文件与上传 ----------
    INVALID_FILE_ID = ("invalid_file_id", 400, "Invalid file ID format")
    ZIP_REQUIRED = ("zip_required", 400, "File must be a ZIP archive")
    FILE_READ_FAILED = ("file_read_failed", 500, "Failed to read file content")
    INVALID_FILE_PATH = ("invalid_file_path", 400, "Invalid file path")
    FILE_NOT_FOUND = ("file_not_found", 404, "File not found")
    EMPTY_FILE = ("empty_file", 400, "Empty file")
    FILE_UPLOAD_NO_PERMISSION = (
        "file_upload_no_permission",
        403,
        "No permission to upload {{category}} files",
    )
    FILE_TOO_LARGE = ("file_too_large", 413, "File size exceeds maximum of {{max}}MB")
    AVATAR_TOO_LARGE = ("avatar_too_large", 413, "Avatar file size exceeds maximum of 2MB")
    UPLOAD_DUPLICATE_CONFLICT = (
        "upload_duplicate_conflict",
        409,
        "Upload failed: duplicate record conflict",
    )
    FILE_URL_FAILED = ("file_url_failed", 500, "Failed to generate file URL")
    FILE_EXTENSION_NOT_ALLOWED = (
        "file_extension_not_allowed",
        400,
        "File extension '.{{ext}}' is not allowed for {{category}} files",
    )
    FILE_TYPE_NOT_ALLOWED = (
        "file_type_not_allowed",
        400,
        "File type '.{{ext}}' is not allowed. Allowed types: {{allowed}}",
    )
    UPLOAD_FAILED = ("upload_failed", 500, "Upload failed")
    AVATAR_UPLOAD_FAILED = ("avatar_upload_failed", 500, "Avatar upload failed")
    AVATAR_DELETE_FAILED = ("avatar_delete_failed", 500, "Avatar deletion failed")
    COVER_THUMBNAIL_NOT_AVAILABLE = (
        "cover_thumbnail_not_available",
        404,
        "Cover thumbnail not available",
    )
    THUMB_NOT_AVAILABLE = ("thumb_not_available", 404, "Thumb not available")
    COVER_RENDER_FAILED = ("cover_render_failed", 500, "Failed to render cover")
    THUMB_RENDER_FAILED = ("thumb_render_failed", 500, "Failed to render thumb")

    # ---------- skill / marketplace：技能与市场 ----------
    SKILL_NOT_FOUND = ("skill_not_found", 404, "Skill not found")
    SKILL_ERROR = ("skill_error", 500, "Skill operation failed")
    SKILL_DEACTIVATED = ("skill_deactivated", 403, "This skill has been deactivated")
    SKILL_FILE_REQUIRED = ("skill_file_required", 400, "Skill must have at least one file")
    PUBLISH_SKILL_FAILED = ("publish_skill_failed", 500, "Failed to publish skill")
    MARKETPLACE_SKILL_NAME_REQUIRED = (
        "marketplace_skill_name_required",
        400,
        "Marketplace skill name is required",
    )
    MARKETPLACE_SYNC_ROLLED_BACK = (
        "marketplace_sync_rolled_back",
        500,
        "Failed to sync files, marketplace entry rolled back",
    )
    MARKETPLACE_SYNC_FAILED = (
        "marketplace_sync_failed",
        500,
        "Failed to sync files to marketplace",
    )
    MARKETPLACE_SKILL_NO_FILES = (
        "marketplace_skill_no_files",
        404,
        "Marketplace skill has no files",
    )
    MARKETPLACE_FILES_INCOMPLETE = (
        "marketplace_files_incomplete",
        500,
        "Marketplace skill files are incomplete",
    )
    ONLY_CREATOR_CAN_UPDATE = ("only_creator_can_update", 403, "Only the creator can update")
    ONLY_CREATOR_CAN_TOGGLE_TOOLS = (
        "only_creator_can_toggle_tools",
        403,
        "Only the creator can toggle tools on this server",
    )
    ONLY_ADMIN_OR_CREATOR_CAN_ACTIVATE = (
        "only_admin_or_creator_can_activate",
        403,
        "Only admin or creator can activate/deactivate",
    )
    ONLY_ADMIN_OR_CREATOR_CAN_DELETE = (
        "only_admin_or_creator_can_delete",
        403,
        "Only admin or creator can delete",
    )
    INVALID_EXPIRES_RANGE = (
        "invalid_expires_range",
        400,
        "expires must be between 60 and 86400 seconds",
    )
    REPOSITORY_OR_BRANCH_NOT_FOUND = (
        "repository_or_branch_not_found",
        404,
        "Repository or branch not found",
    )
    NO_SKILLS_FOUND_IN_REPOSITORY = (
        "no_skills_found_in_repository",
        404,
        "No skills found in repository",
    )
    SKILL_BATCH_LIMIT = (
        "skill_batch_limit",
        400,
        "Cannot process more than {{max}} skills at once",
    )
    SKILL_BATCH_ALL_FAILED = ("skill_batch_all_failed", 400, "All skills failed")
    SKILL_BINARY_UPLOAD_FAILED = ("skill_binary_upload_failed", 500, "Failed to upload binary file")
    SKILL_FILE_NOT_FOUND = (
        "skill_file_not_found",
        404,
        "File '{{path}}' not found in skill '{{skill}}'",
    )
    SKILLS_NOT_FOUND = ("skills_not_found", 404, "Skill(s) not found: {{missing}}")
    SKILL_ALREADY_INSTALLED = ("skill_already_installed", 409, "Skill '{{name}}' already installed")
    SKILL_NOT_INSTALLED = (
        "skill_not_installed",
        400,
        "Skill '{{name}}' not installed. Install it first",
    )
    SKILL_MANUAL_NO_UPDATE = (
        "skill_manual_no_update",
        409,
        "Skill '{{name}}' is a manual skill and cannot be updated from marketplace",
    )
    MARKETPLACE_SKILL_NOT_FOUND = (
        "marketplace_skill_not_found",
        404,
        "Marketplace skill '{{name}}' not found",
    )
    MARKETPLACE_NAME_TAKEN = (
        "marketplace_name_taken",
        409,
        "Marketplace skill name '{{name}}' is already taken",
    )
    MARKETPLACE_FILE_COUNT_LIMIT = (
        "marketplace_file_count_limit",
        413,
        "Marketplace skill contains too many files (max {{max}})",
    )
    MARKETPLACE_FILE_TOO_LARGE = (
        "marketplace_file_too_large",
        413,
        "Marketplace skill file is too large (max {{max}} characters)",
    )
    MARKETPLACE_TOTAL_TOO_LARGE = (
        "marketplace_total_too_large",
        413,
        "Marketplace skill files are too large (max {{max}} total characters)",
    )
    GITHUB_INSTALL_LIMIT = (
        "github_install_limit",
        400,
        "Cannot install more than {{max}} skills at once",
    )
    GITHUB_RATE_LIMITED = ("github_rate_limited", 429, "GitHub API rate limit exceeded")
    GITHUB_ERROR = ("github_error", 400, "GitHub operation failed")
    GITHUB_API_ERROR = ("github_api_error", 500, "GitHub API error: {{status}}")
    GITHUB_FETCH_FAILED = ("github_fetch_failed", 500, "Failed to fetch repository")
    GITHUB_SCAN_FAILED = ("github_scan_failed", 500, "Failed to scan repository")

    # ---------- settings / notification ----------
    SETTING_NOT_FOUND = ("setting_not_found", 404, "Setting not found")
    NOTIFICATION_NOT_FOUND = ("notification_not_found", 404, "Notification not found")

    # ---------- memory：记忆 ----------
    MEMORY_BACKEND_UNAVAILABLE = ("memory_backend_unavailable", 503, "Memory backend not available")
    MEMORY_NOT_FOUND = ("memory_not_found", 404, "Memory not found")
    MEMORY_IDS_REQUIRED = ("memory_ids_required", 400, "memory_ids must be a non-empty list")
    MEMORY_DELETE_LIMIT = (
        "memory_delete_limit",
        400,
        "Cannot delete more than 100 memories at once",
    )
    MEMORY_IMPORT_LIMIT = (
        "memory_import_limit",
        400,
        "Cannot import more than 1000 memories at once",
    )
    MEMORY_MUST_BE_OBJECT = ("memory_must_be_object", 400, "Each memory must be an object")
    MEMORY_CONTENT_TOO_SHORT = (
        "memory_content_too_short",
        400,
        "Memory content must be at least 5 characters",
    )
    MEMORIES_MUST_BE_LIST = ("memories_must_be_list", 400, "memories must be a list")
    MEMORY_CONTENT_TOO_LARGE = (
        "memory_content_too_large",
        400,
        "Memory content too large (max {{max}} characters)",
    )
    MEMORY_IMPORT_TOO_LARGE = (
        "memory_import_too_large",
        400,
        "Memory import content too large (max {{max}} total characters)",
    )
    INVALID_MEMORY_TYPE = (
        "invalid_memory_type",
        422,
        "Invalid memory_type. Must be one of: {{allowed}}",
    )
    INVALID_MEMORY_SOURCE = (
        "invalid_memory_source",
        422,
        "Invalid source. Must be one of: {{allowed}}",
    )

    # ---------- mcp / model：MCP 与模型 ----------
    MCP_SERVER_EXISTS = ("mcp_server_exists", 409, "Server '{{name}}' already exists")
    MCP_SERVER_EXISTS_AS_SYSTEM = (
        "mcp_server_exists_as_system",
        400,
        "Server '{{name}}' already exists as a system server",
    )
    MCP_SYSTEM_SERVER_EXISTS = (
        "mcp_system_server_exists",
        400,
        "System server '{{name}}' already exists",
    )
    MCP_SYSTEM_SERVER_NOT_FOUND = (
        "mcp_system_server_not_found",
        404,
        "System server '{{name}}' not found",
    )
    MCP_SYSTEM_SERVER_CONFLICT = (
        "mcp_system_server_conflict",
        404,
        "System server '{{name}}' not found or user already has server with same name",
    )
    MCP_USER_SERVER_NOT_FOUND = (
        "mcp_user_server_not_found",
        404,
        "User server '{{name}}' not found or system server with same name exists",
    )
    MCP_IMPORT_LIMIT = (
        "mcp_import_limit",
        413,
        "Import contains too many MCP servers (max {{max}})",
    )
    MCP_WRITE_PERMISSION_DENIED = (
        "mcp_write_permission_denied",
        403,
        "Permission denied. Requires '{{permission}}' or 'mcp:admin' permission",
    )
    MCP_SERVER_PERMISSION_DENIED = (
        "mcp_server_permission_denied",
        403,
        "Permission denied for server '{{name}}'. Requires '{{permission}}' or 'mcp:admin' permission",
    )
    MCP_SERVER_NOT_FOUND = ("mcp_server_not_found", 404, "Server '{{name}}' not found")
    MCP_SERVER_NOT_OWNED = (
        "mcp_server_not_owned",
        404,
        "Server '{{name}}' not found or not owned by user",
    )
    MCP_SERVER_ERROR = ("mcp_server_error", 400, "MCP server operation failed")
    MODEL_BATCH_LIMIT = (
        "model_batch_limit",
        413,
        "Cannot process more than {{max}} models at once",
    )
    INVALID_PROVIDER = (
        "invalid_provider",
        400,
        "Invalid provider '{{provider}}'. Must be a non-empty string",
    )
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
    INVALID_DISABLED_TOOLS = (
        "invalid_disabled_tools",
        400,
        "Invalid disabled_tools: must be a list of strings",
    )
    INVALID_PINNED_MODEL_IDS = (
        "invalid_pinned_model_ids",
        400,
        "Invalid pinned_model_ids: must be a list of strings",
    )
    TOO_MANY_PINNED_MODELS = (
        "too_many_pinned_models",
        400,
        "Too many pinned models: maximum 10 allowed",
    )
    MODELS_REQUIRED = ("models_required", 400, "models must be a non-empty list")
    MODEL_FALLBACK_SELF = ("model_fallback_self", 400, "A model cannot be its own fallback")
    MODEL_NOT_FOUND = ("model_not_found", 404, "Model not found")
    MODEL_DISABLED = ("model_disabled", 400, "Model is disabled")
    MODEL_NOT_ALLOWED = ("model_not_allowed", 403, "Model not allowed")
    MODEL_EMPTY_RESPONSE = (
        "model_empty_response",
        500,
        "The model returned an empty response after retries, please try again or switch models",
    )

    # ---------- team：团队 ----------
    TEAM_NOT_FOUND = ("team_not_found", 404, "Team not found")
    TEAM_MEMBER_MODEL_UNAVAILABLE = (
        "team_member_model_unavailable",
        400,
        "Team member model unavailable",
    )
    TEAM_ERROR = ("team_error", 400, "Team operation failed")

    # ---------- human / task：人工恢复与后台任务 ----------
    HUMAN_RESUME_SUBMIT_FAILED = (
        "human_resume_submit_failed",
        503,
        "Failed to submit resume task, please retry",
    )
    SCHEDULED_TASK_ERROR = ("scheduled_task_error", 400, "Scheduled task operation failed")

    # ---------- chat / agent：对话与执行 ----------
    INVALID_ATTACHMENTS = ("invalid_attachments", 400, "Invalid attachments")
    AGENT_NOT_REGISTERED = ("agent_not_registered", 422, "Agent '{{agent}}' is not registered")
    AGENT_ERROR = ("agent_error", 500, "Agent execution failed")
    LLM_ERROR = ("llm_error", 500, "LLM call failed")
    TOOL_ERROR = ("tool_error", 500, "Tool execution failed")

    # ---------- infra：基础设施 ----------
    CONFIGURATION_ERROR = ("configuration_error", 500, "Configuration error")
    STORAGE_ERROR = ("storage_error", 500, "Storage operation failed")

    # ---------- task：后台任务 ----------
    TASK_NOT_FOUND = ("task_not_found", 404, "Task not found")
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
