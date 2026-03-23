# Skills 架构升级设计方案

**日期**: 2026-03-23
**状态**: 已批准
**版本**: 1.0

## 1. 背景与目标

### 1.1 当前问题

- `system_skills` / `user_skills` / `user_skill_preferences` / `skill_files` 多表关联，过于复杂
- 沙箱写文件到 `skills_store` 后需要"注册"才能生效
- 并发写入 skills 时没有注册机制，导致 skills 散落

### 1.2 目标

- **Skills 商城**：管理员上传/管理，用户浏览/安装
- **简化用户 Skills**：文件存储 + 开关表，无需复杂元数据
- **沙箱自由写入**：写文件即 skill 存在，无需注册步骤
- **向后兼容**：提供迁移脚本

---

## 2. 数据模型

### 2.1 skill_marketplace（商城元数据表）

```json
{
  "skill_name": "ppt-generator",
  "description": "AI PPT 生成器",
  "tags": ["ppt", "presentation"],
  "version": "1.0.0",
  "created_at": "2026-03-23T00:00:00Z",
  "updated_at": "2026-03-23T00:00:00Z",
  "created_by": "admin_user_id"
}
```

**索引**: `{ skill_name }` UNIQUE

### 2.2 skill_marketplace_files（商城文件表）

```json
{
  "skill_name": "ppt-generator",
  "file_path": "SKILL.md",
  "content": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

**索引**: `{ skill_name, file_path }` UNIQUE

### 2.3 skill_files（用户文件表）

```json
{
  "skill_name": "ppt-generator",
  "user_id": "user123",
  "file_path": "SKILL.md",
  "content": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

**索引**: `{ skill_name, user_id, file_path }` UNIQUE

### 2.4 skill_toggles（用户开关表）

```json
{
  "skill_name": "ppt-generator",
  "user_id": "user123",
  "enabled": true,
  "installed_from": "marketplace | manual",
  "created_at": "...",
  "updated_at": "..."
}
```

**索引**: `{ skill_name, user_id }` UNIQUE

---

## 3. 目录结构

```
/home/yangyang/LambChat/src/
├── kernel/schemas/
│   ├── skill.py              # 重写：简化 schemas
│   └── marketplace.py        # 新增：商城 schemas
│
├── infra/skill/
│   ├── __init__.py
│   ├── types.py              # 新增：SkillSource, SkillFile, SkillToggle 等类型定义
│   ├── storage.py            # 重写：删除 system/user skills CRUD，新增简化存储
│   ├── marketplace.py        # 新增：商城逻辑（上传/安装/浏览）
│   ├── toggles.py            # 新增：开关管理
│   ├── cache.py              # 保留：Redis 缓存
│   ├── loader.py             # 改写：适配新架构
│   ├── middleware.py         # 改写：适配新架构
│   ├── manager.py            # 改写：适配新架构
│   ├── constants.py          # 改写：新增 collection 名称
│   ├── converters.py         # 删除（不再需要）
│   ├── preferences.py        # 删除（被 toggles.py 替代）
│   ├── import_export.py      # 删除（不再需要）
│   ├── builtin.py           # 删除（不再从代码库加载预置 skills）
│   └── github_sync.py       # 保留（未来可扩展）
│
├── infra/backend/
│   └── skills_store.py       # 改写：适配新架构
│
└── api/routes/
    ├── skills.py             # 重写：用户 Skills CRUD + Toggle
    ├── marketplace.py        # 新增：用户商城浏览 + 安装
    └── admin/
        └── marketplace.py    # 新增：管理员商城管理
```

---

## 4. API 设计

### 4.1 用户 Skills API (`/api/skills`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/skills` | 列出我安装的所有 Skills |
| GET | `/skills/{name}` | 获取某个 Skill 文件列表 |
| GET | `/skills/{name}/files/{path}` | 读取单个文件 |
| PUT | `/skills/{name}/files/{path}` | 更新单个文件 |
| DELETE | `/skills/{name}` | 删除（卸载）整个 Skill |
| PATCH | `/skills/{name}/toggle` | 开关 Skill |

### 4.2 用户商城 API (`/api/marketplace`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/marketplace` | 列出所有已发布的商城 Skills |
| GET | `/marketplace/tags` | 获取所有标签 |
| GET | `/marketplace/{name}` | 预览某个商城 Skill |
| GET | `/marketplace/{name}/files/{path}` | 读取商城 Skill 文件 |
| POST | `/marketplace/{name}/install` | 安装到我的 Skills |
| POST | `/marketplace/{name}/update` | 从商城更新（覆盖） |

### 4.3 管理员商城 API (`/api/admin/marketplace`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/marketplace` | 列出所有商城 Skills |
| POST | `/admin/marketplace` | 创建商城 Skill 元数据 |
| GET | `/admin/marketplace/{name}` | 获取商城 Skill 详情 |
| PUT | `/admin/marketplace/{name}` | 更新商城 Skill 元数据 |
| DELETE | `/admin/marketplace/{name}` | 删除商城 Skill |
| POST | `/admin/marketplace/{name}/upload` | 上传 Skill 文件（ZIP） |

---

## 5. 核心逻辑

### 5.1 获取用户生效 Skills（DeepAgent 用）

```python
async def get_user_active_skills(user_id: str) -> dict[str, dict[str, str]]:
    # 1. 从 skill_toggles 找 enabled=true 的 skill_names
    toggles = await db.skill_toggles.find({"user_id": user_id, "enabled": True})

    # 2. 批量获取这些 skill 的所有文件
    skill_names = [t["skill_name"] for t in toggles]
    files = await db.skill_files.find({
        "user_id": user_id,
        "skill_name": {"$in": skill_names}
    })

    # 3. 组装成 { skill_name: { file_path: content } }
    return group_files_by_skill(files)
```

### 5.2 安装商城 Skill

```python
async def install_marketplace_skill(skill_name: str, user_id: str) -> None:
    # 1. 验证商城 Skill 存在
    marketplace_skill = await db.skill_marketplace.find_one({"skill_name": skill_name})
    if not marketplace_skill:
        raise ValueError(f"Marketplace skill '{skill_name}' not found")

    # 2. 检查用户是否已安装
    existing = await db.skill_toggles.find_one({
        "skill_name": skill_name, "user_id": user_id
    })
    if existing:
        raise ValueError(f"Skill '{skill_name}' already installed")

    # 3. 批量复制文件到用户目录
    files = await db.skill_marketplace_files.find({"skill_name": skill_name})
    for file in files:
        await db.skill_files.insert_one({
            "skill_name": skill_name,
            "user_id": user_id,
            "file_path": file["file_path"],
            "content": file["content"],
            "created_at": now(),
            "updated_at": now(),
        })

    # 4. 创建开关记录
    await db.skill_toggles.insert_one({
        "skill_name": skill_name,
        "user_id": user_id,
        "enabled": True,
        "installed_from": "marketplace",
        "created_at": now(),
        "updated_at": now(),
    })
```

### 5.3 沙箱写入 Skills（无需注册）

```python
async def awrite(file_path: str, content: str) -> WriteResult:
    # 1. 解析路径获取 skill_name, file_path
    skill_name, file_name = parse_path(file_path)

    # 2. 直接 upsert 文件（user_id = 当前用户）
    await db.skill_files.update_one(
        {"skill_name": skill_name, "user_id": user_id, "file_path": file_name},
        {"$set": {"content": content, "updated_at": now()}},
        upsert=True
    )

    # 3. 如果 skill_toggles 中没有该 skill，自动创建开关（enabled=True）
    await ensure_skill_toggle(skill_name, user_id)

    # 4. 失效缓存
    await invalidate_cache(user_id)
```

**核心改进：写文件即 skill 存在，无需额外注册步骤。**

---

## 6. 各模块职责

| 模块 | 职责 |
|------|------|
| `types.py` | 类型定义（SkillSource, SkillFile, SkillToggle, MarketplaceSkill） |
| `storage.py` | 底层 MongoDB 操作（文件 CRUD，批量查询） |
| `marketplace.py` | 商城逻辑（上传/安装/浏览/删除） |
| `toggles.py` | 用户开关管理（开启/关闭/列表） |
| `cache.py` | Redis 缓存（用户生效 skills 缓存） |
| `loader.py` | DeepAgent skill 加载 |
| `middleware.py` | 技能注入中间件 |
| `manager.py` | SkillManager（门面类） |
| `skills_store.py` | DeepAgent 后端（适配新架构） |

---

## 7. 向后兼容方案

### 7.1 迁移脚本

```python
async def migrate_system_skills_to_marketplace():
    """一次性迁移：system_skills -> skill_marketplace + skill_marketplace_files"""

    # 1. 读取所有 system_skills
    for doc in db.system_skills.find({}):
        # 2. 导入元数据到 skill_marketplace
        db.skill_marketplace.insert_one({
            "skill_name": doc["name"],
            "description": doc.get("description", ""),
            "tags": [],
            "version": doc.get("version", "1.0.0"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "created_by": doc.get("updated_by", "system"),
        })

        # 3. 复制文件到 skill_marketplace_files
        files = db.skill_files.find({"skill_name": doc["name"], "user_id": "system"})
        for file in files:
            db.skill_marketplace_files.insert_one({
                "skill_name": file["skill_name"],
                "file_path": file["file_path"],
                "content": file["content"],
                "created_at": file.get("created_at"),
                "updated_at": file.get("updated_at"),
            })

    logger.info(f"Migrated {count} system skills to marketplace")
```

### 7.2 迁移后清理

- 删除 `system_skills` 表
- 删除 `user_skills` 表
- 删除 `user_skill_preferences` 表
- 删除 `skill_files` 中 `user_id="system"` 的记录

---

## 8. 扩展点设计

### 8.1 版本控制（未来）

- `skill_marketplace_versions` 表存储历史版本
- 用户可查看版本列表、回滚

### 8.2 Skill 依赖（未来）

- `skill_dependencies` 表声明依赖关系
- 安装时自动检查依赖是否满足

### 8.3 Skill 评分/评论（未来）

- `skill_reviews` 表存储用户评分
- 商城按评分排序

### 8.4 GitHub 集成（已有）

- `github_sync.py` 可扩展为：从 GitHub URL 自动同步商城 Skill

---

## 9. 实施顺序

1. **第一阶段**：新建表和常量（`skill_marketplace`, `skill_marketplace_files`, `skill_toggles`）
2. **第二阶段**：新建 `types.py`, `toggles.py`, `marketplace.py`
3. **第三阶段**：重写 `storage.py`（移除 system/user skills CRUD）
4. **第四阶段**：重写 API routes（`skills.py`, `marketplace.py`, `admin/marketplace.py`）
5. **第五阶段**：重写 `skills_store.py`（适配新架构）
6. **第六阶段**：改写 `loader.py`, `middleware.py`, `manager.py`
7. **第七阶段**：运行迁移脚本
8. **第八阶段**：删除旧表和旧文件

---

## 10. 决策记录

| 日期 | 决策 |
|------|------|
| 2026-03-23 | 商城 Skill 元数据独立建表（不使用自动解析） |
| 2026-03-23 | 用户开关简单 enabled/disabled |
| 2026-03-23 | 商城 Skill 管理员上传，用户安装后完全自由修改 |
| 2026-03-23 | 管理员上传方式：ZIP + 元数据表单（复用现有上传逻辑） |
| 2026-03-23 | 商城 Skill 更新：手动，用户自行选择覆盖 |
| 2026-03-23 | 商城分类：自由标签（tags） |
| 2026-03-23 | 迁移策略：一次性迁移脚本 |
| 2026-03-23 | 版本控制：无版本控制，每次覆盖 |
| 2026-03-23 | 商城文件单独存表（`skill_marketplace_files`） |
