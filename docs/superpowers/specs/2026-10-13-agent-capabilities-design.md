# LambChat Agent 六项能力增强设计

状态：用户已确认全部设计并明确授权直接实现与验证，不再请求阶段确认。

## 用户目标与基线

用户要求支持此前调研的六项能力，基于最新 PR 开始做。目标是提升真实任务完成率、长任务连贯性、工具调用效率与可控性。

用户明确选择最新 `origin/develop` 为基线。本次 fetch 后基线为 `7f3d6bbcfdf1e2edd7203c6d99a0f38d9f9348ce`，已包含 PR #870。开发分支为 `codex/agent-capability-research`。原工作区未提交改动保留，不把并行 UI 改动复制进新分支。

开工时已确认 PR #871 的子代理实现合入 develop；子项目 E 直接复用基线中的实现，不复制原工作区的未提交改动。

实现分成六个可独立验收的子项目：评测、PTC、证据、持久 Goal、子代理控制、目录发现。最终全部交付；顺序由依赖决定。复用 FastAPI、LangGraph/deepagents、QuickJS、MongoDB、Redis、arq 和现有 React 组件，不引入新 Agent 框架。

## 方案选择

1. 直接接入 OpenAI managed harness：省部分调度代码，但依赖特定 API 能力并改变多模型路径，不选为主实现。
2. 在 LambChat 现有执行链路增量增强：复用审批、模型配置、恢复和前端事件，推荐并采用。
3. 只增强提示词：成本低，但无法可靠处理跨 worker 调度、预算和证据失效，不满足本次全部支持的目标。

## 共同约束

- 普通聊天和既有 run 级 Goal 保持兼容；自动续跑只发生在用户显式开启的持久 Goal 中。
- 权限以执行时真实用户、会话、角色授权为准，checkpoint/摘要/子代理报告不扩大权限。
- 只读 PTC 保留逐工具审计，写操作与审批工具仍走正常工具调用。
- 文件路径、URL、criterion 文本作字段值，不作 MongoDB 动态字段名。
- 新后端错误遵循 ErrorCode/AppError；所有用户文案同步 zh/en/ja/ko/ru。
- 新增内置工具须专属 Item、事件处理、工具路由和覆盖基线；复用现有 Subagent/Goal 展示。
- 所有验证用 `scripts/run_validation.py` 串行，worker/job=1；占用退出 75，不排队。红绿定向测试在修改最终稳定前允许执行。
- 任何新增功能必须通过调用方集成测试，独立 helper 单测不能作为功能完成证据。

## A. 可复现 Agent 回归与 A/B

### 行为

支持离线 trace 诊断与隔离测试会话的真实执行。两种模式明确分开：重读轨迹不算重新执行 Agent。

固定初始九类任务：插话修改约束、压缩后续作、多源聚合、父子消息、审批恢复、worker 恢复、证据不足、工具失败换路径、产物内容核验。每个 case 包含输入、受控工具响应/资料、机械断言、可选评分 rubric、能力分类。

新增 `scripts/eval_agent_capabilities.py` 与版本化 fixtures，支持 `--mode trace|live`、`--cases`、`--output`，A/B 通过两份结果按 case ID 比较。live 必须显式给测试服务地址及凭据，不隐式触碰生产；不把凭据写结果。

输出 JSON：case_id、outcome（pass/fail/error/skip）、failure_stage、evidence、input/output/total tokens、elapsed_seconds、tool_calls、duplicate_effects。unknown usage 不填零；skip 不计成功。存在 fail/error 的检查退出非零。LLM judge 不能覆盖机械断言失败。

### 验收

同 fixtures 结果可重复；超时、401、无效 grader 输出分别归因；空案例/全 skip 不算通过；比较不同 case 集或版本时拒绝无提示合并。结果脱敏；一条 trace 不能读取其他用户数据。

## B. 结构化只读 PTC

### 行为与接口

保留现有 interpreter 双开关、`eval`、快照签名和只读名单。给桥接的 web_search/web_fetch 添加结构化返回适配，普通顶层工具结果保持兼容。

程序内结果：`{ok, data, sources, truncated, error}`；sources 包含原始 URL/工具调用标识，error 包含稳定 code 与英文 fallback。合法 JSON 解码，非 JSON 文本作为有界文本值；超限返回截断标记与原始证据引用，不能切坏 JSON 后要求模型用正则猜字段。

适配器使用上游显式 BaseTool PTC 注册接口，不改 site-packages，不通过临时全局 monkeypatch。工具参数 schema、调用用户上下文、工具事件及原始错误状态必须保留。对现有配置允许的名称再做只读资格核验，配置名单不等于授权。

程序单次限制：32 次工具调用，60 秒执行期限，聚合输出上限维持现有 8000 字符。以实际安装版本暴露的参数设置；不能支持的限额由调用适配器强制。并发上限 3；一个失败可由程序读取其结构化错误继续处理其余结果。

### 验收

在真实 QuickJS 中运行 Promise.all/筛选/聚合，不只验证构造参数；覆盖坏 JSON、大输出、部分超时、取消、来源保留、工具审计、直接调用与 PTC 对照。取消必须收敛未结束 host calls；不得把错误事件标记为成功或失去 trace 归属。

## C. 压缩后可追溯的验收证据

### 行为与接口

新增 `src/infra/agent/evidence.py` 与证据中间件，复用当前 checkpoint 私有 state 与事件库，不复制所有工具输出。

证据记录包含：evidence_id、session_id、run_id、tool_call_id/event_id、claim、criterion、source_ref、observed_at、scope_version、status（observed/verified/stale/unavailable）。文件/URL只作引用；模型给出的结论不能自动变成 verified。

在工具事件完成后记录事实与可读引用；失败/取消仍记录失败结果。持久 Goal 新建或用户改动目标时改变 scope_version，旧验收证据失效。修改文件后，与该文件相关的测试证据需重验；没有可靠相关性时采取待复核状态，不擅自把全部旧证据视为有效。

每轮模型调用注入当前目标、约束、未完成项和至多 20 条最新证据索引；完整记录持久化且可按 ID 读取。摘要与主子交接文件保留索引和失效状态。Goal grader 通过现有受控文件/事件访问路径读取当前证据，不信任一句“测试通过”。

### 验收

两次强制摘要后仍可检索原始依据；目标变化、文件变化、缺失引用使相关证据失效；子代理来源标识不丢失；跨用户引用被拒绝。无证据不得宣布满足要求，尚不可判定返回 needs_revision 或明确 blocker。

## D. 用户显式开启的持久 Goal

### 状态与协议

保留现有 `GoalSpec` 和单次 run Goal。新增持久 Goal：id、session_id、user_id、objective、rubric、version、status、limits、accounting、last_verdict、current_run_id、continuation_sequence、last_progress_signature。

状态：active、paused、waiting_human、blocked、completed、budget_limited、cleared。预算默认 10 轮、100000 total tokens、3600 秒；用户可设更低值。预算在提交前与运行中检查，主/子代理和评分器都计入；无法可靠获取 token 时不得无上限续跑，仍由轮数与时间限制收敛并报告 unknown。

MongoDB 单独文档存唯一会话 Goal，更新通过 version/CAS；会话 metadata 仅保留展示引用。Redis 复用现有会话任务互斥，Mongo 保存 continuation intent（含确定性序号）后提交 arq，任务 ID 由 goal_id/version/sequence 唯一决定。恢复扫描重投未确认 intent；重复提交不启动两个执行器。旧 lease 的结果不能覆盖新 Goal 版本。

会话授权后的 API：GET/PUT `/chat/sessions/{id}/goal`，POST `/chat/sessions/{id}/goal/pause`、`resume`、`clear`。普通 run Goal 的请求格式不变；持久 Goal 通过明确 API 创建与修改。前端命令 `/goal persist <objective>` 创建；`/goal pause|resume|clear` 控制；原 `/goal <objective>` 维持单轮行为。已有 clear/done/complete 别名不伪装成证据完成。

复用 ActiveGoalBar 显示状态、预算、暂停/继续/清除，不新增独立管理页面。新增 `goal:updated` 事件，SSE/历史/刷新加载一致；保留 `goal:start/end` 表达 run 生命周期，不能把 end 转为持久 completed。

### 调度

仅 active、空闲、无用户排队消息、无待审批、预算允许时自动提交下一轮。普通用户插话优先，Goal 仍记得原目标；明确停止/取消会暂停 Goal，防止刚取消又续跑。审批挂起改为 waiting_human，授权恢复后继续；删除会话/撤销访问终止投递。

评分 satisfied 且每条要求有当前证据时 completed；needs_revision 且仍可推进时续跑；连续两轮无工具调用且无新的进展签名时 blocked。budget_limited 与 blocked 均不是 completed。用户 resume 后重置停滞计数，但不清空已经消耗的预算。

### 验收

双 worker、提交后崩溃、入队前崩溃、旧 worker 迟到、用户消息竞态、暂停/恢复、审批恢复、预算耗尽、未知 usage、无进展、会话删除和 fork。fork 不继承活跃调度身份；普通聊天不能意外开启自动执行。

## E. 子代理控制与既有实现复用

### 行为

以 develop 的子代理能力为准，并按上述依赖规则复用 PR #871 的 SubagentSessions、独立 checkpoint、父子消息及角色授权。先以 team 跑通，再让 fast/search 复用同一装配 helper，保留现有专用角色和 fork 类型。不开第二套异步任务系统。

一个父 run 默认最多 3 个正在执行的子代理；排队任务状态 queued，不能标 running。每次子任务执行期限 600 秒，等待用户审批不计模型执行期限。父 run 取消或结束时收敛活跃子任务；本次不支持父 run 结束后的脱离执行。

新增 `cancel_subagent(subagent_id)` 和 `list_subagents()`，单子任务取消不影响其他任务，重复取消幂等；对应专属 Item 与五语文案。wait 有界等待，超时返回 running/queued 状态，不能为了轮询阻塞模型不明确时长；收集最终答案仍需等待相关结果。

重启后恢复稳定 ID、未处理消息、角色及待审批状态；使用现有父 run 恢复所有权，禁止同一子图被两个父 runner 恢复。恢复主模型、工具与角色授权时重新核验。非幂等外部写操作不因 checkpoint 重放而宣称恰好一次执行；无法确认上次执行结果时暂停核验，不能盲重试。

### 验收

三个 Agent 模式都能启动、发消息、等待、取消、列状态；并发上限、排队取消、运行中取消、超时、父取消、审批超时排除、重启恢复、权限撤回、同 ID 幂等及父子消息无串写。验证 SubagentBlock、工具面板、回放、刷新后状态一致。

## F. 按业务域发现工具与技能

### 行为

复用 DeferredToolManager 与 search_tools/search_skills，不改工具执行名称与 schema。候选工具超过 40 个时先按 MCP server/系统业务域暴露分组名、短描述与数量；小目录维持完整 stubs。搜索仍访问完整已授权候选集，支持 `select:exact_tool_name`。

技能超过现有 `SKILL_PROMPT_DESCRIPTION_THRESHOLD` 时以技能分类/能力关键词组暴露目录，而不是盲列全部技能名；无可靠分类的技能保留可搜索入口，不能被静默遗漏。技能内容仍按需读取，references 不自动全读。

目录在会话范围冻结、搜索命中追加加载、发现顺序可恢复；权限撤销/禁用必须立即生效，缓存稳定性不能优先于安全。分组目录是搜索提示，不是改变工具实际执行的 namespace。

### 验收

20/100/500 个工具和技能 fixture：精确命中、语义查找、未知分类、重名、禁用、父子隔离、重启顺序。量化目录 token 与召回/误选率；新目录不能以漏工具换取 token 降低。

## 交付与验证顺序

### 后续确认：独立后台任务与完成提醒

用户追加要求后，增加 `start_background_task`：显式在独立会话中派发任务，复用现有授权、TaskManager 和 ARQ。返回任务身份只表示已接收；父对话结束后子任务继续。普通 `task(background=true)` 仍受当前 run 生命周期约束。后台任务继承父权限限制，执行时重新校验，禁止递归创建独立后台任务；不确定的外部写入必须停下来核验。

前台运行中的“后台继续”释放当前页面订阅并允许开启新对话，不调用取消接口；“停止”仍取消任务。完成、失败和待审批分别通知。通知先进入用户隔离的持久完成记录，再尝试 WebSocket/Push；登录、重连、恢复前台或恢复网络时按游标补取，并与实时消息去重，不让模型循环查询状态。原生系统提醒依赖已有通知权限。

验收分别覆盖正常队列派发、权限撤回、重复调用、独立身份、父对话结束、API 重启、完成记录重启保留、补取失败重试与账号切换。独立 worker/API 验证不等于 worker 崩溃时所有外部写入都能安全重放。

1. A 建立基线与差异报告。
2. B 支持结构化只读 PTC。
3. C 持久证据与摘要/交接集成。
4. D 持久 Goal 后端、调度和五语 UI。
5. E 子代理控制及 fast/search/team 装配。
6. F 目录分组；用 A 对全部能力做回归和 A/B。

每项先定向 RED，再最小实现 GREEN。所有代码/调用方/配置/locale 完成后统一最终 pytest、前端测试、Ruff/Mypy、lint/build。涉及 daemon/本地沙箱链路的改动加全量沙箱 E2E。live Agent 评测与纯单测分别报告；缺少服务、模型权限或验证锁占用不算通过。

设计自检：六项路线均有交付和验收；普通 run 与持久 Goal 分离；run end 与完成分离；PTC 不越审批；并发工具调用不绕过本机验证锁；不承诺未验证的成功率或跨副本恰好一次外部写入。具体文件、函数签名和逐项 RED/GREEN 命令在设计通过后的实现计划中确定。
