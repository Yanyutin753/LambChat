"""
会话路由

所有会话操作都需要认证，用户只能访问自己的会话。
管理员可以访问所有会话。
"""

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required
from src.infra.logging import get_logger
from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage
from src.kernel.config import settings
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

# 支持的语言白名单
SUPPORTED_LANGUAGES = frozenset(["en", "zh", "ja", "ko"])


def _is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试（429、网络错误等）"""
    error_str = str(error).lower()
    retryable_patterns = [
        "429",  # rate limit
        "503",  # service unavailable
        "502",  # bad gateway
        "504",  # gateway timeout
        "timeout",
        "connection",
        "overloaded",
        "网络错误",  # Chinese API proxy network error
        "network error",
    ]
    return any(pattern in error_str for pattern in retryable_patterns)


async def _ainvoke_with_retry(model, prompt: str, max_retries: int | None = None) -> Any:
    """带重试的 LLM 调用"""

    if max_retries is None:
        max_retries = getattr(settings, "LLM_MAX_RETRIES", 3)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await model.ainvoke(prompt)
        except Exception as e:
            last_error = e
            if _is_retryable_error(e) and attempt < max_retries - 1:
                delay = settings.LLM_RETRY_DELAY * (2**attempt)  # 指数退避
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise
    if last_error is None:
        raise RuntimeError("Unexpected state: no error but loop exhausted")
    raise last_error


def verify_session_ownership(session: Session, user: TokenPayload) -> None:
    """验证会话所有权，仅允许会话所有者访问"""
    if session.user_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此会话",
        )


@router.get("")
async def list_sessions(
    skip: int = Query(0, ge=0, description="跳过的会话数量"),
    limit: int = Query(20, ge=1, le=100, description="返回的会话数量"),
    status: Optional[str] = Query(None, description="状态过滤: active 或 archived"),
    project_id: Optional[str] = Query(None, description="项目过滤: 项目ID 或 'none'(未分类)"),
    search: Optional[str] = Query(None, description="搜索关键词，模糊匹配会话名称"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出会话

    普通用户只能看到自己的会话，管理员可以看到所有会话。

    Args:
        project_id: 可选的项目过滤
                   - 不传: 返回所有会话
                   - "none": 返回未分类的会话
                   - 项目ID: 返回该项目内的会话

    Returns:
        {
            "sessions": [...],
            "total": 总数量,
            "skip": 跳过数量,
            "limit": 请求的限制,
            "has_more": 是否有更多数据
        }
    """
    manager = SessionManager()

    # 确定过滤条件
    is_active = None
    if status == "active":
        is_active = True
    elif status == "archived":
        is_active = False

    # 所有用户只能查看自己的会话
    filter_user_id = user.sub

    sessions, total = await manager.list_sessions(
        user_id=filter_user_id,
        skip=skip,
        limit=limit,
        is_active=is_active,
        project_id=project_id,
        search=search,
    )

    return {
        "sessions": sessions,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(sessions)) < total,
    }


@router.post("", response_model=Session)
async def create_session(
    session_data: SessionCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建会话

    会话自动关联到当前认证用户。
    """
    manager = SessionManager()
    return await manager.create_session(session_data, user_id=user.sub)


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话

    只能获取自己拥有的会话，管理员可以获取任意会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)
    return session


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除会话

    只能删除自己拥有的会话，管理员可以删除任意会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    success = await manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    # 清理延迟工具发现记录
    try:
        from src.infra.tool.deferred_manager import clear_discovered_tools

        await clear_discovered_tools(session_id)
    except Exception:
        pass

    return {"status": "deleted"}


@router.post("/{session_id}/mark-read")
async def mark_session_read(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """将会话标记为已读（清除未读计数）"""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    await manager.mark_read(session_id)
    return {"status": "ok"}


@router.get("/{session_id}/events")
async def get_session_events(
    session_id: str,
    event_types: Optional[str] = Query(
        None, description="事件类型过滤，逗号分隔，如: message,thinking,tool_use"
    ),
    run_id: Optional[str] = Query(None, description="Run ID 过滤（用于获取特定对话轮次的事件）"),
    exclude_run_id: Optional[str] = Query(
        None, description="排除的 Run ID（用于排除正在运行的 run）"
    ),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话所有事件

    只能获取自己拥有的会话事件。

    Args:
        session_id: 会话 ID
        event_types: 可选的事件类型过滤（逗号分隔）
        run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
        exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
    """
    from src.infra.session.dual_writer import get_dual_writer

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()

    # 解析事件类型过滤
    types_list = None
    if event_types:
        types_list = [t.strip() for t in event_types.split(",") if t.strip()]

    # 重要：completed_only=True，确保正在运行的 trace 中的事件不要被返回，而是单独去请求/stream接口，避免重复返回事件，导致前端消息重复显示。
    # 否则刷新页面时，当前 run 的 user:message 事件会丢失，导致消息合并
    events = await dual_writer.read_session_events(
        session_id,
        types_list,
        run_id=run_id,
        exclude_run_id=exclude_run_id,
        completed_only=True,
    )

    # 获取 session 的 current_run_id 用于响应
    current_run_id = session.metadata.get("current_run_id") if session.metadata else None

    return {
        "events": events,
        "session_id": session_id,
        "run_id": run_id or current_run_id,
    }


@router.get("/{session_id}/runs")
async def get_session_runs(
    session_id: str,
    limit: int = Query(50, description="最大返回数量"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的所有 runs（对话轮次）

    每个 run 代表一轮独立的对话。

    Args:
        session_id: 会话 ID
        limit: 最大返回数量
    """
    from src.infra.session.dual_writer import get_dual_writer
    from src.infra.session.trace_storage import get_trace_storage

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    # 获取traces基本信息
    dual_writer = get_dual_writer()
    traces = await dual_writer.list_traces(session_id=session_id, limit=limit)

    # 获取trace_storage来查询用户消息
    trace_storage = get_trace_storage()

    # 转换为 run 摘要格式
    runs = []
    for trace in traces:
        run_id = trace.get("run_id")
        trace_id = trace.get("trace_id")
        # 查询该run的第一个用户消息
        user_message = None
        if run_id and trace_id:
            events = await trace_storage.get_trace_events(trace_id=trace_id)
            for event in events:
                if event.get("event_type") == "user:message":
                    data = event.get("data", {})
                    user_message = data.get("content") or data.get("message") or ""
                    if user_message:
                        # 截断过长消息
                        if len(user_message) > 20:
                            user_message = user_message[:17] + "..."
                        break

        runs.append(
            {
                "run_id": run_id,
                "trace_id": trace.get("trace_id"),
                "agent_id": trace.get("agent_id"),
                "started_at": trace.get("started_at"),
                "completed_at": trace.get("completed_at"),
                "status": trace.get("status"),
                "event_count": trace.get("event_count", 0),
                "user_message": user_message,
            }
        )

    return {
        "session_id": session_id,
        "runs": runs,
        "count": len(runs),
    }


@router.get("/{session_id}/traces")
async def get_session_traces(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的所有 traces（调试用）

    只能获取自己拥有的会话 traces。
    """
    from src.infra.session.dual_writer import get_dual_writer

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()
    traces = await dual_writer.list_traces(session_id=session_id, limit=100)

    return {"traces": traces, "session_id": session_id}


@router.get("/{session_id}/raw-traces")
async def get_session_raw_traces(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的原始 traces 数据（包含 events）
    """
    from src.infra.session.trace_storage import get_trace_storage

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    trace_storage = get_trace_storage()

    # 直接查询 MongoDB
    cursor = trace_storage.collection.find({"session_id": session_id}, {"_id": 0})
    traces = await cursor.to_list(length=100)

    return {"session_id": session_id, "traces": traces, "count": len(traces)}


@router.patch("/{session_id}/status")
async def update_session_status(
    session_id: str,
    status: str = Query(..., description="新状态: active 或 archived"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新会话状态

    只能更新自己拥有的会话状态。
    """
    if status not in ["active", "archived"]:
        raise HTTPException(status_code=400, detail="状态必须是 active 或 archived")

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    is_active = status == "active"
    updated_session = await manager.update_session(
        session_id,
        SessionUpdate(metadata={"is_active": is_active}),
    )
    if not updated_session:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"status": "updated", "session": updated_session}


@router.post("/{session_id}/clear-messages")
async def clear_session_messages(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    清空会话消息

    只能清空自己拥有的会话消息。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    released_attachments = await manager.clear_session_messages(session_id)
    return {"status": "cleared", "released_attachments": released_attachments}


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新会话信息（如名称）

    只能更新自己拥有的会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    updated_session = await manager.update_session(session_id, session_data)
    if not updated_session:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"status": "updated", "session": updated_session}


@router.post("/{session_id}/generate-title")
async def generate_session_title(
    session_id: str,
    message: str = Query(..., description="用户消息内容，用于生成标题"),
    lang: str = Query("en", description="语言代码: en, zh, ja, ko"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    根据用户消息自动生成标题

    使用 LLM 根据用户消息生成一个简短的会话标题。
    支持通过 settings 自定义模型和提示词。
    """
    from src.infra.llm.client import LLMClient

    # 验证语言参数白名单
    if lang not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language code: {lang}, falling back to 'en'")
        lang = "en"

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    if not message or not message.strip():
        return {"title": "新对话", "session_id": session_id}

    title_model = settings.SESSION_TITLE_MODEL
    title_api_base = settings.SESSION_TITLE_API_BASE or None
    title_api_key = settings.SESSION_TITLE_API_KEY or None
    prompt_template = settings.SESSION_TITLE_PROMPT

    # 使用 LLM 生成标题
    try:
        model = await LLMClient.get_model(
            model=title_model,
            api_base=title_api_base,
            api_key=title_api_key,
            max_tokens=100,
            max_retries=settings.LLM_MAX_RETRIES,
        )
        prompt = prompt_template.replace("{lang}", lang).replace("{message}", message[:800])

        response = await _ainvoke_with_retry(model, prompt)
        logger.debug("LLM 生成标题响应: %s", response)

        # 提取标题，兼容新旧格式
        content = response.content
        if isinstance(content, list):
            # 新格式：content 是列表，提取 type 为 'text' 的部分
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    title = str(item.get("text", "")).strip()
                    break
            else:
                title = str(content[0]).strip() if content else ""
        else:
            # 旧格式：content 直接是字符串
            title = str(content).strip()

        title = title.strip('"').strip("'")

        # 限制标题长度
        if len(title) > 30:
            title = title[:27] + "..."

        # 更新 session 名称
        await manager.update_session(session_id, SessionUpdate(name=title))

        return {"title": title, "session_id": session_id}
    except Exception as e:
        # 如果生成失败，使用消息的前几个字作为标题
        fallback_title = message[:20]
        if len(message) > 20:
            fallback_title += "..."
        await manager.update_session(session_id, SessionUpdate(name=fallback_title))
        return {"title": fallback_title, "session_id": session_id, "error": str(e)}


@router.post("/{session_id}/move")
async def move_session(
    session_id: str,
    body: dict,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    移动会话到项目

    将会话移动到指定项目，或设置为未分类。

    Args:
        session_id: 会话ID
        body: {"project_id": "xxx" 或 null}

    Returns:
        {"status": "moved", "session": updated_session}
    """
    from src.infra.folder.storage import get_project_storage

    manager = SessionManager()
    storage = SessionStorage()

    # Verify session exists and belongs to user
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    # Get project_id from body
    project_id = body.get("project_id")

    # If project_id provided (not null), verify project exists and belongs to user
    if project_id is not None:
        project_storage = get_project_storage()
        project = await project_storage.get_by_id(project_id, user.sub)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

    # Move session
    updated_session = await storage.move_to_project(session_id, user.sub, project_id)
    if not updated_session:
        raise HTTPException(status_code=500, detail="移动失败")

    # Sync revealed files' project_id
    try:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        revealed_storage = get_revealed_file_storage()
        await revealed_storage.update_project_id_by_session(session_id, project_id)
    except Exception as e:
        logger.warning(f"Failed to sync revealed files project_id: {e}")

    return {"status": "moved", "session": updated_session}
