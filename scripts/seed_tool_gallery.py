"""Seed display-only tool conversations in local desktop_dev; never execute tools or MCP.

Run: uv run python scripts/seed_tool_gallery.py
Only inserts owned sessions/traces. Existing conversations and MCP settings stay intact.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.seed_desktop_preview import preview_id, seed, validate_target
from src.kernel.schemas.session import Session


def tool_cases():
    """Each tuple is a visible group, tool name, synthetic arguments and result."""
    image = "/images/best-practice/chat-home.webp"
    return [
        (
            "01 文件与代码",
            "ls",
            {"path": "/workspace"},
            ["/workspace/report.md", "/workspace/data.csv"],
        ),
        (
            "01 文件与代码",
            "glob",
            {"pattern": "**/*.md", "path": "/workspace"},
            ["/workspace/report.md", "/workspace/README.md"],
        ),
        (
            "01 文件与代码",
            "grep",
            {"pattern": "delivery", "path": "/workspace", "output_mode": "content"},
            "/workspace/report.md:3: delivery complete",
        ),
        (
            "01 文件与代码",
            "read_file",
            {"file_path": "/workspace/report.md", "offset": 0, "limit": 10},
            "1  # 交付报告\n2  \n3  本周完成原型验证与体验检查。",
        ),
        (
            "01 文件与代码",
            "write_file",
            {"file_path": "/workspace/notes.md", "content": "# 验收记录\n\n布局检查完成。"},
            "Successfully wrote /workspace/notes.md",
        ),
        (
            "01 文件与代码",
            "edit_file",
            {
                "file_path": "/workspace/notes.md",
                "old_string": "布局检查完成",
                "new_string": "布局与键盘检查完成",
            },
            "Successfully edited /workspace/notes.md",
        ),
        (
            "01 文件与代码",
            "execute",
            {"command": 'python -c "print(128 + 156)"'},
            "284\nExit code: 0",
        ),
        (
            "01 文件与代码",
            "eval",
            {"code": "const totals = [128, 156]; return totals.reduce((a, b) => a + b, 0);"},
            {"result": 284},
        ),
        (
            "02 搜索与网页",
            "web_search",
            {"query": "产品交付验收清单"},
            {
                "results": [
                    {
                        "title": "交付验收指南（演示）",
                        "url": "https://example.com/guide",
                        "snippet": "检查目标、范围、负责人和验收证据。",
                    }
                ]
            },
        ),
        (
            "02 搜索与网页",
            "web_fetch",
            {"url": "https://example.com/guide"},
            "# 交付验收指南\n\n## 检查清单\n- 明确范围\n- 验证结果\n\n仅为 Mock 内容。",
        ),
        (
            "02 搜索与网页",
            "search_tools",
            {"query": "检索项目资料"},
            "Found 2 tool(s). Loaded 2 new; 0 already available.\n\n"
            "## preview_research:search\nDescription: 检索项目的计划、验收记录与研究资料。\n\n"
            "## preview_research:open_document\nDescription: 打开资料并读取引用段落。",
        ),
        (
            "02 搜索与网页",
            "search_skills",
            {"query": "产品设计"},
            "Name: design-review-demo\nDescription: 检查信息层级、对齐和交互反馈。\n"
            "Path: /skills/design-review-demo/SKILL.md\nTags: 设计, 可读性, 验收\n\n"
            "Name: delivery-checklist-demo\nDescription: 整理交付范围与验证记录。\n"
            "Path: /skills/delivery-checklist-demo/SKILL.md\nTags: 交付, 验证",
        ),
        (
            "02 搜索与网页",
            "search_conversation_history",
            {"query": "交付计划"},
            {
                "items": [
                    {
                        "session_id": "mock-session",
                        "session_name": "季度交付复盘",
                        "user_message_preview": "这轮交付优先验证哪些路径？",
                        "assistant_final_preview": "整理了三个验收重点。",
                    }
                ]
            },
        ),
        (
            "02 搜索与网页",
            "get_conversation_detail",
            {"session_id": "mock-session"},
            {
                "session": {"name": "季度交付复盘"},
                "turns": [
                    {
                        "user_message": "这轮优先做什么？",
                        "assistant_final": "先验证核心路径，再处理边界情况。",
                    }
                ],
            },
        ),
        (
            "03 图片音频与文档",
            "image_generate",
            {"prompt": "一个简洁的工作区界面", "size": "1024x1024"},
            {"images": [{"url": image}], "url": image, "model": "mock-image"},
        ),
        (
            "03 图片音频与文档",
            "image_edit_with_references",
            {"prompt": "保留布局并调整留白", "input_images": [image]},
            {"images": [{"url": image}], "url": image},
        ),
        (
            "03 图片音频与文档",
            "image_analyze",
            {"image_urls": [image], "prompt": "描述界面层级"},
            "## 界面分析\n\n侧栏用于导航，主区域展示消息和附件，操作按钮位于右侧。",
        ),
        (
            "03 图片音频与文档",
            "video_analyze",
            {"video_url": "https://example.com/mock-demo.mp4", "prompt": "总结操作步骤"},
            "演示结果：打开对话、查看文件、展开项目。未请求外部视频。",
        ),
        (
            "03 图片音频与文档",
            "audio_transcribe",
            {"url": "https://example.com/mock-meeting.wav", "language": "zh"},
            {"text": "本周完成需求梳理，下周安排原型验证。", "language": "zh", "duration": 12},
        ),
        (
            "03 图片音频与文档",
            "document_parse",
            {"url": "https://example.com/mock-report.pdf", "pages": "1-2"},
            {
                "markdown": "# 项目报告\n\n| 阶段 | 状态 |\n|---|---|\n| 原型验证 | 完成 |",
                "pages": 2,
            },
        ),
        (
            "04 交付与传输",
            "upload_url_to_sandbox",
            {"url": "https://example.com/mock.csv", "file_path": "/workspace/data.csv"},
            {"path": "/workspace/data.csv", "size": 128, "success": True},
        ),
        (
            "04 交付与传输",
            "transfer_file",
            {"source_path": "/workspace/report.md", "target_path": "/deliverables/report.md"},
            {"success": True, "size": 256, "target_path": "/deliverables/report.md"},
        ),
        (
            "04 交付与传输",
            "transfer_path",
            {"source_dir": "/workspace", "target_prefix": "/deliverables"},
            {"success": True, "file_count": 3, "transferred": 3},
        ),
        (
            "04 交付与传输",
            "reveal_file",
            {"path": "/workspace/workspace.webp"},
            {"key": "mock-workspace", "url": image, "name": "工作区预览.webp", "type": "image"},
        ),
        (
            "04 交付与传输",
            "reveal_project",
            {"path": "/workspace/demo"},
            {
                "type": "project_reveal",
                "name": "展示项目",
                "mode": "project",
                "template": "static",
                "entry": "/index.html",
                "file_count": 1,
                "files": {"/index.html": "<h1>Mock 项目</h1><p>仅用于界面预览。</p>"},
            },
        ),
        (
            "05 记忆与环境",
            "memory_recall",
            {"query": "交付偏好"},
            {
                "memories": [
                    {
                        "memory_id": "mock-memory",
                        "text": "用户偏好简洁且对齐的界面。",
                        "type": "user",
                        "source": "conversation",
                        "created_at": "2026-10-12T12:00:00Z",
                        "score": 0.94,
                    }
                ]
            },
        ),
        (
            "05 记忆与环境",
            "memory_retain",
            {"content": "演示偏好：清晰的信息层级。"},
            {"success": True, "id": "mock-memory", "content": "演示偏好：清晰的信息层级。"},
        ),
        (
            "05 记忆与环境",
            "memory_delete",
            {"memory_id": "mock-memory"},
            {"success": True, "deleted": 1},
        ),
        (
            "05 记忆与环境",
            "env_var_list",
            {},
            {"variables": [{"key": "DEMO_THEME", "value": "dark"}]},
        ),
        (
            "05 记忆与环境",
            "env_var_set",
            {"key": "DEMO_THEME", "value": "dark"},
            {"success": True, "key": "DEMO_THEME"},
        ),
        (
            "05 记忆与环境",
            "env_var_delete",
            {"key": "DEMO_THEME"},
            {"success": True, "key": "DEMO_THEME"},
        ),
        ("05 记忆与环境", "env_var_delete_all", {}, {"success": True, "deleted": 1}),
        *[
            (
                "06 定时任务与角色",
                name,
                {
                    "name": "每周交付复盘（Mock）",
                    "task_id": "mock-task",
                    "trigger_type": "cron",
                    "cron_expression": "0 9 * * 1",
                    "message": "整理交付进展",
                },
                {"success": True, "message": "仅为展示结果，不创建或更改定时任务", "tasks": []}
                if name.endswith("list")
                else {
                    "success": True,
                    "task": {
                        "id": "mock-task",
                        "name": "每周交付复盘（Mock）",
                        "enabled": False,
                        "trigger_type": "cron",
                        "cron_expression": "0 9 * * 1",
                    },
                },
            )
            for name in [
                "scheduled_task_create",
                "scheduled_task_list",
                "scheduled_task_update",
                "scheduled_task_delete",
            ]
        ],
        *[
            (
                "06 定时任务与角色",
                name,
                {
                    "name": "产品研究员（Mock）",
                    "description": "整理研究证据与下一步计划",
                    "system_prompt": "优先区分证据与假设。",
                },
                {
                    "success": True,
                    "preset": {
                        "name": "产品研究员（Mock）",
                        "id": "mock-persona",
                        "description": "整理研究证据，区分事实与假设，为交付提供可追溯的结论。",
                        "system_prompt": "优先检查来源与时间，输出关键证据、风险和下一步计划。",
                        "tags": ["研究", "交付"],
                        "starter_prompts": [
                            {"text": "整理本周交付的研究依据"},
                            {"text": "比较两种方案的收益与风险"},
                        ],
                    },
                },
            )
            for name in ["save_persona_preset", "create_persona_preset", "update_persona_preset"]
        ],
        (
            "06 定时任务与角色",
            "search_persona_presets",
            {"query": "研究员"},
            {"personas": [{"id": "mock-persona", "name": "产品研究员", "description": "整理证据"}]},
        ),
        (
            "06 定时任务与角色",
            "create_agent_team",
            {
                "name": "交付小组（Mock）",
                "members": [{"role_name": "研究员"}, {"role_name": "审阅员"}],
            },
            {
                "success": True,
                "name": "交付小组（Mock）",
                "members": [{"role_name": "研究员"}, {"role_name": "审阅员"}],
            },
        ),
        (
            "07 确认表单与电脑",
            "ask_human",
            {
                "message": "请选择下一轮验证范围（演示，已回答）",
                "fields": [
                    {
                        "name": "scope",
                        "type": "radio",
                        "label": "验证范围",
                        "options": ["桌面", "移动端"],
                        "required": True,
                    },
                    {"name": "notes", "type": "textarea", "label": "补充说明"},
                ],
            },
            {
                "status": "success",
                "message": "已收到演示回答",
                "values": {"scope": "桌面", "notes": "重点检查附件区"},
            },
        ),
        (
            "07 确认表单与电脑",
            "computer_use",
            {"action": "apps"},
            {"apps": [{"pid": 42, "name": "演示编辑器", "bundle_id": "local.mock.editor"}]},
        ),
        (
            "07 确认表单与电脑",
            "computer_use",
            {"action": "state", "pid": 42},
            {
                "tree": "1 window 演示编辑器\n  2 button 保存\n  3 text area 验收记录",
                "screenshot": {"url": image},
            },
        ),
        (
            "09 Todo 与子代理",
            "send_parent_message",
            {"message": "权限审查已完成，等待父代理汇总"},
            {
                "subagent_id": "mock-researcher",
                "submission_id": "mock-parent-message",
                "status": "queued",
            },
        ),
        (
            "09 Todo 与子代理",
            "send_subagent_message",
            {"subagent_id": "mock-researcher", "message": "补充核对移动端布局"},
            {"subagent_id": "mock-researcher", "status": "running"},
        ),
        (
            "09 Todo 与子代理",
            "wait_subagent",
            {"subagent_id": "mock-researcher"},
            {"subagent_id": "mock-researcher", "status": "completed", "result": "移动端检查完成"},
        ),
        (
            "09 Todo 与子代理",
            "list_subagents",
            {},
            {"subagents": [{"subagent_id": "mock-researcher", "status": "completed"}]},
        ),
        (
            "09 Todo 与子代理",
            "cancel_subagent",
            {"subagent_id": "mock-reviewer"},
            {"subagent_id": "mock-reviewer", "status": "cancelled"},
        ),
        (
            "09 Todo 与子代理",
            "start_background_task",
            {"description": "后台整理验收记录，完成后通知我"},
            {
                "task_id": "mock-background-task",
                "session_id": "mock-background-session",
                "run_id": "mock-background-run",
                "parent_session_id": "mock-parent-session",
                "execution_mode": "arq",
                "status": "queued",
            },
        ),
        ("08 异常与空结果", "web_search", {"query": "不存在的模拟资料"}, {"results": []}),
        (
            "08 异常与空结果",
            "ask_human",
            {"message": "确认演示操作", "fields": []},
            {"status": "rejected", "message": "用户取消了本次演示", "values": {}},
        ),
        (
            "08 异常与空结果",
            "execute",
            {"command": "mock-failed-command"},
            "ERROR: 模拟命令失败；没有执行任何命令。",
        ),
    ]


def build_records(owner: str, now: datetime, mcp_names: list[str]):
    groups = defaultdict(list)
    for group, name, args, result in tool_cases():
        groups[group].append((name, args, result))
    for i, server in enumerate(sorted(set(mcp_names))):
        groups[f"10 自定义 MCP · 第 {i // 5 + 1} 组"].append(
            (
                f"{server}:preview_search",
                {"query": "本周交付资料", "limit": 3, "mock": True},
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"## 本周交付资料\n\n来源：{server}（Mock）\n\n### 1. 交付计划\n状态：已就绪。已整理交付范围、负责人和验收时间。\n\n### 2. 验证记录\n状态：待复核。桌面端已完成检查，移动端待确认。\n\n> 本内容为模拟结果，不代表服务已连接。",
                        }
                    ]
                },
            )
        )
    groups.setdefault("09 Todo 与子代理", [])
    records = {"sessions": [], "traces": []}
    for group_index, (group, cases) in enumerate(sorted(groups.items())):
        slug = f"tool-gallery-v1-{group}"
        sid = preview_id(owner, "sessions", slug)
        trace = f"tool-gallery:{sid}"
        run = trace + ":run"
        stamp = now + timedelta(milliseconds=group_index)
        session = Session(
            id=str(sid),
            user_id=owner,
            name=f"工具展示 · {group}",
            created_at=stamp,
            updated_at=stamp,
            task_status="completed",
            completed_at=stamp,
        ).model_dump()
        session.pop("id")
        session.update(_id=sid, session_id=str(sid), preview_owner=owner)
        records["sessions"].append(session)
        events = []

        def emit(kind, data, **extra):
            events.append(
                {
                    "id": f"{trace}:{len(events)}",
                    "event_type": kind,
                    "run_id": run,
                    "data": {"run_id": run, **data},
                    "timestamp": stamp + timedelta(milliseconds=len(events) * 100),
                    **extra,
                }
            )

        emit(
            "user:message",
            {
                "content": f"展示「{group}」的工具调用样式。",
                "message_id": run + ":user",
                "attachments": [],
                "agent_id": "fast",
            },
        )
        emit(
            "metadata",
            {
                "session_id": str(sid),
                "trace_id": trace,
                "agent_id": "fast",
                "agent_name": "Fast Agent",
            },
        )
        emit(
            "message:chunk",
            {
                "content": f"## {group}\n\n以下全部是本地 Mock 展示数据，工具没有实际执行，配置没有被修改。点击工具可查看参数和结果。\n\n",
                "text_id": run + ":intro",
                "message_id": run + ":assistant",
                "agent_id": "fast",
            },
        )
        for index, (name, args, result) in enumerate(cases):
            call = f"{run}:tool:{index}"
            emit(
                "tool:start", {"tool": name, "tool_call_id": call, "args": args, "agent_id": "fast"}
            )
            emit(
                "tool:result",
                {
                    "tool": name,
                    "tool_call_id": call,
                    "result": result
                    if isinstance(result, str) or ":preview_search" in name
                    else json.dumps(result, ensure_ascii=False),
                    "success": not (isinstance(result, str) and result.startswith("ERROR:")),
                    "agent_id": "fast",
                },
            )
        if group.startswith("09"):
            emit(
                "todo:updated",
                {
                    "todos": [
                        {"content": "整理需求", "status": "completed"},
                        {"content": "验证布局", "status": "completed"},
                        {"content": "记录反馈", "status": "completed"},
                    ]
                },
            )
            emit(
                "agent:call",
                {"agent_name": "演示研究员", "input": "检查附件列表的信息层级", "step": 1},
                agent_id="mock-researcher",
                depth=1,
            )
            emit(
                "agent:result",
                {"result": "演示结论：图标、文件名与操作按钮应各自对齐。", "success": True},
                agent_id="mock-researcher",
                depth=1,
            )
        emit(
            "message:chunk",
            {
                "content": "\n\n展示结束。以上结果均为模拟数据。",
                "text_id": run + ":outro",
                "message_id": run + ":assistant",
                "agent_id": "fast",
            },
        )
        emit("done", {})
        records["traces"].append(
            {
                "_id": preview_id(owner, "traces", slug),
                "preview_owner": owner,
                "trace_id": trace,
                "session_id": str(sid),
                "agent_id": "fast",
                "run_id": run,
                "user_id": owner,
                "events": events,
                "event_count": len(events),
                "event_revision": 1,
                "started_at": stamp,
                "updated_at": stamp,
                "completed_at": stamp,
                "status": "completed",
                "metadata": {"merged": True},
            }
        )
    return records


def main():
    from src.infra.storage.mongodb import build_mongo_connection_string, get_mongo_sync_client
    from src.kernel.config import settings

    validate_target(build_mongo_connection_string(), settings.MONGODB_DB, "desktop_dev")
    db = get_mongo_sync_client()[settings.MONGODB_DB]
    user = db.users.find_one({"username": "desktop_dev"}, {"_id": 1})
    if not user:
        raise SystemExit("Existing desktop_dev account required")
    owner = str(user["_id"])
    servers = [d["name"] for d in db.user_mcp_servers.find({"user_id": owner}, {"name": 1})]
    records = build_records(owner, datetime.now(timezone.utc), servers)
    seed(db, owner, records)
    for session in records["sessions"]:
        print(f"{session['name']}: http://127.0.0.1:3001/chat/{session['session_id']}")
    print(
        f"Coverage: {len({c[1] for c in tool_cases()})} tool names, {len(servers)} MCP configs, Todo and subagent events"
    )


if __name__ == "__main__":
    main()
