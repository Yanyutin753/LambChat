# 沙箱产物统一交付方案

## 背景

LambChat 当前已经有文件交付链路：

- `reveal_file`：把单个沙箱文件上传到存储，并返回前端可预览的文件信息。
- `reveal_project`：把项目或文件夹上传成 manifest，前端可浏览或运行预览。
- 前端 `RevealArtifactsSummary` 优先从 `artifact:result` 消息 part 收集产物，并兼容历史 `reveal_file` / `reveal_project` 工具结果。
- `FILE_REVEAL_GUIDE` 已经要求 agent 创建或修改文件后调用 reveal 工具。

缺口是这条链路依赖 agent 自觉调用 reveal。只要 agent 忘记 reveal，或者子 agent 生成了文件但最终只返回路径，用户就看不到文件；“全部文件”也只能显示已经 reveal 的产物。

## 目标

每轮对话结束时，用户能在“全部文件”里看到本轮所有 agent 认为可交付、用户可能需要查看或下载的沙箱产物。

“所有产物”不是沙箱全量文件扫描。范围应由 agent 的交付意图决定，包含：

- 用户明确要求生成、修改、查看、下载、预览的文件。
- agent 在最终答案中引用的文件、报告、图片、数据表、压缩包、代码项目或文件夹。
- 子 agent 完成任务后交给主 agent 的产物。
- 对最终结果有价值的中间产物，例如图表源数据、分析 notebook、生成的设计稿、可复现脚本。

默认排除：

- `node_modules`、`.venv`、`.cache`、`dist`、`build`、临时日志、测试缓存、下载缓存。
- agent 自己不准备交付给用户的草稿。
- 体积过大或包含敏感信息的文件，除非用户明确要求且通过安全检查。

## 非目标

- 不把沙箱目录完整同步到前端。
- 不改变“全部文件”的主要交互形态。
- 不绕过现有 `reveal_file` / `reveal_project` 上传、索引和预览链路。
- 不把失败 reveal 包装成成功交付。

## 推荐方案

采用“自动登记 + 内部 reveal/deliver + artifact 事件展示”的机制。

### 1. 自动登记高置信产物

中间件先自动登记高置信产物：

- `write_file` / `edit_file` 成功后，按 `file_path` 或 `path` 登记最终文件。
- `upload_url_to_sandbox` 成功后，按返回的 `path` 登记下载到沙箱的文件。
- `execute` 成功后，在当前 session workspace/work_dir 做前后文件快照，登记新增或修改的文件。
- `reveal_file` / `reveal_project` 成功后，标记对应路径已经交付，避免最终重复 reveal。

不再提供单独的候选登记工具。系统无法自动推断的产物仍可用现有 reveal 工具显式交付，或由后续统一 deliver API 接管：

- 外部 `http(s)` URL：调用 `reveal_file(file_path="<url>")`。
- 项目或文件夹：调用 `reveal_project(project_path=..., name=...)`。
- 当前 workspace 外的文件：先放入 workspace，或直接调用 `reveal_file`。

它解决三个问题：

- 常见文件写入和 sandbox shell 产物无需额外工具调用，也不会因为 agent 忘记 reveal 而丢失。
- 长任务或多阶段任务不需要等到最终答案时回忆所有产物，registry 会随着生成过程持续积累。
- agent 仍可通过 `reveal_file` / `reveal_project` 显式交付自动检测不到的 URL、项目目录或特殊路径；自动产物则由运行时内部调用 reveal 能力完成上传/索引。
- 系统能在最终答案前统一处理去重、过滤、上传和错误报告。

直接 reveal 的产物自动视为已交付，最终 flush 不会重复上传。

### 2. 回合结束前统一 flush

新增 `ArtifactDeliveryMiddleware`，适配所有 deepagents agent 栈。

职责：

- 自动观察 `write_file`、`edit_file`、`upload_url_to_sandbox` 等高置信产物工具，成功后登记候选产物。
- 自动观察 `execute`，通过当前 workspace 前后快照登记 shell 新增/修改的文件。
- 自动扫描最终 AI 文本中的文件型外部 URL（例如 `.svg`、`.png`、`.pdf`、`.zip`），作为兜底候选产物；普通网页链接不进入“全部文件”。
- 观察 `reveal_file` / `reveal_project` 成功结果，把已 reveal 的产物标记为已交付，避免最终重复上传。
- 在主 agent 和子 agent 最终输出前执行 flush：
  - 去重同一路径，保留最后一次声明。
  - 同一路径多次生成或修改时，只交付最终版本。
  - 对已 reveal 的产物跳过重复上传。
  - 对未 reveal 的候选产物按 `kind` 在内部调用 `reveal_file` 或 `reveal_project` 能力。
  - 产物较多时优先使用 `reveal_project`，避免大量单文件卡片。
  - 把成功交付结果作为 `artifact:result` 事件发送给前端，不再伪造成可见工具调用。
  - reveal/deliver 失败时发送失败 artifact 事件并写日志，但不伪装成交付成功。

这样用户不需要看到 reveal 工具卡片；前端“全部文件”直接从 artifact part 聚合，同时继续兼容历史 reveal 工具结果。

## 适配所有 agent

统一适配点应放在共享层，而不是分别改每个 agent 的业务逻辑。

### 工具注册

在 fast agent、search agent、team agent 共享的 context setup 中保留：

- 现有 `reveal_file`
- 现有 `reveal_project`

当前 `fast_agent/context.py` 和 `search_agent/context.py` 已经注册 reveal 工具；team agent 的主 agent 和 subagent middleware 也应确保工具集合一致。

### 提示词合同

扩展 `src/agents/core/subagent_prompts.py` 的 `FILE_REVEAL_GUIDE`：

- 普通 `write_file` / `edit_file` 写入会被系统自动登记。
- sandbox `execute` 在当前 workspace 内新增或修改的文件会被系统自动登记。
- 文件型外部 URL 会被最终文本扫描兜底登记；如果用户明确要求马上查看，仍可直接调用 `reveal_file`。
- 项目目录、文件夹路径、当前 workspace 外路径或其他无法自动推断的用户可见产物，应直接调用 `reveal_file` 或 `reveal_project`。
- 如果用户明确要求查看、打开、发送、下载某个文件，可以直接调用 `reveal_file` 或 `reveal_project`。
- 最终答案只能引用已经自动登记或 revealed 的文件。
- 子 agent 必须通过自动登记或 reveal 交付自己的产物，主 agent 汇总时不能只转述路径。

因为 `MAIN_AGENT_PROMPT_SECTIONS` 和 `WORKFLOW_SECTION` 已被 fast/search/team/subagent 共用，修改这里可以覆盖大多数 agent。团队角色的自定义 prompt 不应覆盖这条交付规则。

### 中间件注入

在 agent nodes 的共享 middleware 构造位置加入 `ArtifactDeliveryMiddleware`：

- fast agent：主 agent middleware 和 subagent middleware。
- search agent：主 agent middleware 和 subagent middleware。
- team agent：router 的 user middleware，以及每个 team member subagent middleware。

建议放在 `ToolResultBinaryMiddleware` 之后、`PromptCachingMiddleware` 之前。原因是二进制文件读取可能已经被上传成 URL，而 artifact flush 属于本轮动态状态，不应被 prompt cache 误处理。

## Artifact Registry

registry 只保存本轮 run 的交付候选，不作为长期文件库的唯一来源。长期索引仍由 `reveal_file` / `reveal_project` 写入 `revealed_file` storage。自动交付中间件内部调用 reveal 工具时会携带 `delivery_source: "artifact_auto"`，因此这些产物会进入“全部文件/文件库”，同时仍保留 `source: "reveal_file" | "reveal_project"` 兼容现有文件库导航。

文件库记录使用 `dedupe_key` 去重，而不是只依赖上传后的 `file_key`：

- 沙箱/本地文件优先按规范化 `original_path` 合并，同一个文件重新上传成不同 S3 key 时会更新同一条记录。
- http(s) 外部文件 URL 按 `scheme + host + path` 合并，忽略 query/fragment，避免 `?download=1` 等参数造成重复记录。
- 没有 `original_path` 的历史记录回退到 `key:{source}:{file_key}`，并在索引迁移时回填。
- `is_favorite` 属于用户显式状态，重复 upsert 时不会被覆盖。

建议字段：

```json
{
  "run_id": "run_xxx",
  "session_id": "session_xxx",
  "agent_scope": "main | subagent:<name>",
  "path": "/workspace/report.pdf",
  "kind": "file | project | folder",
  "name": "report.pdf",
  "description": "最终分析报告",
  "priority": "intermediate | final",
  "status": "staged | revealed | failed | skipped",
  "source_tool": "auto | reveal_file | reveal_project",
  "reveal_result": {},
  "created_at": "2026-06-27T00:00:00Z"
}
```

存储位置可先使用运行时内存 + `artifact:result` message parts，因为目标是保证当前回合最终交付。若需要跨 worker 或断线恢复，再落 MongoDB，按 `session_id + run_id` 查询。

## 过滤规则

自动登记仍需要保守过滤：

- 路径必须在当前 session workspace/work_dir 内，或是带可交付文件扩展名的 http(s) 远程 URL。
- 禁止 reveal `.env`、密钥、cookie、token、私钥、认证配置等敏感文件。
- 默认跳过常见依赖和构建目录：`node_modules/`、`.venv/`、`.git/`、`.cache/`、`dist/`、`build/`。
- 单文件大小沿用 `reveal_file` 的上传限制。
- 项目文件数沿用 `reveal_project` 的 `MAX_PROJECT_FILES`。
- 如果路径不存在，记录 `failed`，最终答案提示“产物生成了但交付失败”，不要只给沙箱路径。

## 前端影响

前端增加 `ArtifactPart` 和 `artifact:result` 事件处理：

- `processMessageEvent()` 把 `artifact:result` 写入当前消息或子 agent parts。
- `collectRevealArtifacts()` 优先收集 artifact parts，并继续兼容历史 reveal tool parts。
- 自动预览和外部导航定位同时支持 artifact parts。

后续可选优化：

- 在“全部文件”中标记 `final` / `intermediate`。
- 产物很多时提供筛选。
- 对 reveal 失败的产物显示一个不可预览的错误行。

## 执行流程

1. 用户发起请求。
2. agent 在沙箱中创建、修改或下载文件。
3. 文件工具、编辑工具、上传工具和 sandbox `execute` 成功后，中间件自动登记候选记录。
4. 最终文本中的文件型外部 URL 会被兜底登记；项目/文件夹路径、当前 workspace 外路径等自动登记无法推断的产物，agent 直接调用 `reveal_file` / `reveal_project`。
5. 如果用户正在等待明确预览，agent 仍可直接调用 `reveal_file` / `reveal_project` 提前发出。
6. 同一路径被多次登记时，registry 保留最新声明；同一文件被多次修改时，最终 reveal 读取的是沙箱里的最终内容。
7. 子 agent 完成时，middleware flush 子 agent registry，发送 `artifact:result`。
8. 主 agent 汇总子 agent 结果，并可继续 stage/reveal 自己产生的文件。
9. 主 agent 最终输出前，middleware flush 本轮剩余候选产物。
10. 事件处理器把 artifact 结果写入消息 parts。
11. 前端从 parts 收集 artifact，展示“全部文件”。

## 失败处理

- 单个产物 reveal 失败，不影响其他产物交付。
- 所有产物 reveal 都失败时，最终答案必须明确说明文件没有成功发出。
- 失败原因应保留内部日志；用户侧只显示可理解的短错误，例如文件不存在、文件过大、权限不足、疑似敏感文件。
- 如果 flush 在最终答案生成后才失败，需要补一条系统可见工具结果或 assistant 说明，避免用户以为文件已经可访问。

## 测试重点

- `write_file`、`edit_file`、`upload_url_to_sandbox` 成功后会自动登记候选产物。
- `execute` 成功后会通过 workspace 前后快照登记新增/修改文件。
- 最终文本里的文件型外部 URL 会自动登记，普通网页 URL 不会进入“全部文件”。
- 上述工具失败时不会自动登记。
- 多次登记同一路径时只保留最新声明，最终只 reveal 一次。
- 自动登记后继续修改文件时，flush 交付修改后的最终内容。
- flush 会把自动登记的文件转换成 `artifact:result`，不会生成用户可见的 reveal 工具卡片。
- 已经直接 `reveal_file` 的路径不会重复上传。
- subagent 自动登记/revealed 的产物能出现在最终消息的“全部文件”。
- 敏感路径和忽略目录会被跳过，并记录 skipped/failed。
- reveal 失败时最终答案不会声称文件已成功交付。
- 前端 `collectRevealArtifacts()` 能同时收集 artifact parts 和历史 reveal parts。

## 分阶段落地

### 第一阶段：提示词和工具合同

- 扩展 `FILE_REVEAL_GUIDE`。
- 保留现有 `reveal_file` / `reveal_project` 工具合同。
- 不改变前端。

### 第二阶段：统一 flush middleware

- 新增 `ArtifactDeliveryMiddleware`。
- 在所有 agent middleware 栈中注入。
- 补充 focused backend tests。

### 第三阶段：体验增强

- “全部文件”区分最终产物和中间产物。
- reveal 失败行可见。
- 文件库按 run/session 追踪本轮交付集合。
