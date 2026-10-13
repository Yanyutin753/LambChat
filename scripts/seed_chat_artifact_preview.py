"""Add downloadable file and project demos to the existing local desktop_dev account.

Run: uv run python scripts/seed_chat_artifact_preview.py
Reuses the desktop preview's local-only and insert-only safeguards.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seed_desktop_preview import preview_id, seed, validate_target
from src.kernel.schemas.session import Session


def build_preview(owner: str, now: datetime) -> tuple[dict, dict[str, bytes]]:
    records: dict[str, list[dict]] = {"sessions": [], "traces": [], "file_records": []}
    files = {}
    names = [
        "交付计划.md",
        "季度交付数据.csv",
        "用户访谈复盘.md",
        "项目进度.csv",
        "发布验收清单.md",
        "长期研究资料与跨部门协作验证记录.md",
    ]
    for count in (1, 3, 6, 2):
        slug = f"chat-artifact-cards-v1-{count}"
        sid = preview_id(owner, "sessions", slug)
        trace = f"artifact-preview-{owner}-{count}"
        run = trace + ":run"
        session = Session(
            id=str(sid),
            user_id=owner,
            name="项目与文件预览 · 1 个项目 + 2 个文件"
            if count == 2
            else f"文件卡片预览 · {count} 个文件",
            created_at=now,
            updated_at=now,
            task_status="completed",
            completed_at=now,
        ).model_dump()
        session.pop("id")
        session.update(_id=sid, session_id=str(sid), preview_owner=owner)
        records["sessions"].append(session)
        events = [
            {
                "event_type": "user:message",
                "data": {
                    "content": f"整理这次交付的 {count} 个文件。",
                    "message_id": run + ":user",
                    "run_id": run,
                    "attachments": [],
                    "agent_id": "fast",
                },
                "timestamp": now,
            },
            {
                "event_type": "metadata",
                "data": {
                    "session_id": str(sid),
                    "trace_id": trace,
                    "run_id": run,
                    "agent_id": "fast",
                    "agent_name": "Fast Agent",
                },
                "timestamp": now,
            },
            {
                "event_type": "message:chunk",
                "data": {
                    "content": "交付资料已整理好，点击下方文件可预览内容，也可以直接下载。\n\n这是本地界面演示数据，用于查看文件卡片和多文件收纳效果。",
                    "text_id": run + ":assistant",
                    "message_id": run + ":assistant",
                    "run_id": run,
                    "agent_id": "fast",
                },
                "timestamp": now,
            },
        ]
        for index, name in enumerate(names[:count]):
            key = f"{owner}/chat-artifact-preview-v1/{count}/{name}"
            content = (
                f"阶段,完成率,备注\n需求确认,100%,{name}\n原型验证,85%,{count} 个文件示例\n发布验收,60%,待验证\n"
                if name.endswith(".csv")
                else f"# {name[:-3]}\n\n这是 {count} 个文件示例中的本地文件卡片预览资料。\n\n## 下一步\n\n- 确认需求和负责人\n- 完成原型验证\n- 记录验收结果\n"
            ).encode()
            files[key] = content
            records["file_records"].append(
                {
                    "_id": preview_id(owner, "file_records", f"{slug}-{index}"),
                    "preview_owner": owner,
                    "hash": hashlib.sha256(content).hexdigest(),
                    "key": key,
                    "name": name,
                    "mime_type": "text/csv" if name.endswith(".csv") else "text/markdown",
                    "size": len(content),
                    "category": "document",
                    "uploaded_by": owner,
                    "created_at": now,
                }
            )
            artifact = {
                "kind": "file",
                "id": trace + f":file-{index}",
                "name": name,
                "path": f"/交付资料/{name}",
                "fileSize": len(content),
                "preview": {
                    "kind": "file",
                    "previewKey": key,
                    "filePath": f"/交付资料/{name}",
                    "signedUrl": f"http://127.0.0.1:8000/api/upload/file/{key}",
                    "s3Key": key,
                },
            }
            events.append(
                {
                    "event_type": "artifact:result",
                    "data": {"artifact": artifact, "success": True, "run_id": run},
                    "timestamp": now,
                }
            )
        if count == 2:
            project_key = trace + ":project"
            project_files = {
                "/index.html": "<!doctype html><html lang='zh'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>交付计划</title><style>body{font:16px system-ui;margin:0;background:#f6f5f1;color:#292524}main{max-width:720px;margin:64px auto;padding:24px}h1{font-size:36px}article{padding:20px 0;border-top:1px solid #ddd}small{color:#78716c}</style><main><small>项目演示 · 本地数据</small><h1>季度交付计划</h1><p>将研究成果整理成可执行的下一步。</p><article><h2>01 需求确认</h2><p>明确目标用户、核心场景与验收标准。</p></article><article><h2>02 原型验证</h2><p>验证关键路径，记录反馈并迭代。</p></article></main></html>",
                "/README.md": "# 季度交付计划\n\n本地项目演示，包含可预览的静态页面与说明文件。\n",
            }
            events.append(
                {
                    "event_type": "artifact:result",
                    "data": {
                        "success": True,
                        "run_id": run,
                        "artifact": {
                            "kind": "project",
                            "id": project_key,
                            "name": "季度交付计划",
                            "mode": "project",
                            "fileCount": 2,
                            "template": "static",
                            "preview": {
                                "kind": "project",
                                "previewKey": project_key,
                                "project": {
                                    "version": 1,
                                    "name": "季度交付计划",
                                    "mode": "project",
                                    "template": "static",
                                    "path": "/季度交付计划",
                                    "entry": "/index.html",
                                    "fileCount": 2,
                                    "files": project_files,
                                },
                            },
                        },
                    },
                    "timestamp": now,
                }
            )
        events.append({"event_type": "done", "data": {"run_id": run}, "timestamp": now})
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
                "started_at": now,
                "updated_at": now,
                "completed_at": now,
                "status": "completed",
                "metadata": {"merged": True},
            }
        )
    return records, files


def main():
    from src.infra.storage.mongodb import build_mongo_connection_string, get_mongo_sync_client
    from src.kernel.config import settings

    validate_target(build_mongo_connection_string(), settings.MONGODB_DB, "desktop_dev")
    if settings.S3_ENABLED:
        raise SystemExit("Local storage required; remote uploads are never performed")
    database = get_mongo_sync_client()[settings.MONGODB_DB]
    user = database.users.find_one({"username": "desktop_dev"})
    if not user:
        raise SystemExit("Existing desktop_dev account required")
    owner = str(user["_id"])
    records, files = build_preview(owner, datetime.now(timezone.utc))
    storage = Path(settings.LOCAL_STORAGE_PATH).resolve()
    for key, content in files.items():
        path = storage / key
        if path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Existing preview file differs: {path.name}")
    seed(database, owner, records)
    for key, content in files.items():
        path = storage / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
    for session in records["sessions"]:
        print(f"{session['name']}: http://127.0.0.1:3001/chat/{session['session_id']}")


if __name__ == "__main__":
    main()
