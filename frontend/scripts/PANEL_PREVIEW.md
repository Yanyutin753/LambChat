# Panel 本地预览

在 `frontend` 目录运行 `pnpm preview:panels`，访问 http://127.0.0.1:3002/files 。使用真实前端组件和独立的只读 API fixture，无需后端。仅绑定本机；模拟登录只写入预览 origin，API 写请求默认返回 405，不连接真实 API（下述显式模拟流程除外）。

主要列表各有 65 条记录，文件有 65 个会话、196 个文件，覆盖 Markdown、代码、CSV、Excalidraw；用量包含趋势、排行和日志，设置包含九类配置。数据仅用于展示，不代表真实经营指标。

## 页面清单

| 页面       | 路径               | 分页单位               |
| ---------- | ------------------ | ---------------------- |
| MCP        | `/mcp`             | 服务                   |
| 技能       | `/skills`          | 技能                   |
| 技能商店   | `/marketplace`     | 技能                   |
| 文件       | `/files`           | 会话组                 |
| 收藏       | `/bookmarks`       | 收藏                   |
| 用户       | `/users`           | 用户                   |
| 权限角色   | `/roles`           | 角色                   |
| 角色广场   | `/persona`         | 角色                   |
| 团队       | `/team`            | 团队                   |
| 记忆       | `/memory`          | 记忆                   |
| 通知       | `/notifications`   | 通知                   |
| 反馈       | `/feedback`        | 反馈                   |
| 定时任务   | `/scheduled-tasks` | 任务                   |
| 用量       | `/usage`           | 日志                   |
| 助手与模型 | `/agents`          | 模型配置、角色模型列表 |
| 渠道       | `/channels`        | 三类渠道，无分页       |
| 设置       | `/settings`        | 分类浏览，无分页       |

## 状态与走查

桌面端数据位置可用独立入口 `/sandbox-data-preview?theme=dark&custom=1`；`lang=ru` 检查长文案，`failure=read|pick|save|reset|relaunch` 让指定操作等待1.2秒后首次失败、重试恢复。该入口渲染真实 `SandboxDataLocationCard`，预览服务只将此组件的原生服务模块与 process 插件替换为本地 fixture，选择/保存/恢复/重启均不访问真实文件或原生桥。可检查读取错误、路径折行、迁移选项锁定、重试和重启提示；不能证明真实数据迁移、覆盖文件、跨窗口状态或应用重启。

URL 参数：`?theme=dark` 为深色；默认浅色。`?fixture=empty` 返回空列表，`?fixture=error` 模拟加载失败，`?fixture=loading` 延迟响应；可组合 `?theme=dark&fixture=empty`。设置和认证保持可用，以便继续导航。

助手角色读取恢复可用 `/agents?failure=agent-role`：角色分配首次读取失败，编辑被阻止，点击 Retry 后恢复。角色切换使用共享选择器，可验证键盘、长列表及草稿保留。保存仍返回 405，不改变真实权限。

选择器单独走查可用 `?fixture=error&failure=teams` 或 `?fixture=error&failure=persona-presets`，仅让对应列表请求失败，保留聊天与模式入口。演示助手标识与后端注册一致（`fast`、`search`、`team`），团队模式的功能菜单可打开团队选择器。

欢迎页可用 `/chat?fixture=error&failure=welcome-personas` 或 `failure=welcome-teams`：每个页面查询组合的对应列表首次请求失败，重试恢复；团队场景默认进入团队助手。更换查询参数或重启预览可重放。已完成的聊天样例包含宽表格与长 Python 行，可检查消息内复制、CSV 导出和局部横向滚动。

渠道列表可用 `/channels/slack?failure=channel-list` 或 `/channels?failure=channel-list`，对应实例列表首次读取失败，再点击刷新恢复；`failure=channel-status` 仅让各实例状态首次读取失败，可检查状态不可用与禁用的区别及单独重试。`/channels/slack/instance-0?failure=channel-config` 检查编辑器配置首次加载失败和恢复；Feishu 同样适用。更换查询参数或重启预览可重放。所有非 GET 仍返回 405，不创建真实渠道、注册会话或修改凭据。

`?fixture=error&failure=document` 仅让文档样例首次请求失败，点击重试恢复；更换页面查询参数或重启预览可重新检查失败状态。Markdown 内含 Mermaid 图表，可检查导出菜单及嵌套全屏焦点。

文件库首组提供 `研究流程.excalidraw`，用于检查手机全屏工具栏、图像加载、缩放、键盘焦点以及 SVG / PNG 导出。`?fixture=error&failure=excalidraw` 让缩略图和直接预览的首次请求失败，再点击重试恢复；更换查询参数或重启预览可重新检查。

文件库的 Markdown、Python、CSV 卡片分别读取对应格式的只读样例。样例包含长代码行、多列表格和中文内容，可验证预览中的横向滚动与编码；不再让代码、CSV 卡片读取同一份 Markdown。

公开主页和认证页使用 `?guest=1`，以访客状态走查，避免演示登录自动跳到聊天页。仅影响此只读预览的 3002 origin。

公开分享入口可用 `/shared/preview-report?failure=share-content`：首次内容读取返回503，点击重试后恢复；换一个 `run` 参数可重放。`share-status=401|404` 分别检查登录提示和失效链接。`scope=project` 返回3个会话的分页 manifest（初始2个），第二个会话无消息；`fixture=empty` 检查空项目，`profile=long` 检查长分享者名称。项目子会话和下一页读取等待2秒，`failure=project-session` 让每个子会话首次读取返回503，`failure=project-page` 让下一页首次读取返回503；重试后恢复。可组合三主题及 `fixture=loading`（读取等待8秒）；语言通过会话分享页已有菜单切换。仅模拟 GET 结果，不创建分享、不验证真实访问权限或认证。

聊天侧栏提供 65 条会话及一个长标题项目；`/chat/preview-report` 的分享选择有 65 个轮次。项目分享可检查长列表与 50 条上限。`loading` 延迟资源与设置响应 8 秒，认证 fixture 保持即时，以便检查各页面骨架；`empty` 仅清空已支持的列表，助手/渠道目录及用量汇总可能仍有样例。上述数据均不代表真实分享或项目。

`/chat/preview-report?chat-state=working|streaming|error|cancelled` 可检查等待、流式、失败和停止状态；默认 `completed` 包含思考过程与完整正文。`streaming` 使用本机 GET SSE，在 6/12/18 秒追加正文，24 秒结束；`working` 只维持等待，离开页面会清理所有定时器。已完成的流式场景在本次预览进程内按页面查询组合记住，换一个查询参数或重启可重放。公开分享始终返回已完成样例，API 写请求仍为 405，不请求真实模型，停止/重试生成等写操作需要测试后端验证。

本轮已逐页查看上述 17 个主页面的手机布局（390×844），并检查桌面列表；平板（834×1112）抽查文件、团队、设置、用量的深色布局。文件第二页、市场/收藏/团队/模型末页已实际点击验证。共享分页测试覆盖边界与总数收缩；菜单测试覆盖 Escape 和焦点归还。

继续验收时应检查：宽/窄屏的首页和末页、长标题、搜索后重置页码、空/错/加载状态、键盘焦点与深浅色对比。只读预览不验证保存、删除、真实服务权限或原生 App 安全区；这些需要连接测试后端及真机回归。

Impeccable 更新命令已尝试；当前环境未安装 skill folders，因此按 `DESIGN.md` 清单人工走查。

截图更新可用 `PANEL_PREVIEW_PORT=3017 pnpm preview:panels` 避开已占用端口。`/chat/preview-report` 与 `/shared/preview-report` 提供只读演示会话；不会创建真实分享或请求真实模型。

### 公开页面视觉验证

`/download` 的版本接口提供示例安装包与 daemon 资产，便于检查平台推荐、文件名换行及终端反色。资产仅用于只读预览，不代表真实发布文件，请勿用此页面安装。
预览使用独立的 `.vite-panel-preview` 缓存，避免与同一 worktree 的普通 Vite 服务争用依赖预构建缓存。

本轮继续逐页复查上述主页面的桌面浅色与手机深色布局，并额外检查模型配置、聊天/分享、找回密码、无令牌重置/验证、注册待验证和 404；320px 复查通知与反馈，834px 复查设置。通知标题在窄屏分行、反馈操作和设置表单保留触控尺寸，认证辅助页复用登录页的主题表面；未执行真实发送、保存、删除或安装。示例默认助手 ID 与 fixture 的助手列表一致，避免选择器呈现空值。

复制反馈走查：`/chat/preview-report?tools=1&failure=clipboard` 添加只读演示工具的参数/结果，并让本页面首次剪贴板写入失败；点击同一复制入口重试恢复真实剪贴板写入。仅在预览HTML启用，生产不覆盖浏览器API。页面重新加载可重放；复制不会请求真实模型或写API。

分享复制走查：会话与项目分享管理列表各提供一个只读演示链接 `preview-report`，可组合 `failure=clipboard` 检查首次失败与重试。不会创建新分享，创建、更新与删除请求仍返回405；创建成功但复制失败的路径由组件测试覆盖。

成果文件树走查：`/chat/preview-report?artifacts=1` 添加两个文件与一个内联文本项目的只读成果，可打开“全部文件”、项目文件树，检查长中文文件名、复制、单文件下载和 ZIP。可组合 `theme=dark` / `sepia` 与 `failure=clipboard`；不连接真实 API 或执行项目代码。

图片走查：`/chat/preview-report?images=1` 添加已有桌面/手机截图及一个固定404的图片到实际 `reveal_file` 画廊，可检查键盘打开、失败重试、切换恢复、缩放旋转与下载。404保持失败；同一图片重试成功由组件测试覆盖。图片来自仓库已有公开演示资产，不创建或上传真实文件。

视频走查：`/chat/preview-report?videos=1` 提供固定404的视频，可检查错误说明与同 URL 重试。需要实际播放时，用 `PANEL_PREVIEW_VIDEO=/absolute/path/sample.webm pnpm preview:panels` 启动，页面额外提供此本机样例；文件只由预览服务读取，不加入生产资源或提交仓库。本轮使用 [MDN 的示例视频](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video)（[flower.webm](https://developer.mozilla.org/shared-assets/videos/flower.webm)）验证播放、暂停、原生控件 Tab 顺序和下载内容。原生视频全屏、旧 iOS WebView 回退及真实触屏仍需对应设备验证。

技能导入走查：`/skills?imports=1` 仅为 `/api/github/preview` 和 `/api/skills/upload/preview` 两个只读 POST 返回 24 个预设候选；上传内容丢弃、不解析或存储，不连接 GitHub 或真实 API。可组合 `failure=skill-preview` 首次失败后 Retry 恢复，`fixture=empty` 空候选，`fixture=loading` 延迟8秒。安装与发布等其他写请求仍405；此入口只证明表单、文件选择和候选交互，不证明真实 ZIP 解析或导入成功。

技能文件读取走查：`/skills?file-flow=1&failure=skill-file` 提供三个不同正文的文本文件，每个文件首次 GET 返回503，重试恢复。新增页面查询参数（例如 `run=2`）可重放。可验证普通/全屏错误提示、重试焦点、文件路径重复提示和未命名草稿；保存及二进制上传仍返回405，不改变真实技能。并发请求、删除期间的响应归属由组件测试覆盖。

技能附件走查：`/skills?file-flow=1&binary=1` 提供一个已有公开图标的二进制读取/预览；可在表单选择其它公开测试文件。显式加 `save-flow=1&failure=skill-upload` 时，仅用户技能文件 PUT 返回模拟保存结果，二进制上传等待2秒、首次503、重试200；请求字节丢弃，不存储文件、更新真实列表或转发 API。可检查等待焦点、底部错误/重试、草稿保留与完成后关闭。其它写请求仍405；此模式不证明真实保存、存储、权限或发布成功。真实部分上传后的文件清单、仅重试未完成项和删除恢复由集成测试验证。

技能商店只读预览：`/marketplace?failure=marketplace-files` 的文件清单首次 GET 返回503，`failure=marketplace-file` 的每个文件首次 GET 返回503，重试恢复。添加新的 `run` 查询参数可重放。可检查列表/文件错误、重试焦点、手机关闭按钮和已有二进制预览；并发请求归属与空文本缓存由集成测试验证。没有安装、发布、修改文件或真实存储写入，其它写请求仍405。

记忆全文走查：`/memory?failure=memory-detail` 的每条记忆全文首次 GET 返回503，重试恢复；列表片段与完整正文不同，全文附带长链接以检查窄屏换行。新的 `run` 查询参数可重放，`fixture=loading` 可检查8秒读取等待。保存仍返回405，可验证持续错误、草稿保留与重试入口；没有写真实记忆。成功保存、切换期间旧请求和旧保存的隔离由组件集成测试验证，不作为真实存储或权限证明。

角色编辑器读取恢复：`/persona?fixture=error&failure=persona-bindings` 让 MCP 目录首次 GET 503，重试恢复；`failure=persona-skill-list` 仅让技能选择框的20项分页首次 GET 503，不影响编辑器的绑定可用性检查。可验证已选名称和草稿保留、加载与失败反馈、重试及 Escape/Tab/触控关闭焦点。新的 `run` 参数可重放。编辑、保存与头像上传仍受405写入保护，这些只读场景不证明真实保存、权限写入或真机软键盘行为。

角色详情走查：在 `/chat` 的“功能 → 增强 → 角色”选择器点击首个角色标题，样例包含 Markdown、长链接和长技能名，可切换原文检查换行、复制入口与关闭后卡片焦点。`/roles` 前两个系统角色带三项限额，可检查系统标识、窄侧栏列宽与手机日期换行。以上只补 GET 展示数据，写请求仍405，未修改真实角色或权限。

代码查找走查：`/chat/preview-report?theme=dark` 的代码块搜索邻接复制，展开为紧凑的 CodeMirror 原生查找；通过“会话文件”打开 `今天吃什么.py`，可检查搜索并入文件标题工具栏、Cmd/Ctrl+F、命中导航与 Escape 焦点。手机入口保留 44px 触控区域，文件代码内容不再额外显示一行孤立搜索按钮。只读 fixture 不证明真实文件写入或手机软键盘行为。

文件浏览恢复走查：同一路由的 `failure=workspace-list` 让首次云端目录 GET 503，`failure=workspace-read` 让首次文件内容 GET 503，后续读取恢复；新的 `run` 参数可重放。加 `workspace-flow=1` 使目录与文件读取等待2秒，`fixture=empty` 提供空目录。可检查目录错误/重试、加载期间焦点与刷新禁用，以及手机打开预览、返回/关闭后回到原文件。目录刷新移除文件后的关闭焦点回退与迟到读取隔离由真实组件集成测试覆盖；该只读入口不证明真实沙箱、文件写入、原生设备或软键盘行为。

普通工具文件代码预览的搜索改为复制旁的小悬浮图标，继续调用编辑器内置查找并支持 Cmd/Ctrl+F；带语言标签或复制操作的聊天代码工具栏仍保留。2026-10-02 验证文件预览 320px/390px 深色布局，标题栏搜索可打开紧凑浮动查找，命中高亮且页面无横向溢出。

会话搜索走查：从 `/chat/preview-report` 的侧栏搜索入口打开实际 SearchDialog。`search-long=1` 提供长会话标题、项目名和匹配摘要；输入“季度”可查看匹配结果，输入不存在的词检查空状态。`search-flow=1` 使会话列表 GET 等待2秒，`failure=search-sessions` 让第一次带搜索词的 GET 返回503，点击重试恢复；新的 `run` 参数可重放。无搜索词时有65项分页结果，方向键滚动触发后续页，追加后应保留键盘选择。可检查手机单层 sheet、标题/摘要/项目层级、聚焦清空、combobox/listbox 语义与 Escape 关闭。只读 fixture 不证明真实搜索权限、后端检索或设备输入法/软键盘。

聊天评价弹层走查：`/chat/preview-report?feedback-flow=1&failure=feedback-save` 或 `failure=feedback-upload` 显式启用反馈提交及图片上传 POST 的2秒模拟等待，指定流程首次503、重试200；新的 `run` 参数可重放。请求字节丢弃，不解析、存储或转发，上传只返回公开图标。其它写操作仍405。用于检查窄屏操作、附件键盘删除、上传原文件重试、提交冻结、持续错误、评论保留和 Ctrl / ⌘ + Enter；不证明真实反馈提交、文件存储、权限或手机软键盘。关闭上传及卸载后的旧响应隔离另有组件边界测试。

角色头像与保存走查：`/persona?persona-flow=1&failure=persona-save` 或 `failure=persona-avatar` 显式启用对应模拟流程；仅角色创建 POST、单个角色 PUT、头像上传 POST 等待2秒，指定流程首次503、点击重试后200。请求字节丢弃，不解析、保存、更新真实列表或转发 API；返回已有 fixture 角色或公开图标。新的 `run` 参数可重放，其它写操作仍405。用于检查当前会话保存等待、字段冻结、持续错误、草稿保留、原文件重试和头像操作焦点，不证明真实保存、存储、权限或手机软键盘。旧保存及列表刷新不冻结新草稿、旧上传不修改新头像由组件与真实 Hook 集成测试验证。

团队编辑器状态走查：`/team?team-flow=1&failure=team-save` 显式启用团队创建 POST、单个团队 PUT 的2秒模拟等待，首次503、重试200；请求字节丢弃，不解析、存储、更新列表或转发。单个团队详情 GET 同样等待2秒，`failure=team-detail` 让其首次503、重试恢复，列表不受影响。新的 `run` 参数可重放，其它写操作仍405。用于检查详情等待/错误、保存冻结、成员选择器关闭、持续页脚错误及草稿保留，不证明真实团队写入、权限、存储或真机软键盘；切换/关闭后的旧响应隔离由组件测试验证。

团队成员目录走查：`/team?failure=team-roles` 仅让编辑器角色目录的20项分页首次 GET 503，重试恢复；搜索沿用服务端 `q`，翻页后查询回第一页。新的 `run` 参数可重放，可检查成员默认摘要、长名称、局部 Escape、搜索加载/空结果/失败重试，以及翻页和重试回到搜索框的焦点。其它写操作仍405；添加或调整成员仅修改本页草稿，不写真实团队，也不证明真机触屏或软键盘。

模型与助手目录走查：`/team?failure=catalog-models` 或 `failure=catalog-agents` 分别让可用模型 GET、助手目录 GET 首次503，重试恢复。`/chat/preview-report?failure=catalog-models` 可检查标题栏和个人设置的模型目录；`failure=catalog-preference` 让个人偏好中的已保存助手偏好 GET 首次503，重试恢复。新的 `run` 参数可重放。可检查紧凑错误反馈、手机44px重试、焦点保留和现有草稿/选择不被失败清空；其它写操作仍405，不证明真实保存、认证或设备行为。

聊天助手模式走查：`/chat/preview-report?failure=catalog-agents&agent-flow=1` 让助手目录读取等待2秒、首次503、重试恢复；模式入口保持可见，等待期间显示紧凑状态并保持焦点。`agents=empty` / `agents=single` 分别返回成功空目录和单助手，可检查空提示、选择和关闭。可组合三主题与新的 `run` 参数；只修改 GET fixture，写请求仍405，没有真实对话或偏好保存。

个人偏好保存走查：`/chat/preview-report?preferences-flow=1&failure=preference-save` 显式启用个人元数据及默认助手 PUT 的2秒模拟等待，各路径首次503、重试200；请求字节丢弃，不解析、存储、更新真实偏好或转发。新的 `run` 参数可重放，其它写请求仍405。用于检查失败后选择保留、本机应用与云端同步错误的区分、逐字段禁用、原请求重试、移动端44px及稳定焦点。不证明真实云端持久化、认证、真机触屏或软键盘；账号切换及跨外观操作失败恢复由组件测试验证。

个人信息写入走查：`/chat/preview-report?profile-flow=1&failure=profile-save` 显式启用用户名 POST 和头像 POST/DELETE 的2秒模拟等待，各方法/路径首次503、重试200。请求字节丢弃，不解析、存储或转发；成功返回静态fixture，用户名和头像不会真实改变，其他写请求仍405。`profile-avatar=1` 给资料 GET 加现有公开头像，`profile-long=1` 返回长用户名/邮箱/角色；新的 `run` 可重放失败。用于检查用户名冻结、错误保留、Enter提交、Escape局部取消和焦点恢复，以及头像上传/删除等待与原文件重试。不证明真实持久化、认证、手机软键盘；旧请求隔离、压缩回退与2MB约束由集成测试验证。

语言同步走查复用 `preferences-flow=1&failure=preference-save`：标题栏菜单选择语言后立即本机应用，保存等待时禁用重复选择，失败后原请求重试；个人设置共享相同等待和错误状态，新的成功选择清除旧重试。`/auth/login?guest=1`、`/download?guest=1` 与 `/shared/preview-report?guest=1` 可检查公共语言菜单、键盘关闭和手机44px触控区域；访客及公开分享仅本机切换，不提交受保护的偏好请求。账号切换及迟到资料刷新由行为测试覆盖，预览不证明真实认证或云端持久化。

原生服务地址组件走查：`/server-connection-preview?view=setup&theme=dark&lang=zh` 渲染实际首启表单，去掉 `view=setup` 渲染设置页分区；此独立入口不加载原生桥，不属于生产路由。输入 `http://127.0.0.1:<预览端口>/preview-health` 后按 Enter，探测 GET 等待2秒并固定503，可检查禁用、取消、错误、焦点及320px短屏滚动。不会连真实服务、成功保存地址或刷新应用；成功保存、取消后的迟到响应与15秒超时由组件测试验证。不能替代原生客户端网络/软键盘/换服登录验证。

原生沙箱数据位置走查：`/sandbox-data-preview?theme=dark&lang=zh` 渲染实际数据位置组件；`custom=1` 显示自定义根，`failure=read|pick|save|reset|relaunch` 让对应操作首次失败后恢复。命令由仅预览的模块替身执行等待，不读写文件、不迁移目录、不重启应用。短屏使用明确的100dvh滚动容器，避免仅在scripts内出现的Tailwind类未生成。此入口不是生产路由，不证明真实Tauri目录迁移或重启。

本地沙箱设置走查：同一入口加 `shell=unpaired|paired|web` 渲染实际LocalSandboxSection；`failure=process` 首次进程读取失败、重试/下一次轮询恢复，`shell=web&failure=status` 检查网页状态错误与重试。可组合三主题及 `lang=ru` 检查完整路径、两列手机快捷按钮、完整确认策略值、字段标签、44px按钮及16px输入。默认所有配对、PAT、策略、目录打开、重启与取消配对命令等待后拒绝执行；只填写公开演示占位符，不提供真实凭据。这些状态替身仅用于此独立入口，常规面板使用实际全局状态hook和GET fixture。不能证明真实登录、PAT持久化、原生进程操作或真机软键盘。

分步恢复走查：显式加 `native-flow=1`，可用 `failure=pair-login|pair-create|pair-save|pair-restart|policy-server|policy-save|policy-restart|restart|unpair|open-workspaces|open-audit|open-logs` 使对应模拟步骤首次失败、重试恢复。配对回执使用公开占位符，账号字段不被解析或转发；模拟保存/策略/启动仅更新预览模块内存，不访问原生桥、文件系统或真实 API。可检查回执确认后收起凭据表单、重启失败的准确说明、只继续失败步骤，以及策略保存失败后点击 Restart 仍继续原保存。目录打开只模拟等待、首次失败和恢复，不会打开系统文件管理器；未启用 `native-flow=1` 时仍拒绝。刷新页面重置模拟流程。此入口不证明真实凭据落盘、服务端写入、目录打开、进程重启或真实设备行为。

连接与目录互锁走查：`shell=paired&failure=status` 同时保留原生“运行中”与连接读取错误，Retry 等待1.2秒后恢复；`shell=web&failure=status` 同样有等待反馈。`shell=paired&native-flow=1&failure=save` 可检查选目录、确认、保存重试与待应用重启期间暂停原生操作；`failure=restart` 可检查原生重启等待禁用目录修改，随后选目录也禁用原生错误中的Retry。只读读取重试仍可用。互锁当前限同一设置分区，预览不调用原生桥、迁移文件或重启应用，不证明多实例协调或真实迁移。

同一入口加 `reopen=1` 可关闭/重新挂载实际设置组件，保留页面和共享store。可检查迁移等待中重新进入、保存后新路径与待重启入口保留，以及 `custom=1` 恢复默认后的说明；`failure=relaunch` 可检查重启失败/Retry。刷新整个页面会重置模块内存，模拟重启不会真的刷新；该入口只证明同一WebView生命周期内的状态连续性，不证明独立WebView重载、原生迁移或应用重启。

会话分享阅读走查：`/shared/preview-report?share-long=1` 提供无空格的长标题、作者/助手/模型名和长中文角色名；叠加 `share-avatar=1` 检查作者头像、角色与模型图标的固定尺寸。`fixture=empty` 在会话分享中返回无事件内容；可组合三主题，使用已有语言菜单检查俄语长文案。仅 GET fixture，不验证真实分享权限、模型执行或真机键盘。

子目录恢复走查：`/chat/preview-report?failure=workspace-child&workspace-flow=1` 保持根目录正常，首次读取子目录 GET 等待2秒后503，重试返回研究资料内的访谈记录目录和访谈笔记；进一步展开访谈记录可读会议记录.txt。新的 `run` 参数重放失败，可组合三主题。目录失败就地提示，Retry 保留展开状态、稳定焦点及缓存；全局刷新也重新读取失败目录。`failure=workspace-read` 可检查深层文件路径、读取失败、直接Retry及移动端返回原文件。仅只读fixture，不证明真实沙箱权限、原生文件管理器或设备行为。


系统弹窗走查：`/dialog-preview?theme=dark&lang=ru` 直接渲染实际 UpdateDialog；支持 `state=downloading|error|ready`、`long=1` 长版本号/日志/表格、`platform=ios|tauri`（默认 android）和 `source=unknown`。升级按钮只模拟等待2秒、首次失败、重试后待安装、确认后关闭，不调用原生 updater、下载、安装、重启或真实写 API。

联系管理员走查：同一路由加 `view=contact&guest=1` 渲染实际 ContactAdminDialog 的无 token 路径；默认邮箱验证原因，`reason=permission` 切换权限说明，`contact=empty` 为空联系方式，`long=1` 是公开占位长邮箱。公开认证配置 GET `/api/auth/oauth/providers` 等待2秒，`failure=contact-config` 首次503、Retry恢复（旧 `contact-settings` 参数保留为别名）；新的 `run` 查询可重放。也可从 `/auth/pending?email=preview@example.test&guest=1&contact-flow=1` 的实际支持按钮进入，`contact-flow=1` 仅延迟 GET。保留实际 mailto/外链语义，走查仅检查链接、不激活邮件客户端或发送消息。公开 API 内容由只读 fixture 提供，不证明真实认证服务、配置广播、支持发送或原生设备行为；接口白名单及受保护设置匿名401由真实 AuthMiddleware 边界测试验证。

关于与确认弹窗：`/dialog-preview?view=about` 使用真实 useVersion 与只读版本 GET，等待2秒；`failure=about-version` 让初次读取503后 Retry 恢复，`failure=about-check` 只让强制检查首次503，已读版本保持可见。`long=1` 返回长版本号，`state=current` 显示已更新状态。`view=confirm` 仅模拟确认等待2秒后关闭，没有删除或写请求；`long=1` 添加长正文，`long-actions=1` 使用长操作文案检查按钮换行，`variant=warning|info` 检查主题变体。可组合 `theme=light|dark|sepia` 与 `lang=zh|en|ja|ko|ru`。外链为 example.test 占位，不证明真实更新下载、删除或手机软键盘。
