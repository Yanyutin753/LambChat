"""字面量 detail 的 HTTPException → AppError 批量迁移（codemod）。

只处理 detail 为字符串字面量的调用点；f-string / str(exc) 透传等留人工处理。
用法：uv run python scripts/codemod_error_literals.py [--dry]
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = ROOT / "src" / "api" / "routes"

# detail 字面量 → (ErrorCode 成员名, 可选 args 字面量)
MAPPING: dict[str, tuple[str, str]] = {
    # 英文
    "Admin permission required": ("ADMIN_PERMISSION_REQUIRED", ""),
    "Another replica is running the backfill": ("BACKFILL_IN_PROGRESS", ""),
    "Cannot delete more than 100 memories at once": ("MEMORY_DELETE_LIMIT", ""),
    "Cannot import more than 1000 memories at once": ("MEMORY_IMPORT_LIMIT", ""),
    "Channel instance is disabled": ("CHANNEL_INSTANCE_DISABLED", ""),
    "Channel instance not found": ("CHANNEL_INSTANCE_NOT_FOUND", ""),
    "Cover thumbnail not available": ("COVER_THUMBNAIL_NOT_AVAILABLE", ""),
    "Each memory must be an object": ("MEMORY_MUST_BE_OBJECT", ""),
    "Empty file": ("EMPTY_FILE", ""),
    "Failed to create authorization URL": ("OAUTH_URL_FAILED", ""),
    "Failed to generate file URL": ("FILE_URL_FAILED", ""),
    "Failed to publish skill": ("PUBLISH_SKILL_FAILED", ""),
    "Failed to read file content": ("FILE_READ_FAILED", ""),
    "Failed to read file": ("FILE_READ_FAILED", ""),
    "Failed to render cover": ("COVER_RENDER_FAILED", ""),
    "Failed to render thumb": ("THUMB_RENDER_FAILED", ""),
    "Failed to sync files to marketplace": ("MARKETPLACE_SYNC_FAILED", ""),
    "Failed to sync files, marketplace entry rolled back": ("MARKETPLACE_SYNC_ROLLED_BACK", ""),
    "Feedback not found": ("FEEDBACK_NOT_FOUND", ""),
    "File must be a ZIP archive": ("ZIP_REQUIRED", ""),
    "File not found": ("FILE_NOT_FOUND", ""),
    "Instance name is required": ("INSTANCE_NAME_REQUIRED", ""),
    "Invalid OAuth callback payload": ("OAUTH_CALLBACK_INVALID", ""),
    "Invalid OAuth state. Please try logging in again.": ("OAUTH_INVALID_STATE", ""),
    "Invalid feedback ID format": ("INVALID_FEEDBACK_ID", ""),
    "Invalid file ID format": ("INVALID_FILE_ID", ""),
    "Invalid file path": ("INVALID_FILE_PATH", ""),
    "Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$": ("INVALID_ENV_KEY_FORMAT", ""),
    "Marketplace skill files are incomplete": ("MARKETPLACE_FILES_INCOMPLETE", ""),
    "Marketplace skill has no files": ("MARKETPLACE_SKILL_NO_FILES", ""),
    "Marketplace skill name is required": ("MARKETPLACE_SKILL_NAME_REQUIRED", ""),
    "Memory backend not available": ("MEMORY_BACKEND_UNAVAILABLE", ""),
    "Memory content must be at least 5 characters": ("MEMORY_CONTENT_TOO_SHORT", ""),
    "Memory not found": ("MEMORY_NOT_FOUND", ""),
    "No skills found in repository": ("NO_SKILLS_FOUND_IN_REPOSITORY", ""),
    "Notification not found": ("NOTIFICATION_NOT_FOUND", ""),
    "OAuth authentication failed": ("OAUTH_FAILED", ""),
    "Only admin or creator can activate/deactivate": ("ONLY_ADMIN_OR_CREATOR_CAN_ACTIVATE", ""),
    "Only admin or creator can delete": ("ONLY_ADMIN_OR_CREATOR_CAN_DELETE", ""),
    "Only creator can update": ("ONLY_CREATOR_CAN_UPDATE", ""),
    "Only the creator can toggle tools on this server": ("ONLY_CREATOR_CAN_TOGGLE_TOOLS", ""),
    "Persona preset does not exist": ("PERSONA_PRESET_NOT_FOUND", ""),
    "Persona preset is not allowed": ("PERSONA_PRESET_NOT_ALLOWED", ""),
    "Push notifications are not available (VAPID key generation failed)": ("PUSH_UNAVAILABLE", ""),
    "Push subscription endpoint must use HTTPS": ("PUSH_ENDPOINT_HTTPS_REQUIRED", ""),
    "Push subscription keys are required": ("PUSH_SUBSCRIPTION_KEYS_REQUIRED", ""),
    "Registration session not found": ("REGISTRATION_SESSION_NOT_FOUND", ""),
    "Repository or branch not found": ("REPOSITORY_OR_BRANCH_NOT_FOUND", ""),
    "Setting not found": ("SETTING_NOT_FOUND", ""),
    "Skill must have at least one file": ("SKILL_FILE_REQUIRED", ""),
    "Skill not found": ("SKILL_NOT_FOUND", ""),
    "Task not found": ("TASK_NOT_FOUND", ""),
    "This skill has been deactivated": ("SKILL_DEACTIVATED", ""),
    "Thumb not available": ("THUMB_NOT_AVAILABLE", ""),
    "Upload failed: duplicate record conflict": ("UPLOAD_DUPLICATE_CONFLICT", ""),
    "User not found": ("USER_NOT_FOUND", ""),
    "expires must be between 60 and 86400 seconds": ("INVALID_EXPIRES_RANGE", ""),
    "memories must be a list": ("MEMORIES_MUST_BE_LIST", ""),
    "memory_ids must be a non-empty list": ("MEMORY_IDS_REQUIRED", ""),
    "models must be a non-empty list": ("MODELS_REQUIRED", ""),
    "persona_preset_not_found": ("PERSONA_PRESET_NOT_FOUND", ""),
    "target_user_id is required to identify the user server": ("TARGET_USER_REQUIRED", ""),
    "target_user_id is required to specify the new owner": ("TARGET_OWNER_REQUIRED", ""),
    "team_not_found": ("TEAM_NOT_FOUND", ""),
    # 中文
    "不能修改自己所属角色的权限": ("CANNOT_CHANGE_OWN_ROLE_PERMISSIONS", ""),
    "不能创建收藏项目": ("CANNOT_CREATE_FAVORITES_PROJECT", ""),
    "不能删除收藏项目": ("CANNOT_DELETE_FAVORITES_PROJECT", ""),
    "人机验证失败，请重试": ("TURNSTILE_FAILED", ""),
    "会话不在此分享中": ("SESSION_NOT_IN_SHARE", ""),
    "会话不存在": ("SESSION_NOT_FOUND", ""),
    "会话分享需要 session_id": ("SHARE_SESSION_ID_REQUIRED", ""),
    "分享不存在": ("SHARE_NOT_FOUND", ""),
    "分享不存在或已过期": ("SHARE_EXPIRED_OR_MISSING", ""),
    "删除失败": ("DELETE_FAILED", ""),
    "删除项目内会话失败": ("DELETE_PROJECT_SESSIONS_FAILED", ""),
    "原会话已不存在": ("SHARE_SOURCE_MISSING", ""),
    "只能分享自己的会话": ("SHARE_OWN_ONLY", ""),
    "只能删除自己创建的分享": ("SHARE_DELETE_OWN_ONLY", ""),
    "只能查看自己会话的分享": ("SHARE_VIEW_OWN_ONLY", ""),
    "只能编辑自己创建的分享": ("SHARE_EDIT_OWN_ONLY", ""),
    "审批请求不存在": ("APPROVAL_NOT_FOUND", ""),
    "审批请求已处理": ("APPROVAL_ALREADY_HANDLED", ""),
    "插话内容不能为空": ("STEER_CONTENT_REQUIRED", ""),
    "收藏状态更新失败": ("FAVORITE_UPDATE_FAILED", ""),
    "无效或过期的验证令牌": ("INVALID_VERIFICATION_TOKEN", ""),
    "无效的 before_trace_started_at": ("INVALID_BEFORE_TRACE_STARTED_AT", ""),
    "无效的令牌内容": ("INVALID_TOKEN_PAYLOAD", ""),
    "无效的刷新令牌": ("REFRESH_TOKEN_INVALID", ""),
    "无效的重置令牌": ("INVALID_RESET_TOKEN", ""),
    "无权访问此会话": ("SESSION_ACCESS_DENIED", ""),
    "更新失败": ("UPDATE_FAILED", ""),
    "注册已关闭": ("REGISTRATION_CLOSED", ""),
    "状态必须是 active 或 archived": ("INVALID_SESSION_STATUS", ""),
    "用户不存在": ("USER_NOT_FOUND", ""),
    "用户名或密码错误": ("INVALID_CREDENTIALS", ""),
    "移动后收藏状态同步失败": ("MOVE_FAVORITE_SYNC_FAILED", ""),
    "移动失败": ("MOVE_FAILED", ""),
    "缺少刷新令牌": ("REFRESH_TOKEN_MISSING", ""),
    "缺少权限: feedback:write": ("PERMISSION_MISSING", 'args={"permission": "feedback:write"}'),
    "置顶状态更新失败": ("PIN_UPDATE_FAILED", ""),
    "角色不存在": ("ROLE_NOT_FOUND", ""),
    "角色预设不存在": ("PERSONA_PRESET_NOT_FOUND", ""),
    "该邮箱请求过于频繁，请稍后再试": ("EMAIL_RATE_LIMITED", ""),
    "请先验证邮箱后再登录": ("EMAIL_VERIFICATION_REQUIRED", ""),
    "请求过于频繁，请稍后再试": ("TOO_MANY_REQUESTS", ""),
    "账户未激活，请验证邮箱后登录": ("ACCOUNT_NOT_ACTIVE", ""),
    "邮件服务未启用": ("EMAIL_SERVICE_DISABLED", ""),
    "部分会话不属于该项目": ("SESSIONS_NOT_IN_PROJECT", ""),
    "部分分享需要指定 run_ids": ("SHARE_PARTIAL_NEEDS_RUN_IDS", ""),
    "部分项目分享需要 session_ids": ("SHARE_PARTIAL_NEEDS_SESSION_IDS", ""),
    "项目分享需要 project_id": ("SHARE_PROJECT_NEEDS_PROJECT_ID", ""),
    "重置令牌已过期": ("RESET_TOKEN_EXPIRED", ""),
    "需要登录才能查看此分享": ("SHARE_LOGIN_REQUIRED", ""),
    "项目不存在": ("PROJECT_NOT_FOUND", ""),
}

# raise HTTPException( [status_code=] (404 | status.HTTP_404_NOT_FOUND) [,] [detail=] "literal" [, 尾随其他参数] )
RAISE_PAT = re.compile(
    r"""raise\s+HTTPException\(\s*
        (?:status_code\s*=\s*)?
        (?:(?:fastapi\.)?(?:starlette\.)?status\.HTTP_(?P<sn>\d{3})_\w+|(?P<dn>\d{3}))
        \s*,\s*
        (?:detail\s*=\s*)?
        (?P<q>["'])(?P<det>(?:[^"'\\]|\\.)*)(?P=q)
        (?P<trailing>\s*,[^)]*)?
        \s*\)""",
    re.VERBOSE,
)


def ensure_imports(source: str) -> str:
    """保证从 src.kernel.errors 导入 AppError 与 ErrorCode。"""
    if "from src.kernel.errors import" in source:
        m = re.search(r"from src\.kernel\.errors import ([^\n]+)", source)
        names = [n.strip() for n in m.group(1).split(",")]
        if "AppError" not in names:
            names.append("AppError")
        if "ErrorCode" not in names:
            names.append("ErrorCode")
        names = sorted(set(names))
        source = source[: m.start()] + "from src.kernel.errors import " + ", ".join(names) + source[m.end() :]
    else:
        # 用 AST 定位 fastapi 导入块结束行号之后插入（兼容括号多行导入）
        tree = ast.parse(source)
        insert_line = None
        first_body_line = tree.body[0].lineno if tree.body else 1
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "fastapi":
                insert_line = max(
                    getattr(n, "end_lineno", node.lineno) or node.lineno for n in [node]
                )
                break
        if insert_line is None:
            for node in tree.body:
                if isinstance(node, (ast.ImportFrom, ast.Import)):
                    insert_line = max(
                        insert_line or 0,
                        getattr(node, "end_lineno", node.lineno) or node.lineno,
                    )
        if insert_line is None:
            insert_line = first_body_line
        lines = source.splitlines(keepends=True)
        lines.insert(insert_line, "from src.kernel.errors import AppError, ErrorCode\n")
        source = "".join(lines)
    return source


def codemod_file(path: Path, dry: bool) -> int:
    source = path.read_text(encoding="utf-8")
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        detail_raw = m.group("det")
        try:
            detail = ast.literal_eval('"' + detail_raw + '"') if m.group("q") == '"' else ast.literal_eval("'" + detail_raw + "'")
        except (ValueError, SyntaxError):
            return m.group(0)
        if detail not in MAPPING:
            print(f"  !! 未映射: {path.name}:{source[:m.start()].count(chr(10))+1} {detail!r}")
            return m.group(0)
        member, args_lit = MAPPING[detail]
        count += 1
        suffix = f", {args_lit}" if args_lit else ""
        return f"raise AppError(ErrorCode.{member}{suffix})"

    new_source = RAISE_PAT.sub(_sub, source)
    if count and not dry:
        new_source = ensure_imports(new_source)
        path.write_text(new_source, encoding="utf-8")
    return count


def main() -> None:
    dry = "--dry" in sys.argv
    total = 0
    for py in sorted(ROUTES_DIR.rglob("*.py")):
        n = codemod_file(py, dry)
        if n:
            print(f"{py.relative_to(ROOT)}: {n} 处")
        total += n
    print(f"{'[DRY] ' if dry else ''}共迁移 {total} 处")


if __name__ == "__main__":
    main()
