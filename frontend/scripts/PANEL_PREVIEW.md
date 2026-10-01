# Panel 本地预览

在 `frontend` 目录运行 `pnpm preview:panels`，访问 http://127.0.0.1:3002/files 。使用真实前端组件和独立的只读 API fixture，无需后端。仅绑定本机；模拟登录只写入 3002 origin，API 写请求返回 405，不连接真实 API。

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

URL 参数：`?theme=dark` 为深色；默认浅色。`?fixture=empty` 返回空列表，`?fixture=error` 模拟加载失败，`?fixture=loading` 延迟响应；可组合 `?theme=dark&fixture=empty`。设置和认证保持可用，以便继续导航。

助手角色读取恢复可用 `/agents?failure=agent-role`：角色分配首次读取失败，编辑被阻止，点击 Retry 后恢复。角色切换使用共享选择器，可验证键盘、长列表及草稿保留。保存仍返回 405，不改变真实权限。

选择器单独走查可用 `?fixture=error&failure=teams` 或 `?fixture=error&failure=persona-presets`，仅让对应列表请求失败，保留聊天与模式入口。演示助手标识与后端注册一致（`fast`、`search`、`team`），团队模式的功能菜单可打开团队选择器。

欢迎页可用 `/chat?fixture=error&failure=welcome-personas` 或 `failure=welcome-teams`：每个页面查询组合的对应列表首次请求失败，重试恢复；团队场景默认进入团队助手。更换查询参数或重启预览可重放。已完成的聊天样例包含宽表格与长 Python 行，可检查消息内复制、CSV 导出和局部横向滚动。

渠道列表可用 `/channels/slack?failure=channel-list` 或 `/channels?failure=channel-list`，对应实例列表首次读取失败，再点击刷新恢复；`failure=channel-status` 仅让各实例状态首次读取失败，可检查状态不可用与禁用的区别及单独重试。`/channels/slack/instance-0?failure=channel-config` 检查编辑器配置首次加载失败和恢复；Feishu 同样适用。更换查询参数或重启预览可重放。所有非 GET 仍返回 405，不创建真实渠道、注册会话或修改凭据。

`?fixture=error&failure=document` 仅让文档样例首次请求失败，点击重试恢复；更换页面查询参数或重启预览可重新检查失败状态。Markdown 内含 Mermaid 图表，可检查导出菜单及嵌套全屏焦点。

文件库首组提供 `研究流程.excalidraw`，用于检查手机全屏工具栏、图像加载、缩放、键盘焦点以及 SVG / PNG 导出。`?fixture=error&failure=excalidraw` 让缩略图和直接预览的首次请求失败，再点击重试恢复；更换查询参数或重启预览可重新检查。

文件库的 Markdown、Python、CSV 卡片分别读取对应格式的只读样例。样例包含长代码行、多列表格和中文内容，可验证预览中的横向滚动与编码；不再让代码、CSV 卡片读取同一份 Markdown。

公开主页和认证页使用 `?guest=1`，以访客状态走查，避免演示登录自动跳到聊天页。仅影响此只读预览的 3002 origin。

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
