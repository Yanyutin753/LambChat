"""Insert local mock chats for role selection and persistent subagent conversations.

Run: uv run python scripts/seed_subagent_preview.py
Uses the existing desktop_dev account and insert-only local preview safeguards.
Only synthetic sessions, traces and their local read-only share links are added.
No model, role, tool, MCP or subagent is executed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seed_desktop_preview import preview_id, seed, validate_target
from src.kernel.schemas.session import Session


def build_records(owner: str, now: datetime) -> dict[str, list[dict]]:
    records: dict[str, list[dict]] = {"sessions": [], "traces": [], "shared_sessions": []}
    for scenario, name in (
        ("role", "子代理演示 · 选角色、运行中发消息、完成后续跑"),
        ("fallback", "子代理演示 · 通用代理回退与续跑失败"),
        ("parent", "子代理演示 · 给父代理发消息与继续执行"),
    ):
        slug = f"subagent-preview-v1-{scenario}"
        sid = str(preview_id(owner, "sessions", slug))
        child = f"subagent-demo-{scenario}-{sid[:12]}"
        role = f"persona:{preview_id(owner, 'persona_presets', slug)}"
        specialized = scenario != "fallback"
        rounds = 2 if specialized else 1
        for turn in range(rounds):
            stamp = now + timedelta(seconds=turn * 60)
            trace = f"subagent-preview:{sid}:{turn}"
            run = trace + ":run"
            events: list[dict] = []

            def emit(kind, **data):
                timestamp = stamp + timedelta(seconds=len(events))
                events.append(
                    {
                        "id": f"{trace}:{len(events)}",
                        "event_type": kind,
                        "run_id": run,
                        "timestamp": timestamp,
                        "data": {
                            "run_id": run,
                            "agent_id": "team",
                            "depth": 0,
                            "timestamp": timestamp.isoformat(),
                            **data,
                        },
                    }
                )

            def text(content, *, nested=False):
                emit(
                    "message:chunk",
                    content=content,
                    text_id=f"{run}:text:{len(events)}",
                    message_id=run + ":assistant",
                    **({"agent_id": child, "depth": 1} if nested else {}),
                )

            def start_tool(tool, args, *, nested=False):
                call = f"{run}:tool:{len(events)}"
                # Managed tasks use agent lifecycle events in the real stream.
                if tool == "task":
                    return call
                emit(
                    "tool:start",
                    tool=tool,
                    args=args,
                    tool_call_id=call,
                    **({"agent_id": child, "depth": 1} if nested else {}),
                )
                return call

            def result_tool(tool, call, result, *, success=True, nested=False):
                if tool == "task":
                    return
                emit(
                    "tool:result",
                    tool=tool,
                    tool_call_id=call,
                    result=json.dumps(result, ensure_ascii=False),
                    success=success,
                    **({"agent_id": child, "depth": 1} if nested else {}),
                )

            def start_child(description, *, generic=False):
                emit(
                    "agent:call",
                    agent_id=child,
                    depth=1,
                    agent_name="通用代理" if generic else "API 契约审查助手",
                    input=description,
                )

            def finish_child(result):
                emit("agent:result", agent_id=child, depth=1, result=result, success=True)

            emit(
                "user:message",
                message_id=run + ":user",
                attachments=[],
                content=(
                    "继续让刚才的审查助手处理：记住上一轮的编号，补充最小复现和验收步骤。"
                    if turn
                    else "先找合适的角色，审查接口权限与错误码；运行中再让它只检查权限。"
                    if specialized
                    else "帮我整理离线音频转写稿，先找角色，找不到再用通用代理。"
                ),
            )
            emit("metadata", session_id=sid, trace_id=trace, agent_name="Team Agent")
            if turn:
                text(
                    "继续使用上一轮的 **API 契约审查助手**，保留角色、SOP 和历史记录。以下为本地 Mock 演示。"
                )
                instruction = "沿用上一轮 QC-DEMO-42，只检查权限；补充最小复现与验收步骤。"
                call = start_tool(
                    "send_subagent_message",
                    {"subagent_id": child, "message": instruction, "background": False},
                )
                start_child(instruction)
                text(
                    "我记得上一轮编号 **QC-DEMO-42**，范围已收窄为权限检查。\n\n1. 使用普通账户请求另一用户的资源。\n2. 预期返回 403，且响应不含资源内容。\n3. 使用资源所有者重试，预期成功。",
                    nested=True,
                )
                outcome = "已沿用 QC-DEMO-42，补充普通账户、所有者与管理员三类权限验收步骤。"
                finish_child(outcome)
                result_tool(
                    "send_subagent_message",
                    call,
                    {"subagent_id": child, "status": "completed", "result": outcome},
                )
                text(
                    "**同一个子代理已完成续跑。**\n\n上一轮的编号 QC-DEMO-42 和权限范围都保留了；这轮没有重新搜索角色，也没有新建子代理。\n\n> 此会话是界面 Mock，不代表模型或工具在本次演示中真实执行。"
                )
            else:
                text(
                    "这是本地 **Mock 对话**，可点击工具和子代理卡片查看详情。\n\n先搜索角色，再加载匹配角色的原始系统提示词（SOP）执行任务。"
                )
                call = start_tool(
                    "search_persona_presets",
                    {
                        "query": "API 权限 契约审查" if specialized else "离线音频转写 排版",
                        "limit": 5,
                    },
                )
                result_tool(
                    "search_persona_presets",
                    call,
                    {
                        "presets": [
                            {
                                "id": role.removeprefix("persona:"),
                                "subagent_type": role,
                                "name": "API 契约审查助手",
                                "description": "检查权限、错误码和接口兼容性",
                                "tags": ["工程", "审查"],
                            }
                        ]
                        if specialized
                        else [],
                    },
                )
                text(
                    "找到 **API 契约审查助手**，按该角色原始 SOP：先确认范围、记录证据，再给出可复现结论。"
                    if specialized
                    else "角色搜索成功，但没有匹配项，使用 **通用代理**。"
                )
                description = (
                    "审查接口权限与错误码，使用 QC-DEMO-42 记录本轮结果。"
                    if specialized
                    else "整理模拟转写稿，保留发言人和时间点。"
                )
                call = start_tool(
                    "task",
                    {
                        "description": description,
                        "subagent_type": role if specialized else "general-purpose",
                        "background": specialized,
                    },
                )
                start_child(description, generic=not specialized)
                if specialized:
                    result_tool("task", call, {"subagent_id": child, "status": "running"})
                    text(
                        "已按角色 SOP 开始审查，编号 **QC-DEMO-42**。当前正在核对权限边界。",
                        nested=True,
                    )
                    if scenario == "parent":
                        waiting = start_tool("wait_subagent", {"subagent_id": child})
                        question = "QC-DEMO-42：是否只检查权限，暂时跳过错误码？"
                        sent = start_tool("send_parent_message", {"message": question}, nested=True)
                        acknowledgement = {"subagent_id": child, "status": "queued"}
                        result_tool("send_parent_message", sent, acknowledgement, nested=True)
                        received = start_tool(
                            "send_parent_message",
                            {
                                "subagent_id": child,
                                "message": question,
                                "direction": "received",
                            },
                        )
                        result_tool("send_parent_message", received, acknowledgement)
                        result_tool(
                            "wait_subagent",
                            waiting,
                            {
                                "subagent_id": child,
                                "status": "running",
                                "messages_pending": True,
                            },
                        )
                        text("已收到子代理的范围确认，回复同一个子代理后继续等待。")
                    text("子代理仍在运行，向这个 ID 追加要求：**只检查权限，暂时跳过错误码**。")
                    call = start_tool(
                        "send_subagent_message",
                        {
                            "subagent_id": child,
                            "message": "只检查权限，暂时跳过错误码；保留 QC-DEMO-42。",
                        },
                    )
                    result_tool(
                        "send_subagent_message", call, {"subagent_id": child, "status": "running"}
                    )
                    text(
                        "已收到追加要求，范围调整为 **权限检查**，继续保留 QC-DEMO-42。",
                        nested=True,
                    )
                    call = start_tool("wait_subagent", {"subagent_id": child})
                    outcome = "QC-DEMO-42：权限审查已完成，需补充跨用户资源访问的 403 验收。"
                    finish_child(outcome)
                    result_tool(
                        "wait_subagent",
                        call,
                        {"subagent_id": child, "status": "completed", "result": outcome},
                    )
                    text(
                        "**第一轮已完成。**\n\n- 先搜索并选择角色，加载原始 SOP。\n- 运行中追加要求，子代理收窄为权限检查。\n- 结果编号：**QC-DEMO-42**。\n\n下一条消息展示完成后继续给它发信息。"
                    )
                else:
                    outcome = "模拟转写稿已整理为按时间排序的发言记录。"
                    text(outcome, nested=True)
                    finish_child(outcome)
                    result_tool(
                        "task",
                        call,
                        {"subagent_id": child, "status": "completed", "result": outcome},
                    )
                    call = start_tool(
                        "send_subagent_message",
                        {"subagent_id": child, "message": "继续补充会议行动项。"},
                    )
                    result_tool(
                        "send_subagent_message",
                        call,
                        {
                            "subagent_id": child,
                            "status": "error",
                            "error": "模拟续跑失败：子代理暂时不可用，请重试。",
                        },
                        success=False,
                    )
                    text(
                        "已有整理结果保留。**本次续跑失败**，可检查错误详情并重试。\n\n> 此会话同时展示搜索无匹配后的通用代理回退，以及失败工具的专属消息样式；全部为 Mock 数据。"
                    )
            emit("done")
            finished = events[-1]["timestamp"]
            records["traces"].append(
                {
                    "_id": preview_id(owner, "traces", f"{slug}-{turn}"),
                    "preview_owner": owner,
                    "trace_id": trace,
                    "session_id": sid,
                    "agent_id": "team",
                    "run_id": run,
                    "user_id": owner,
                    "events": events,
                    "event_count": len(events),
                    "event_revision": 1,
                    "started_at": stamp,
                    "updated_at": finished,
                    "completed_at": finished,
                    "status": "completed",
                    "metadata": {"merged": True},
                }
            )
        session = Session(
            id=sid,
            name=name,
            user_id=owner,
            agent_id="team",
            created_at=now,
            updated_at=finished,
            completed_at=finished,
            task_status="completed",
            metadata={"preview": "subagent-mock"},
        ).model_dump()
        session.pop("id")
        session.update(_id=preview_id(owner, "sessions", slug), session_id=sid, preview_owner=owner)
        records["sessions"].append(session)
        records["shared_sessions"].append(
            {
                "_id": preview_id(owner, "shared_sessions", slug),
                "preview_owner": owner,
                "share_id": f"subagent-demo-{sid}",
                "session_id": sid,
                "owner_id": owner,
                "share_scope": "session",
                "share_type": "full",
                "visibility": "public",
                "created_at": now,
                "updated_at": finished,
            }
        )
    return records


def main():
    from src.infra.storage.mongodb import build_mongo_connection_string, get_mongo_sync_client
    from src.kernel.config import settings

    validate_target(build_mongo_connection_string(), settings.MONGODB_DB, "desktop_dev")
    database = get_mongo_sync_client()[settings.MONGODB_DB]
    user = database.users.find_one({"username": "desktop_dev"}, {"_id": 1})
    if not user:
        raise SystemExit("Existing desktop_dev account required")
    owner = str(user["_id"])
    records = build_records(owner, datetime.now(timezone.utc))
    seed(database, owner, records)
    for session, share in zip(records["sessions"], records["shared_sessions"], strict=True):
        print(f"{session['name']}: http://localhost:3001/chat/{session['session_id']}")
        print(f"Read-only demo: http://localhost:3001/shared/{share['share_id']}")


if __name__ == "__main__":
    main()
