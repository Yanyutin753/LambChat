#!/usr/bin/env python3
"""插件中心（Plugin Hub）真实 E2E。

前置：本机 MongoDB/Redis 可达，后端已在 E2E_PLUGIN_HUB_SERVER（默认
http://127.0.0.1:8000）运行且包含插件路由。脚本自举两名一次性测试用户
（admin / 普通），走完整链路：创建→物化→安装→绑定→更新→停用→删除，
并覆盖冲突/引用缺失/越权/未装状态等边缘用例，结束自动回收测试数据。

用法：
    uv run python scripts/e2e_plugin_hub.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("E2E_PLUGIN_HUB_SERVER", "http://127.0.0.1:8000").rstrip("/")
PASS: list[str] = []
FAIL: list[str] = []

# E2E 造物命名前缀，回收时按前缀清理
PREFIX = f"e2e-plugin-{uuid.uuid4().hex[:8]}"
PLUGIN = f"{PREFIX}-kit"
PLUGIN_REF_BAD = f"{PREFIX}-refbad"
PLUGIN_CONFLICT = f"{PREFIX}-conflict"
MCP_NAME = f"{PREFIX}-arxiv"
MCP_REF = f"{PREFIX}-refserver"


def http_json(method: str, path: str, body: dict | None = None, token: str | None = None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except Exception:
            return exc.code, {}


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def err_code(body: dict) -> str:
    detail = body.get("detail", {})
    return detail.get("code", "") if isinstance(detail, dict) else ""


def _mongo():
    from dotenv import dotenv_values

    env = dotenv_values(".env")
    import pymongo

    if MONGO_URL_OVERRIDE:
        url = MONGO_URL_OVERRIDE
        user = os.environ.get("E2E_PLUGIN_HUB_MONGO_USER", "")
        pwd = os.environ.get("E2E_PLUGIN_HUB_MONGO_PASSWORD", "")
        if user and pwd:
            return pymongo.MongoClient(
                url,
                username=user,
                password=pwd,
                authSource=env.get("MONGODB_AUTH_SOURCE", "admin"),
                serverSelectionTimeoutMS=5000,
            )[os.environ.get("E2E_PLUGIN_HUB_MONGO_DB", "agent_state_staging")]
        return pymongo.MongoClient(url, serverSelectionTimeoutMS=5000)[
            os.environ.get("E2E_PLUGIN_HUB_MONGO_DB", "agent_state_staging")
        ]
    url = env.get("MONGODB_URL", "mongodb://localhost:27017")
    user, pwd = env.get("MONGODB_USERNAME", ""), env.get("MONGODB_PASSWORD", "")
    if user and pwd:
        return pymongo.MongoClient(
            url,
            username=user,
            password=pwd,
            authSource=env.get("MONGODB_AUTH_SOURCE", "admin"),
            serverSelectionTimeoutMS=4000,
        )[env.get("MONGODB_DB", "agent_state")]
    return pymongo.MongoClient(url, serverSelectionTimeoutMS=4000)[
        env.get("MONGODB_DB", "agent_state")
    ]


MONGO_URL_OVERRIDE = os.environ.get("E2E_PLUGIN_HUB_MONGO_URL", "")


def register_and_login(username: str, elevate_admin: bool) -> str:
    http_json(
        "POST",
        "/api/auth/register",
        {"username": username, "password": "E2ePass!123", "email": f"{username}@example.com"},
    )
    update: dict = {"is_active": True, "email_verified": True}
    if elevate_admin:
        update["roles"] = ["admin"]
    db = _mongo()
    db.users.update_one({"username": username}, {"$set": update})
    status, login = http_json(
        "POST", "/api/auth/login", {"username": username, "password": "E2ePass!123"}
    )
    assert status == 200, f"login failed for {username}: {status} {login}"
    return login["access_token"]


def cleanup(db) -> None:
    db.users.delete_many({"username": {"$regex": f"^{PREFIX}"}})
    db.plugins.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    db.plugin_files.delete_many({"plugin_name": {"$regex": f"^{PREFIX}"}})
    db.plugin_installs.delete_many({"plugin_name": {"$regex": f"^{PREFIX}"}})
    db.system_mcp_servers.delete_many({"name": {"$regex": f"^{PREFIX}"}})
    db.persona_presets.delete_many(
        {
            "$or": [
                {"name": {"$regex": f"^{PREFIX}"}},
                {
                    "owner_user_id": {
                        "$in": [
                            str(u["_id"])
                            for u in db.users.find({"username": {"$regex": f"^{PREFIX}"}})
                        ]
                    }
                },
            ]
        }
    )
    for user_doc in db.users.find({"username": {"$regex": f"^{PREFIX}"}}):
        db.skill_files.delete_many({"user_id": str(user_doc["_id"])})
        db.users.update_one(
            {"_id": user_doc["_id"]},
            {"$unset": {"metadata.plugin_names": "", "metadata.disabled_skills": ""}},
        )


def make_plugin_payload(name: str) -> dict:
    return {
        "name": name,
        "display_name": f"E2E Kit {name}",
        "description": "e2e plugin hub coverage",
        "version": "1.0.0",
        "tags": ["e2e", "testing"],
        "skills": [
            {
                "skill_name": f"{name}-research",
                "description": "Research skill",
                "tags": ["research"],
            },
            {"skill_name": f"{name}-writer", "description": "Writer skill", "tags": ["writing"]},
        ],
        "mcp_servers": [
            {
                "name": MCP_NAME,
                "transport": "streamable_http",
                "url": "https://arxiv.example.com/mcp",
                "headers": {"Authorization": "Bearer e2e-secret-token"},
                "ref": False,
                "enabled": True,
            }
        ],
        "persona": {
            "name": f"{name} Persona",
            "description": "persona from plugin",
            "system_prompt": "You are an e2e persona.",
            "starter_prompts": [],
            "tags": [],
        },
        "activate": True,
    }


def main() -> int:
    print(f"[e2e-plugin-hub] target={BASE} prefix={PREFIX}")
    db = _mongo()
    admin_user = f"{PREFIX}-admin"
    plain_user = f"{PREFIX}-user"
    admin_token = register_and_login(admin_user, elevate_admin=True)
    user_token = register_and_login(plain_user, elevate_admin=False)
    user_id = str(db.users.find_one({"username": plain_user})["_id"])

    try:
        # ----------------------------------------------------------
        print("\n== 1. 创建与激活（MCP 物化） ==")
        status, body = http_json(
            "POST",
            "/api/plugins/",
            {**make_plugin_payload(PLUGIN), "activate": False},
            token=admin_token,
        )
        check(
            "admin 创建插件（draft）",
            status == 200 and body.get("status") == "draft",
            f"{status} {body}",
        )

        status, body = http_json(
            "PUT",
            f"/api/plugins/{PLUGIN}/skills/{PLUGIN}-research/files",
            {
                "files": {
                    f"{PLUGIN}-research/SKILL.md": "---\nname: research\ndescription: d\n---\n# R v1",
                    "extra.md": "v1",
                }
            },
            token=admin_token,
        )
        check("写入技能负载文件", status == 200, f"{status} {body}")
        http_json(
            "PUT",
            f"/api/plugins/{PLUGIN}/skills/{PLUGIN}-writer/files",
            {
                "files": {
                    f"{PLUGIN}-writer/SKILL.md": "---\nname: writer\ndescription: d\n---\n# W v1"
                }
            },
            token=admin_token,
        )

        status, body = http_json(
            "PATCH", f"/api/plugins/{PLUGIN}/activate", {"is_active": True}, token=admin_token
        )
        check(
            "写入文件后激活成功",
            status == 200 and body.get("status") == "active",
            f"{status} {body}",
        )

        # 防呆：声明技能但无文件的插件不可激活
        status, _ = http_json(
            "POST",
            "/api/plugins/",
            {
                **make_plugin_payload(f"{PREFIX}-nofiles"),
                "skills": [{"skill_name": f"{PREFIX}-empty", "description": "", "tags": []}],
                "mcp_servers": [],
                "activate": False,
            },
            token=admin_token,
        )
        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PREFIX}-nofiles/activate",
            {"is_active": True},
            token=admin_token,
        )
        check(
            "空技能负载激活 → plugin_invalid_payload",
            status == 400 and err_code(body) == "plugin_invalid_payload",
            f"{status} {body}",
        )

        server_doc = db.system_mcp_servers.find_one({"name": MCP_NAME})
        check(
            "MCP 物化为 system server 且带 source_plugin",
            server_doc is not None and server_doc.get("source_plugin") == PLUGIN,
            str(server_doc)[:120] if server_doc else "missing",
        )
        if server_doc:
            headers = server_doc.get("headers")
            check(
                "物化 server headers 落库已加密",
                isinstance(headers, dict) and "__encrypted__" in headers,
                str(headers)[:120],
            )

        status, body = http_json("GET", "/api/plugins/tags", token=user_token)
        check(
            "标签接口返回 e2e 标签",
            status == 200 and "e2e" in body.get("tags", []),
            f"{status} {body}",
        )

        # ----------------------------------------------------------
        print("\n== 2. 边缘：命名冲突 / 引用缺失 / 越权 ==")
        status, body = http_json(
            "POST", "/api/plugins/", make_plugin_payload(PLUGIN), token=admin_token
        )
        check(
            "重复插件名 → plugin_name_exists",
            status == 409 and err_code(body) == "plugin_name_exists",
            f"{status} {body}",
        )

        # ref 指向不存在的 server → 激活失败
        status, _ = http_json(
            "POST",
            "/api/plugins/",
            {
                **make_plugin_payload(PLUGIN_REF_BAD),
                "skills": [],
                "persona": None,
                "mcp_servers": [
                    {"name": MCP_REF, "transport": "streamable_http", "url": None, "ref": True}
                ],
                "activate": False,
            },
            token=admin_token,
        )
        check("创建引用型插件（draft）", status == 200, f"{status}")
        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_REF_BAD}/activate",
            {"is_active": True},
            token=admin_token,
        )
        check(
            "引用缺失 server → plugin_mcp_ref_not_found",
            status == 404 and err_code(body) == "plugin_mcp_ref_not_found",
            f"{status} {body}",
        )
        doc = db.plugins.find_one({"name": PLUGIN_REF_BAD})
        check(
            "激活失败后仍为 draft",
            doc is not None and doc.get("status") == "draft",
            str(doc)[:80] if doc else "missing",
        )

        # 另一插件复用同名 MCP server → 冲突
        status, _ = http_json(
            "POST",
            "/api/plugins/",
            {
                **make_plugin_payload(PLUGIN_CONFLICT),
                "skills": [],
                "persona": None,
                "activate": False,
            },
            token=admin_token,
        )
        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_CONFLICT}/activate",
            {"is_active": True},
            token=admin_token,
        )
        check(
            "MCP server 名冲突 → plugin_mcp_name_conflict",
            status == 409 and err_code(body) == "plugin_mcp_name_conflict",
            f"{status} {body}",
        )

        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_CONFLICT}/activate",
            {"is_active": True},
            token=user_token,
        )
        check("普通用户激活 → 403", status == 403, f"{status} {body}")
        status, body = http_json("DELETE", f"/api/plugins/{PLUGIN}", token=user_token)
        check("普通用户删插件 → 403", status == 403, f"{status} {body}")

        status, body = http_json("GET", "/api/plugins/", token=user_token)
        names = [p["name"] for p in body.get("plugins", [])]
        check(
            "用户列表只见 active（draft 冲突插件不可见）",
            PLUGIN in names and PLUGIN_CONFLICT not in names and PLUGIN_REF_BAD not in names,
            str(names),
        )

        # ----------------------------------------------------------
        print("\n== 3. 安装 / 重复 / 未装状态 ==")
        status, body = http_json("POST", f"/api/plugins/{PLUGIN}/install", token=user_token)
        installed_skills = set(body.get("installed_skills", []))
        check(
            "安装插件：两个技能落库 + 角色复制",
            status == 200
            and installed_skills == {f"{PLUGIN}-research", f"{PLUGIN}-writer"}
            and body.get("persona_created") is True,
            f"{status} {body}",
        )

        meta = db.skill_files.find_one(
            {"user_id": user_id, "skill_name": f"{PLUGIN}-research", "file_path": "__meta__"}
        )
        check(
            "技能 __meta__ installed_from=plugin",
            meta is not None and "plugin" in (meta.get("content") or ""),
            str(meta)[:120] if meta else "missing",
        )

        status, body = http_json("GET", "/api/plugins/installed", token=user_token)
        installs = {i["plugin_name"]: i["version"] for i in body.get("installs", [])}
        check("安装记录列表含插件与版本", installs.get(PLUGIN) == "1.0.0", str(installs))

        status, body = http_json("POST", f"/api/plugins/{PLUGIN}/install", token=user_token)
        check(
            "重复安装 → plugin_already_installed",
            status == 409 and err_code(body) == "plugin_already_installed",
            f"{status} {body}",
        )

        status, body = http_json("POST", f"/api/plugins/{PLUGIN_CONFLICT}/update", token=user_token)
        check(
            "未安装就 update → plugin_not_installed",
            status == 400 and err_code(body) == "plugin_not_installed",
            f"{status} {body}",
        )
        status, body = http_json(
            "POST", f"/api/plugins/{PLUGIN_CONFLICT}/uninstall", token=user_token
        )
        check(
            "未安装就卸载 → plugin_not_installed",
            status == 400 and err_code(body) == "plugin_not_installed",
            f"{status} {body}",
        )

        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_REF_BAD}/activate",
            {"is_active": True},
            token=admin_token,
        )
        # 修好引用后再激活（用真物化的 server 作为引用目标）
        status, body = http_json(
            "PUT",
            f"/api/plugins/{PLUGIN_REF_BAD}",
            {
                "mcp_servers": [
                    {"name": MCP_NAME, "transport": "streamable_http", "url": None, "ref": True}
                ]
            },
            token=admin_token,
        )
        status, body = http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_REF_BAD}/activate",
            {"is_active": True},
            token=admin_token,
        )
        check(
            "ref 指向真实 server 后可激活",
            status == 200 and body.get("status") == "active",
            f"{status} {body}",
        )

        status, body = http_json("POST", f"/api/plugins/{PLUGIN_REF_BAD}/install", token=user_token)
        check("停用前可安装 ref 插件", status == 200, f"{status} {body}")

        # 停用主插件（inline 物化方）→ server 一并禁用
        status, body = http_json(
            "PATCH", f"/api/plugins/{PLUGIN}/activate", {"is_active": False}, token=admin_token
        )
        check(
            "admin 停用主插件",
            status == 200 and body.get("status") == "deactivated",
            f"{status} {body}",
        )
        server_doc = db.system_mcp_servers.find_one({"name": MCP_NAME})
        check(
            "停用后物化 server enabled=false",
            server_doc is not None and server_doc.get("enabled") is False,
            str(server_doc)[:100] if server_doc else "missing",
        )

        # 停用期间：新装拒绝、已装用户更新也拒绝（对齐旧商店语义）
        status, body = http_json("POST", f"/api/plugins/{PLUGIN_REF_BAD}/install", token=user_token)
        check(
            "已停用插件再装 → plugin_already_installed（install 记录优先）",
            status == 409,
            f"{status} {body}",
        )
        status, body = http_json("POST", f"/api/plugins/{PLUGIN}/update", token=user_token)
        check(
            "停用插件更新副本 → plugin_inactive",
            status == 409 and err_code(body) == "plugin_inactive",
            f"{status} {body}",
        )

        status, body = http_json(
            "PATCH", f"/api/plugins/{PLUGIN}/activate", {"is_active": True}, token=admin_token
        )
        check(
            "重新激活恢复 server",
            status == 200
            and db.system_mcp_servers.find_one({"name": MCP_NAME}).get("enabled") is True,
            f"{status}",
        )

        # ref 插件停用不影响被引用 server（ref 只引用不拥有）
        http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_REF_BAD}/activate",
            {"is_active": False},
            token=admin_token,
        )
        server_doc = db.system_mcp_servers.find_one({"name": MCP_NAME})
        check(
            "ref 插件停用不影响被引用 server",
            server_doc is not None and server_doc.get("enabled") is True,
            str(server_doc)[:80] if server_doc else "missing",
        )
        http_json(
            "PATCH",
            f"/api/plugins/{PLUGIN_REF_BAD}/activate",
            {"is_active": True},
            token=admin_token,
        )

        # ----------------------------------------------------------
        print("\n== 4. 文件读取 / 更新链路 ==")
        status, body = http_json(
            "GET", f"/api/plugins/{PLUGIN}/skills/{PLUGIN}-research/files", token=user_token
        )
        check(
            "列技能负载文件",
            status == 200 and len(body.get("file_paths", [])) == 2,
            f"{status} {body}",
        )
        status, body = http_json(
            "GET",
            f"/api/plugins/{PLUGIN}/skills/{PLUGIN}-research/files/extra.md",
            token=user_token,
        )
        check("读负载文件内容", status == 200 and body.get("content") == "v1", f"{status} {body}")

        http_json("PUT", f"/api/plugins/{PLUGIN}", {"version": "1.1.0"}, token=admin_token)
        http_json(
            "PUT",
            f"/api/plugins/{PLUGIN}/skills/{PLUGIN}-research/files",
            {
                "files": {
                    f"{PLUGIN}-research/SKILL.md": "---\nname: research\ndescription: d\n---\n# R v2",
                    "extra.md": "v2",
                }
            },
            token=admin_token,
        )
        status, body = http_json("POST", f"/api/plugins/{PLUGIN}/update", token=user_token)
        check(
            "更新插件到 1.1.0", status == 200 and body.get("version") == "1.1.0", f"{status} {body}"
        )
        doc = db.skill_files.find_one(
            {"user_id": user_id, "skill_name": f"{PLUGIN}-research", "file_path": "extra.md"}
        )
        check(
            "技能副本内容已刷新",
            doc is not None and doc.get("content") == "v2",
            str(doc)[:100] if doc else "missing",
        )
        installs = {
            i["plugin_name"]: i["version"]
            for i in http_json("GET", "/api/plugins/installed", token=user_token)[1].get(
                "installs", []
            )
        }
        check("安装记录版本跟进", installs.get(PLUGIN) == "1.1.0", str(installs))

        # ----------------------------------------------------------
        print("\n== 5. 角色绑定插件 / MCP 白名单 ==")
        status, persona = http_json(
            "POST",
            "/api/persona-presets/",
            {
                "name": f"{PREFIX}-persona",
                "description": "bound",
                "system_prompt": "You test plugin binding.",
                "skill_names": [],
                "plugin_names": [PLUGIN, f"{PREFIX}-missing"],
                "mcp_server_names": ["another-server"],
            },
            token=user_token,
        )
        check("创建绑定插件的角色", status == 200, f"{status} {persona}")
        status, snap = http_json(
            "POST", f"/api/persona-presets/{persona['id']}/use", token=user_token
        )
        check(
            "use 快照展开插件技能与 MCP 白名单",
            status == 200
            and set(snap.get("skill_names", [])) == {f"{PLUGIN}-research", f"{PLUGIN}-writer"}
            and MCP_NAME in snap.get("mcp_server_names", [])
            and "another-server" in snap.get("mcp_server_names", [])
            and snap.get("missing_plugin_names") == [f"{PREFIX}-missing"]
            and snap.get("plugin_names") == [PLUGIN],
            f"{status} {json.dumps(snap, ensure_ascii=False)[:300]}",
        )

        status, admin_persona = http_json(
            "POST",
            "/api/persona-presets/",
            {
                "name": f"{PREFIX}-admin-persona",
                "description": "admin bound",
                "system_prompt": "You test binding without install.",
                "skill_names": [],
                "plugin_names": [PLUGIN],
                "mcp_server_names": [],
            },
            token=admin_token,
        )
        status, snap2 = http_json(
            "POST",
            f"/api/persona-presets/{admin_persona['id']}/use",
            token=admin_token,
        )
        # admin 未安装该插件 → 技能求交后为空，但 MCP 白名单仍透传
        check(
            "未安装用户求交为空但白名单保留",
            status == 200
            and snap2.get("skill_names") == []
            and MCP_NAME in snap2.get("mcp_server_names", []),
            f"{status} {json.dumps(snap2, ensure_ascii=False)[:200]}",
        )
        # 私有 persona 他人不可见（含 admin）
        status, _ = http_json(
            "POST", f"/api/persona-presets/{persona['id']}/use", token=admin_token
        )
        check("私有 persona 他人 use → 404", status == 404, f"{status}")

        # ----------------------------------------------------------
        print("\n== 6. 卸载 / 删除清理 ==")
        status, body = http_json("POST", f"/api/plugins/{PLUGIN}/uninstall", token=user_token)
        check("卸载移除安装记录", status == 200, f"{status} {body}")
        check(
            "卸载后技能副本保留",
            db.skill_files.count_documents({"user_id": user_id, "skill_name": f"{PLUGIN}-research"})
            >= 1,
            "",
        )
        installs = {
            i["plugin_name"]
            for i in http_json("GET", "/api/plugins/installed", token=user_token)[1].get(
                "installs", []
            )
        }
        check("安装记录已清", PLUGIN not in installs, str(installs))

        status, body = http_json("DELETE", f"/api/plugins/{PLUGIN_REF_BAD}", token=admin_token)
        check("admin 删除 ref 插件", status == 200, f"{status} {body}")
        status, body = http_json("DELETE", f"/api/plugins/{PREFIX}-nofiles", token=admin_token)
        check("admin 删除 nofiles 草稿", status == 200, f"{status} {body}")
        status, body = http_json("DELETE", f"/api/plugins/{PLUGIN_CONFLICT}", token=admin_token)
        check("admin 删除 conflict 草稿", status == 200, f"{status} {body}")
        status, body = http_json("DELETE", f"/api/plugins/{PLUGIN}", token=admin_token)
        check("admin 删除主插件", status == 200, f"{status} {body}")
        check(
            "删除后物化 server 一并清理",
            db.system_mcp_servers.count_documents({"name": MCP_NAME}) == 0,
            "",
        )
        check(
            "删除后插件与负载清理",
            db.plugins.count_documents({"name": {"$regex": f"^{PREFIX}"}}) == 0,
            "",
        )

    finally:
        cleanup(db)
        print(f"\n[e2e-plugin-hub] cleanup done (prefix={PREFIX})")

    print(f"\n===== E2E RESULT: {len(PASS)} passed, {len(FAIL)} failed =====")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
