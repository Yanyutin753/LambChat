# 记忆自进化（Self-Evolving Memory）feature 设计

日期：2026-08-28
状态：待用户评审

## 一句话

把"从经验中变好"做成一个 feature：**夜间离线反思管线**从差评/失败的对话里蒸馏"教训"（结构化 feedback 记忆），再由**进化式小抄层**把它编译进现有记忆索引注入——下轮对话行为就变好。全程复用现有记忆基础设施，默认关闭。

## 业界对标结论（两轮调研合成）

Codex（v0.100+ Memories）与 Claude Code 收敛出的专业模式，正是本设计的骨架：

| 借鉴 | 来源 | 本设计落法 |
|---|---|---|
| 两层分离：人工规范层 + 自动记忆层 | Codex/Claude 共识 | LambChat 的 persona/system prompt = 人工层（永不自动改）；自进化只写记忆层 |
| 写入只走离线管线（会话内教训只读） | Codex "Never update memories" | 教训（feedback_rule）只由夜间管线写入；会话内 auto-capture 继续只记事实 |
| 严格 schema + 脱敏 + 配额感知 | Codex Phase1 | 反思 prompt 强 schema（rule+Why+How），密钥脱敏，每用户每晚上限 |
| 纠正与正反馈同记（防漂移） | Claude Code | 👎 蒸馏教训为主，👍 低频蒸馏"已验证做法" |
| 常驻小摘要 + 按需细节 + 硬预算 | Codex summary+grep / Claude 200行+5条 | 小抄进现有 `<memory_index>`（预算子额度），细节走 memory_recall |
| 30 天未召回剪除 | Codex 遗忘机制 | 复用 compaction（inventory 含 feedback_rule，超期未召回可清） |
| 每用户可控开关 | Codex /memories | 复用刚建的用户级记忆开关（关=不采集信号不注入） |
| 排除规则压过指令 | Claude Code | 反思 prompt 明确排除可从代码/git 推导、临时性内容 |

## 闭环

```
信号（已有，零新建）          离线反思（新建核心）           存储（复用）              注入（复用升级）           治理（复用扩展）
─────────────────          ─────────────────           ──────────              ──────────────           ─────────────
👎+评论 / run failed   →    夜间 arq 任务：LLM 蒸馏   →   feedback 记忆      →    小抄编译进            →    面板可见可删可改
（v2: 插话纠正信号）         rule + Why + How              context=feedback_rule   <memory_index>            compaction 遗忘
                            脱敏/排除/配额/去重            source=self_evolved     （30min 快照/预算内）      用户级开关门控
                                                                                     <memory_context> 按话题召回
```

## 组件设计

### 1. 信号扫描器（薄）

夜间任务扫最近 24h：`feedback` 集合里 rating=down 的 run（带评论优先）+ `traces` 里 status=failed 的 run。每用户取最近 N=5 条候选（配额）。v1 不挖 steer 信号（v2）。

### 2. 反思管线（核心，`src/infra/memory/evolution/`）

- arq 定时任务（复用 scheduler 注册模式，随 ENABLE_MEMORY+SELF_EVOLVE 开关注册）
- 每个候选 run：取对话详情（conversation_history 服务）→ 反思 prompt（glm-5.3-flash 渠道）：

  ```
  你在复盘一次被用户差评/失败的助手对话。提取一条可复用的行为教训。
  Schema: { rule: ≤80字祈使句, why: ≤60字, how_to_apply: ≤60字适用条件,
            memory_type: feedback }
  硬排除（即使看起来有用也不提取）：可从代码/git/文档推导的内容、
  一次性任务细节、问候/闲聊、密钥或敏感值（脱敏为 <redacted>）。
  与已有教训重复时输出 existing_memory_id（由调用方去重更新）。
  ```
- 产出走现有 `backend.retain()`——embedding/Qdrant 索引/recall 面板**全部免费获得**
- 👍 run 以 1/5 概率入候选（防漂移：记录"已验证做法"）
- 去重：复用 retain 的 existing_memory_id 路径 + 候选查询先召回相似教训喂给 prompt

### 3. 进化式小抄层（注入升级，零新注入机制）

`indexing.py` 的 `<memory_index>` 增加一个 `### Lessons` 子块：feedback_rule 类记忆按 `(命中次数×新鲜度×manual优先)` 排序取 top-3，每条一行 `rule`（Why/How 留给 memory_recall）。**骑现有 30 分钟快照机制**——KV 缓存纪律零新增（tools 前缀字节稳定性由既有快照保证）。子块预算 ≤400 字符，超预算从尾部裁。

### 4. 治理与护栏

- **总开关** `NATIVE_MEMORY_SELF_EVOLVE_ENABLED`（默认 false）+ 用户级开关（已建）双层门控
- 每用户每晚教训上限 `NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT`（默认 3）
- 所有产出 `source="self_evolved"` + `context="feedback_rule"`——记忆面板可见/可删/可改（前端加一个 source 徽章），完全透明
- compaction 扩展：feedback_rule 超 30 天未召回可清（inventory 加标签，提示词加一条规则）
- 反思 LLM 失败静默跳过（复用降级哲学），绝不阻塞

### 5. 度量（v1 轻量，v2 再闭环）

v1：教训的 access_count/recall 命中走既有统计；运营观察差评率趋势（feedback stats 现成）。v2（不做）：教训召回后当轮 👍/👎 的归因计数、自动升降权。

## 与现有系统的关系

- **不碰**：persona/system prompt（人工层）、NATIVE_MEMORY_GUIDE 规则文本、KV 缓存纪律、A1/A2 捕获链路
- **复用**：retain/recall/嵌入/Qdrant/compaction/面板/arq scheduler/设置系统/用户开关
- **新增文件**：`src/infra/memory/evolution/{reflector.py,scheduler.py}`（约 300 行）+ indexing 子块（~40 行）+ 设置 2 个 + i18n×5 + 面板徽章

## 分期

- **v1（本 feature，估 3-4 天）**：信号扫描 + 反思管线 + 小抄子块 + 护栏 + 测试
- **v2（候选池，不在本 feature）**：插话信号挖掘、教训效果归因、技能诱导（重复多步工具序列→SKILL 草稿+人审门）、GEPA-lite 提示自优化

## 开放问题（评审拍板）

1. 👎 教训蒸馏是否需要**用户确认后生效**？（Codex 全自动 vs 本设计建议 v1 全自动+面板可删——量小且透明，建议全自动）
2. 小抄子块预算 400 字符够不够？
3. v1 是否包含 👍 防漂移采样（建议包含，成本极低）？
