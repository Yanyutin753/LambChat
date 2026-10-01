"""Seed actual local desktop_dev data. Run: uv run python scripts/seed_desktop_preview.py.

Only preview-owned documents are upserted. Existing auth/configuration is preserved.
Tasks, channels, MCP and model examples cannot execute. No external services are used.

Prerequisites: local MongoDB, existing desktop_dev user, local file storage. Launch
backend on 8000 and frontend on 3001, sign in as desktop_dev, then run this script.
It inserts 544 documents across 22 collections and 30 downloadable text documents.
Thirty distinct topics cover pagination, tags, long descriptions and linked chat
history. Six skills are disabled, twenty published, and three marked favorite.
Re-running uses $setOnInsert and preserves edits to existing preview documents.
Only preview skill names are added to the existing user's preference arrays.

Enable Memory in the local Settings panel to display native_memories (the default
is disabled). No system setting, existing credential, model key, or role grant is
modified by this script. Models are visible with include_disabled=true. The existing
Settings and Agent panels continue to display their real configuration. Sandbox
machines, OAuth connections and external provider connections are not fabricated.

Check: uv run pytest tests/scripts/test_seed_desktop_preview.py -q

"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId
from pymongo.uri_parser import parse_uri

from src.infra.memory.client.types import MemoryType
from src.infra.skill.types import MarketplaceSkill, SkillMeta
from src.kernel.schemas.bookmark import Bookmark
from src.kernel.schemas.feedback import Feedback
from src.kernel.schemas.file_record import FileRecordSchema
from src.kernel.schemas.mcp import UserMCPServer
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.notification import Notification
from src.kernel.schemas.persona_preset import PersonaPreset
from src.kernel.schemas.project import Project
from src.kernel.schemas.role import Role
from src.kernel.schemas.scheduled_task import ScheduledTask, TaskRunRecord
from src.kernel.schemas.session import Session
from src.kernel.schemas.team import TeamResponse
from src.kernel.schemas.usage import UsageLog
from src.kernel.schemas.user import UserInDB

# Distinct topics keep search, wrapping, tags and pagination useful during real UI QA.
TOPICS = [
    ("research-brief", "市场研究简报", "研究", "比较目标市场规模、客户需求与主要竞争对手"),
    ("release-plan", "秋季版本发布计划", "产品", "整理里程碑、依赖关系与发布验收标准"),
    ("customer-interviews", "客户访谈洞察", "研究", "归纳访谈证据，区分真实痛点与待验证假设"),
    ("api-review", "API 契约审查", "工程", "检查接口分页、错误码、权限与兼容性"),
    ("onboarding", "新用户引导优化", "产品", "减少首次操作阻力，明确下一步行动"),
    ("weekly-report", "团队周报", "运营", "汇总本周交付、风险与下周重点"),
    ("incident-review", "故障复盘", "工程", "梳理时间线、根因与可验证的改进措施"),
    ("brand-voice", "品牌文案指南", "设计", "保持清晰、友好且一致的产品表达"),
    ("accessibility", "无障碍体验检查", "设计", "核对键盘导航、焦点顺序和文字对比度"),
    ("sales-followup", "销售跟进准备", "运营", "整理客户背景、决策因素和下一次沟通议题"),
    ("data-quality", "数据质量巡检", "数据", "检查缺失值、异常分布和指标口径"),
    ("budget-plan", "季度预算草案", "财务", "拆分资源投入，记录估算依据与不确定性"),
    ("docs-cleanup", "开发文档整理", "工程", "修复过时示例，补全启动和排障路径"),
    ("support-faq", "客服知识库", "运营", "将常见问题整理成可检索的简洁答案"),
    ("architecture", "系统架构评审", "工程", "比较边界划分、部署成本与维护复杂度"),
    ("experiment", "增长实验设计", "数据", "定义假设、样本范围与成功判据"),
    ("hiring", "招聘面试提纲", "团队", "设计围绕真实工作能力的结构化问题"),
    ("meeting-notes", "项目会议纪要", "团队", "提取决定、负责人和明确截止日期"),
    ("localization", "多语言发布检查", "产品", "核对术语、长文本布局与区域格式"),
    ("security-review", "权限边界核查", "工程", "验证最小权限与敏感字段处理"),
    ("roadmap", "下一季度路线图", "产品", "按用户价值与工作量梳理优先顺序"),
    ("content-calendar", "内容发布日历", "运营", "规划主题、受众与素材准备时间"),
    ("performance", "性能基线分析", "工程", "比较响应延迟、吞吐量与资源占用"),
    ("design-tokens", "视觉规范整理", "设计", "统一颜色语义、排版层级和组件状态"),
    ("retention", "用户留存分析", "数据", "比较不同用户群的行为与流失原因"),
    ("contract-summary", "合同要点梳理", "财务", "标注义务、付款节点与需要人工复核的条款"),
    ("training", "新人培训材料", "团队", "将业务背景和常见操作编排成学习路径"),
    ("customer-success", "客户成功计划", "运营", "定义上线目标、使用指标与回访节奏"),
    ("knowledge-map", "领域知识地图", "研究", "连接核心概念、参考资料与开放问题"),
    ("launch-retro", "上线体验回顾", "产品", "汇总实际反馈并形成下一轮改进清单"),
]


def validate_target(uri: str, database: str, username: str) -> None:
    hosts = parse_uri(uri)["nodelist"]
    if (
        not hosts
        or any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in hosts)
        or database != "agent_state"
        or username != "desktop_dev"
    ):
        raise ValueError("Preview seed only supports local agent_state / desktop_dev")


def preview_id(owner: str, collection: str, key: str) -> ObjectId:
    return ObjectId(
        hashlib.sha256(f"desktop-preview-v1:{owner}:{collection}:{key}".encode()).digest()[:12]
    )


def preview_files(owner: str) -> dict[str, bytes]:
    files = {}
    for i, (slug, title, category, description) in enumerate(TOPICS):
        extension = ["md", "csv", "json", "txt"][i % 4]
        content = {
            "md": f"# {title}\n\n{description}。\n\n## 行动清单\n\n- 明确负责人\n- 收集证据\n- 安排复核\n",
            "csv": f"阶段,状态,交付物\n{title},已完成,研究摘要\n评审,待确认,行动清单\n",
            "json": json.dumps(
                {"title": title, "category": category, "summary": description, "preview": True},
                ensure_ascii=False,
                indent=2,
            ),
            "txt": f"{title}\n\n{description}。\n\n这是本地预览资料，不含真实业务数据。\n",
        }[extension]
        files[f"{owner}/desktop-preview/{slug}.{extension}"] = content.encode()
    return files


def build_records(owner: str, now: datetime) -> dict[str, list[dict]]:
    records: dict[str, list[dict]] = defaultdict(list)

    def ident(collection, key):
        return str(preview_id(owner, collection, str(key)))

    def add(collection, record_key, schema=None, **data):
        oid = preview_id(owner, collection, str(record_key))
        if schema:
            data = schema(id=str(oid), **data).model_dump(mode="python")
        if collection != "model_configs":
            data.pop("id", None)
        data["_id"] = str(oid) if collection in {"scheduled_tasks", "task_run_records"} else oid
        if collection == "sessions":
            data["session_id"] = str(oid)
        data["preview_owner"] = owner
        data["preview_seed"] = "desktop-preview-v1"
        records[collection].append(data)
        return str(oid)

    groups = ["产品与设计", "工程与质量", "数据与研究", "运营与增长", "团队与协作", "财务与规划"]
    for i, name in enumerate(groups):
        add(
            "projects",
            i,
            Project,
            name=f"{name} · 示例",
            user_id=owner,
            icon="Folder",
            sort_order=i,
            created_at=now - timedelta(days=30),
            updated_at=now,
        )
    for i, (slug, title, category, description) in enumerate(TOPICS):
        stamp = now - timedelta(hours=i * 7)
        dates = dict(created_at=stamp, updated_at=stamp)
        project = ident("projects", i % len(groups))
        persona = ident("persona_presets", slug)
        session = ident("sessions", slug)
        run = f"preview-{owner}-{slug}"
        trace = f"preview-trace-{owner}-{slug}"
        skill = f"preview-{slug}"
        text = f"## {title}\n\n{description}。\n\n### 本轮结论\n\n- 已整理主要证据与范围。\n- 待确认责任人和验收条件。\n- 下次评审优先处理高影响问题。\n\n| 阶段 | 状态 | 交付物 |\n| --- | --- | --- |\n| 调研 | 已完成 | 证据摘要 |\n| 评审 | 待确认 | 行动清单 |\n\n> 本内容为本地预览示例。"
        add(
            "sessions",
            slug,
            Session,
            name=f"{title} · 示例",
            user_id=owner,
            agent_id="fast",
            metadata={"project_id": project},
            task_status="completed",
            completed_at=stamp,
            unread_count=i % 4,
            **dates,
        )
        events = [
            {
                "event_type": "user:message",
                "data": {
                    "content": f"请帮我完成{title}，并给出可执行的下一步。",
                    "message_id": run + ":user",
                    "run_id": run,
                    "attachments": [],
                    "agent_id": "fast",
                },
                "timestamp": stamp,
            },
            {
                "event_type": "metadata",
                "data": {
                    "session_id": session,
                    "trace_id": trace,
                    "run_id": run,
                    "agent_id": "fast",
                    "agent_name": "Fast Agent",
                },
                "timestamp": stamp,
            },
            {
                "event_type": "message:chunk",
                "data": {
                    "content": text,
                    "text_id": run + ":assistant",
                    "message_id": run + ":assistant",
                    "run_id": run,
                    "agent_id": "fast",
                },
                "timestamp": stamp,
            },
            {"event_type": "done", "data": {"run_id": run}, "timestamp": stamp},
        ]
        add(
            "traces",
            slug,
            trace_id=trace,
            session_id=session,
            agent_id="fast",
            run_id=run,
            user_id=owner,
            events=events,
            event_count=len(events),
            event_revision=1,
            started_at=stamp,
            updated_at=stamp,
            completed_at=stamp + timedelta(seconds=8),
            status="completed",
            metadata={"merged": True},
        )
        add(
            "persona_presets",
            slug,
            PersonaPreset,
            name=f"{title}助手",
            description=description,
            scope="user",
            owner_user_id=owner,
            visibility="private",
            status="published",
            system_prompt=f"你协助{description}。这是本地预览角色。",
            tags=[category, "预览"],
            starter_prompts=[{"text": f"帮我制定{title}的工作清单"}],
            skill_names=[skill],
            **dates,
        )
        add(
            "skill_files",
            slug,
            skill_name=skill,
            user_id=owner,
            file_path="SKILL.md",
            content=f"---\nname: {skill}\ndescription: {description}\ntags: [{category}, 预览]\n---\n\n# {title}\n\n仅供本地预览。{description}。\n\n1. 确认背景与目标。\n2. 整理证据。\n3. 给出下一步。",
            created_at=stamp.isoformat(),
            updated_at=stamp.isoformat(),
        )
        skill_content = records["skill_files"][-1]["content"]
        add(
            "skill_files",
            slug + "-meta",
            skill_name=skill,
            user_id=owner,
            file_path="__meta__",
            content=SkillMeta(
                installed_from="manual",
                published_marketplace_name=skill if i < 20 else None,
                created_at=stamp.isoformat(),
                updated_at=stamp.isoformat(),
            ).model_dump_json(),
            created_at=stamp.isoformat(),
            updated_at=stamp.isoformat(),
        )
        add(
            "skill_marketplace",
            slug,
            MarketplaceSkill,
            skill_name=skill,
            description=description,
            tags=[category, "预览"],
            version=f"1.{i % 4}.0",
            created_by=owner,
            is_active=i % 6 != 0,
            created_at=stamp.isoformat(),
            updated_at=stamp.isoformat(),
        )
        add(
            "skill_marketplace_files",
            slug,
            skill_name=skill,
            file_path="SKILL.md",
            content=skill_content,
            created_at=stamp.isoformat(),
            updated_at=stamp.isoformat(),
        )
        add(
            "native_memories",
            slug,
            user_id=owner,
            memory_id=hashlib.md5(run.encode()).hexdigest(),
            content=f"预览资料：{description}。输出应包含结论、依据和待确认事项。",
            title=title,
            summary=description,
            tags=[category, "预览"],
            memory_type=list(MemoryType)[i % len(MemoryType)].value,
            scope="user",
            source="manual",
            content_storage_mode="inline",
            access_count=i,
            **dates,
        )
        add(
            "bookmarks",
            slug,
            Bookmark,
            user_id=owner,
            session_id=session,
            message_id=run + ":assistant",
            run_id=run,
            label=title,
            created_at=stamp,
        )
        add(
            "feedback",
            slug,
            Feedback,
            user_id=owner,
            username="desktop_dev",
            session_id=session,
            run_id=run,
            rating="down" if i % 4 == 0 else "up",
            comment=["建议补充数据来源", "结构清晰，下一步明确", "希望增加一个具体示例"][i % 3],
            created_at=stamp,
        )
        add(
            "usage_logs",
            slug,
            UsageLog,
            trace_id=trace,
            session_id=session,
            user_id=owner,
            username="desktop_dev",
            agent_name="Fast Agent",
            model=["preview-reasoning", "preview-fast", "preview-vision"][i % 3],
            input_tokens=1200 + i * 317,
            output_tokens=650 + i * 91,
            total_tokens=1850 + i * 408,
            cost_usd=round(0.008 + i * 0.0023, 5),
            cost_available=True,
            duration=8 + i * 1.3,
            started_at=stamp,
            completed_at=stamp + timedelta(seconds=8),
            status="completed",
        )
        task = add(
            "scheduled_tasks",
            slug,
            ScheduledTask,
            name=f"{title} · 已暂停示例",
            description=description,
            agent_id="fast",
            trigger_type="cron",
            trigger_config={"hour": str(8 + i % 10), "minute": "0", "day_of_week": "mon-fri"},
            timezone="Asia/Shanghai",
            input_payload={"message": description},
            owner_id=owner,
            status="paused",
            enabled=False,
            last_run_status="failed" if i % 5 == 0 else "success",
            total_runs=3 + i,
            last_run_at=stamp,
            source_session_id=session,
            **dates,
        )
        add(
            "task_run_records",
            slug,
            TaskRunRecord,
            task_id=task,
            agent_id="fast",
            status="failed" if i % 5 == 0 else "success",
            session_id=session,
            trace_id=trace,
            output_result={"text": description},
            error_message="示例：上游暂时不可用" if i % 5 == 0 else None,
            started_at=stamp,
            finished_at=stamp + timedelta(seconds=8),
            created_at=stamp,
            duration_ms=8000,
        )
        if i < 30:
            add(
                "teams",
                slug,
                TeamResponse,
                name=f"{title}工作组",
                description=description,
                owner_user_id=owner,
                tags=[category, "预览"],
                members=[
                    {
                        "member_id": "researcher",
                        "persona_preset_id": persona,
                        "role_name": "研究员",
                        "agent_id": "fast",
                    },
                    {
                        "member_id": "reviewer",
                        "persona_preset_id": ident("persona_presets", TOPICS[(i + 1) % 30][0]),
                        "role_name": "审阅员",
                        "agent_id": "fast",
                    },
                ],
                default_member_id="researcher",
                **dates,
            )
        add(
            "user_mcp_servers",
            slug,
            UserMCPServer,
            name=skill,
            user_id=owner,
            transport="streamable_http",
            enabled=False,
            url=f"http://127.0.0.1:9/preview/{slug}",
            created_at=stamp.isoformat(),
            updated_at=stamp.isoformat(),
        )
    for i, name in enumerate(
        ["研究推理", "快速问答", "视觉理解", "长文阅读", "代码审阅", "多语言写作"]
    ):
        add(
            "model_configs",
            i,
            ModelConfig,
            value=f"preview-model-{i}",
            label=f"{name} · 禁用示例",
            provider=["openai", "anthropic", "google"][i % 3],
            description="本地列表预览，无密钥，不可调用",
            enabled=False,
            order=100 + i,
            created_at=now,
            updated_at=now,
        )
    for i, name in enumerate(["内容编辑", "项目观察员", "质量审阅员"]):
        role = add(
            "roles",
            i,
            Role,
            name=f"preview-{i}-{name}",
            description="本地预览角色，无授权",
            permissions=[],
            created_at=now,
            updated_at=now,
        )
        for j in range(4):
            add(
                "users",
                f"{i}-{j}",
                UserInDB,
                username=f"preview_{['mei', 'alex', 'sora'][i]}_{j}",
                email=f"preview-{i}-{j}@example.com",
                password_hash="!disabled-preview-account",
                roles=[role],
                is_active=False,
                email_verified=False,
                metadata={"display_name": ["林梅", "Alex Chen", "佐藤そら"][i]},
                created_at=now,
                updated_at=now,
            )
    for i, title in enumerate(
        ["欢迎体验本地工作空间", "知识库整理已完成", "定时任务示例已暂停", "预览环境维护说明"]
    ):
        add(
            "notifications",
            i,
            Notification,
            title_i18n={lang: title for lang in ["zh", "en", "ja", "ko", "ru"]},
            content_i18n={
                lang: "本地预览数据，仅用于界面与交互检查。"
                for lang in ["zh", "en", "ja", "ko", "ru"]
            },
            type=["info", "success", "warning", "maintenance"][i],
            is_active=True,
            created_at=now,
            updated_at=now,
            created_by=owner,
        )
    for i, name in enumerate(["产品反馈群", "研发协作群", "客户支持群"]):
        add(
            "user_channel_configs",
            i,
            user_id=owner,
            channel_type="feishu",
            instance_id=f"preview-{owner}-{i}",
            name=f"{name} · 已停用",
            config={"enabled": False, "app_id": f"preview-{i}", "app_secret": ""},
            enabled=False,
            agent_id="fast",
            created_at=now,
            updated_at=now,
        )
    for i, (key, content) in enumerate(preview_files(owner).items()):
        slug, title, _, description = TOPICS[i]
        group_slug = TOPICS[i % len(groups)][0]
        suffix = key.rsplit(".", 1)[1]
        mime = {
            "md": "text/markdown",
            "csv": "text/csv",
            "json": "application/json",
            "txt": "text/plain",
        }[suffix]
        digest = hashlib.sha256(content).hexdigest()
        add(
            "file_records",
            slug,
            FileRecordSchema,
            hash=digest,
            key=key,
            name=f"{title}.{suffix}",
            mime_type=mime,
            size=len(content),
            category="document",
            uploaded_by=owner,
            created_at=now,
        )
        add(
            "revealed_files",
            slug,
            user_id=owner,
            file_name=f"{title}.{suffix}",
            file_key=key,
            source="reveal_file",
            dedupe_key=f"key:reveal_file:{key}",
            trace_id=f"preview-trace-{owner}-{group_slug}",
            session_id=ident("sessions", group_slug),
            project_id=ident("projects", i % len(groups)),
            file_type="document",
            mime_type=mime,
            file_size=len(content),
            url=f"http://127.0.0.1:8000/api/upload/file/{key}",
            description=description,
            original_path=f"/preview/{slug}.{suffix}",
            content_hash=digest,
            is_favorite=i % 4 == 0,
            created_at=now - timedelta(hours=i * 7),
        )
    return dict(records)


def seed(database, owner: str, records: dict[str, list[dict]]) -> dict[str, int]:
    # Check every collision before the first write; never claim an existing document.
    for collection, docs in records.items():
        for doc in docs:
            existing = database[collection].find_one({"_id": doc["_id"]}, {"preview_owner": 1})
            if existing and existing.get("preview_owner") != owner:
                raise ValueError(f"Non-preview ID collision in {collection}")
    for collection, docs in records.items():
        for doc in docs:
            database[collection].update_one(
                {"_id": doc["_id"], "preview_owner": owner}, {"$setOnInsert": doc}, upsert=True
            )
    return {collection: len(docs) for collection, docs in records.items()}


def main():
    from src.infra.storage.mongodb import build_mongo_connection_string, get_mongo_sync_client
    from src.kernel.config import settings

    validate_target(build_mongo_connection_string(), settings.MONGODB_DB, "desktop_dev")
    database = get_mongo_sync_client()[settings.MONGODB_DB]
    user = database.users.find_one({"username": "desktop_dev"})
    if not user:
        raise SystemExit("Existing desktop_dev user required; no account will be created")
    owner = str(user["_id"])
    if settings.S3_ENABLED:
        raise SystemExit("Preview files require local storage; remote uploads are never performed")
    storage = Path(settings.LOCAL_STORAGE_PATH).resolve()
    for key, content in preview_files(owner).items():
        path = storage / key
        if path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Existing preview file differs: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
    counts = seed(database, owner, build_records(owner, datetime.now(timezone.utc)))
    # Add only preview names; preserve all existing preferences and authentication.
    database.users.update_one(
        {"_id": user["_id"]},
        {
            "$addToSet": {
                "metadata.disabled_skills": {
                    "$each": [f"preview-{topic[0]}" for i, topic in enumerate(TOPICS) if i % 5 == 0]
                },
                "metadata.favorite_skill_names": {
                    "$each": [f"preview-{topic[0]}" for topic in TOPICS[:3]]
                },
            }
        },
    )
    print(
        json.dumps(
            {"database": settings.MONGODB_DB, "username": "desktop_dev", "records": counts},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
