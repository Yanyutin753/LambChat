"""
会话路由

所有会话操作都需要认证，用户只能访问自己的会话。
管理员可以访问所有会话。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required
from src.infra.session.manager import SessionManager
from src.kernel.config import settings
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = logging.getLogger(__name__)

# 管理员角色
ADMIN_ROLES = {"admin", "administrator"}


def is_admin(user: TokenPayload) -> bool:
    """检查用户是否为管理员"""
    return bool(ADMIN_ROLES & set(user.roles))


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
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出会话

    普通用户只能看到自己的会话，管理员可以看到所有会话。

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
        user_id=filter_user_id, skip=skip, limit=limit, is_active=is_active
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
    return {"status": "deleted"}


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

    # 重要：completed_only=False，确保正在运行的 trace 中的事件也被返回
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

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()
    traces = await dual_writer.list_traces(session_id=session_id, limit=limit)

    # 转换为 run 摘要格式
    runs = []
    for trace in traces:
        runs.append(
            {
                "run_id": trace.get("run_id"),
                "trace_id": trace.get("trace_id"),
                "agent_id": trace.get("agent_id"),
                "started_at": trace.get("started_at"),
                "completed_at": trace.get("completed_at"),
                "status": trace.get("status"),
                "event_count": trace.get("event_count", 0),
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

    # TODO: 实现消息清空
    # 目前只返回成功
    return {"status": "cleared"}


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
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    根据用户消息自动生成标题

    使用 LLM 根据用户消息生成一个简短的会话标题。
    支持通过 settings 自定义模型和提示词。
    """
    from src.infra.llm.client import LLMClient

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    if not message or not message.strip():
        return {"title": "新对话", "session_id": session_id}

    title_model = settings.SESSION_TITLE_MODEL
    prompt_template = settings.SESSION_TITLE_PROMPT

    # 使用 LLM 生成标题
    try:
        model = LLMClient.get_model(
            model=title_model,
            api_base=settings.LLM_API_BASE,
            api_key=settings.LLM_API_KEY,
        )
        prompt = prompt_template.format(message=message[:800])

        response = await model.ainvoke(prompt)
        print("LLM 生成标题响应:", response)

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
