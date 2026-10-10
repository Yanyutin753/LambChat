# CUA Agent 实测（2026-10-10）

先前评估使用 `FastAgent.stream()`；按最新要求，办公题改为 `SearchAgent.stream()`，会话明确选择 `sandbox=local` 与测试 daemon 的 `sandbox_machine_id`。共同调用链为正式 `computer_use` 工具 → SSE relay → 本地 sandbox daemon → Linux / Windows GUI。模型请求名与校准响应名均为 `glm-5.3-flash`，在测试进程内复用已有 GLM 通道配置，关闭模型回退，不改写数据库模型配置。测试使用一次性账号、Linux 独立 X11 桌面、LibreOffice 用户配置和 Windows 交互桌面上的专用测试文件，不操作用户文档。

这是直接调用正式 Agent 图的集成实测，尚未经过前端聊天入口或打包客户端的完整操作流程。测试显式开启视觉并使用 base64 图片；随机数字图片校准通过，真实任务请求也记录到图片输入。正常模型配置需要开启视觉能力，树中缺失的正文、单元格和控件才能通过截图观察。

## 测试题与验收（先前 Fast Agent）

| 题目 | 验收依据 | 状态 |
| --- | --- | --- |
| 启动 Calc，处理启动向导并观察窗口 | Agent 调用轨迹、窗口标题、模型读取截图 | PASS，14 次 CUA 调用 |
| A1 输入中文测试，B1 输入 123，C1 输入 =B1*2，保存 XLSX | GUI 观察和保存文件的 XML 内容；不以工具返回 ok 为验收 | PASS：A1 中文测试、B1 123、C1 公式 B1*2、缓存值 246；63 次 CUA，另有一次越出题目约束的 ls |
| Writer 输入中文正文并保存 DOCX | GUI 观察与 `word/document.xml` | 基线 FAIL：英文被中文输入法转换；修复后改用 Search Agent 通过 |
| 多窗口定位和切换 | 指定 window_id 后观察标题、焦点与截图 | 移交 Search Agent 验证 |

这些是本轮办公任务题，不是 OSWorld 等公开任务集的全量成绩，不代表 Microsoft Excel / Word 已通过，也不代表所有办公场景都已覆盖。

## 实测发现与修复

- Linux 可访问树存在隐藏启动按钮、陈旧缓存和大量虚拟单元格，造成错误定位与遍历耗时。刷新缓存、过滤隐藏节点，并限制每个父节点的候选数量。
- 保存对话框实际可见但未进入窗口列表：刷新应用和窗口缓存，并识别 file chooser。仅刷新桌面根节点不能刷新其后代。
- Calc 单元格没有可访问 Action：只在目标窗口和应用都在前台、边界有效时回退到中心坐标点击。
- 过滤空布局节点但保留原索引：同一空表格状态从 10963 字符降到 9129 字符，约 17%；这不是延迟或 token 测量。
- 桌面文件与 Agent 的 Store 虚拟工作区分离，补充工具说明，避免把 ls 的空结果误判为 GUI 保存失败。
- 特殊键给 AT-SPI 传入了错误参数，F2 等按键未实际发送。改为数字 keysym。
- `launch` 的子进程 PID 可能属于 LibreOffice 启动器。改为明确的 `launcher_pid`，Agent 从 `apps` 获取可访问应用 PID。
- `setTextContents` 返回成功但 Calc 没有变化。写入后回读；移除 pyatspi 不存在的 `replaceText` 回退，避免继续报告空操作成功。
- 在光标处输入使用 `insertText`，长度采用 UTF-8 字节数。X11 无障碍写入不生效时使用现有 Xlib 的 Unicode keysym，避免 Shift 触发中文输入法切换，并恢复临时键映射。原生 GTK 校准已验证大小写英文、中文、公式和扩展 Unicode；Search Agent 的真实 Writer 与 Calc 任务也已验证中文、英文和批量公式。保留 Wayland 的限制。输入需要不同字符数不超过空闲键码数，超过时工具明确报错并要求分段。
- Windows WPS 树包含不可见的后台文档：原生探针确认 `win-fixture.xlsx` 的两个文档节点 `is_visible=false`，但先前仍进入 CUA 树。过滤隐藏节点，并在单个失效节点报错时保留可见兄弟节点。
- WPS 的匿名 Group 大量暴露 Invoke，但没有名称、值或独立操作语义。渲染时省略这类布局包装，仍保留原索引、具名 Group、按钮和可展开 Group；同一 Windows 状态从 23358 字符降到 9897 字符，减少约 58%，不代表模型延迟已下降。
- WPS 表格题曾因模型估算坐标把 C1 的公式写入 B1，触发真实循环引用弹窗；模型随后观察并恢复，最终文件内容通过。工具说明增加名称框 / 定位命令与单元格地址核验，减少对像素列宽估算的依赖。
- Windows 的所属弹窗可能嵌在应用树中，而未列在 UIA 桌面顶层。补充按前台 HWND 查找活动弹窗的回退，并保留前台焦点校验。原生 WPS 校准确认主窗口 PID=25352，而「定位」弹窗由 PID=18568 的 et 进程承载；沿用主窗口 PID 会失去焦点和截图。工具说明增加办公弹窗重新发现进程的提示。实际通过 `apps` 找到活动 et、`windows` 找到「定位」、`state` 获取有效截图，再用 Escape 关闭自己的测试弹窗，PASS。
- 同时补充 macOS `.app` 系统 opener、原生多次点击和 Windows 不支持 UIA Invoke 时的 LegacyIAccessible 回退。这些修复有回归测试，不能据此声称这些平台的全部办公任务已通过。

## Search Agent + 本地 daemon

使用 Search Agent 正式图与本地沙箱后端，不替换工具执行器。以下结果来自重新运行，未沿用 Fast Agent 的 PASS。

| 题目 | 结果与独立验收 |
| --- | --- |
| Linux XLSX：A1 中文、B1 数字、C1 公式、GUI 保存 | PASS，29 次 CUA 调用；保存文件 XML 为 A1=中文测试、B1=123、C1=B1*2、缓存结果 246 |
| Linux DOCX：两段中英文正文、GUI 选 Word 格式与确认 | PASS；保存文件 `word/document.xml` 两段精确匹配 `LambChat CUA 文档测试` 和 `第二段：中文、English、123。` |
| Linux Writer / Calc 多窗口定位与切换 | PASS；DOCX 和窗口题合计 29 次 CUA 调用，先列出两个窗口，再分别 activate 并 state 截图验证 focused=true、正确标题 |
| Windows WPS XLSX | PASS，32 次工具调用（其中 31 次 CUA、1 次测试账号记忆保存）；模型自行处理误写引发的循环引用；保存文件 XML 为 A1=中文测试、B1=123、C1=B1*2、缓存结果 246 |
| Windows WPS DOCX | PASS，14 次 CUA 调用；保存文件 `word/document.xml` 为两段精确匹配的中英文正文，与 Linux DOCX 题相同 |

上述五项由模型执行。WPS 弹窗的跨进程枚举、截图与关闭另作原生 CUA 校准，不计为第六项模型任务。测试启动器的终端曾抢占前台，校准时隐藏测试 daemon 自己的终端，未放宽焦点限制。

两轮 Linux 任务各有一次工具报错，Agent 观察后自行恢复。短模型请求约 4 秒；本轮较复杂的图形推理请求可超过一分钟，不能把这些模型等待时间说成已消除。

测试脚本先前人为设置了 2048 输出上限，并传旧的 thinking=off；正式代码会把 off 归一为 low。重跑改为沿用配置默认输出上限和显式 low。测试加载运行时配置，避免把测试脚本的递归上限或输出截断误报为产品缺陷。

## 自动验证

相关测试 657 passed、3 skipped；Ruff 检查通过；Mypy 检查 564 个文件通过；最新修复后全量本地沙箱 E2E 46/46 PASS，追加 `--stress` 为 51/51 PASS。

```bash
env -u LOG_FORMAT uv run pytest tests/client tests/infra/tool/test_computer_use_tool.py tests/infra/agent/test_tool_result_binary_middleware.py tests/agents/test_computer_use_tool_exposure.py -q
env -u LOG_FORMAT uv run python scripts/e2e_local_sandbox.py
env -u LOG_FORMAT uv run python scripts/e2e_local_sandbox.py --stress
uv run mypy src/
```

模型任务必须在已登录、可访问的隔离图形会话内运行；图形环境变量须在 `dbus-run-session` 之前设置，使 AT-SPI 注册服务继承相同 DISPLAY。启动真实 Agent 前加载 `initialize_settings()`，使用服务端运行时配置；只读环境默认的递归上限会与正式服务不同。

完整任务轨迹和输出文件保存在测试机与本机临时测试目录，没有把账号、PAT、模型密钥或截图访问链接写入仓库。测试账号、PAT、会话截图上传和测试账号生成的记忆已清理；专用输出文件保留供核验。

未运行公开桌面任务集全量评分、Microsoft Office 真机题、Wayland 桌面题、前端全量测试或客户端打包。不能据此保证所有应用和办公任务均可用，复杂 WPS 观察仍存在明显模型等待时间。本次代码位于独立工作分支，尚未发布到安装的客户端。

进阶任务、并发输入、批量中文、Edge 滚动与格式失败的后续修复见 [进阶实测](./cua-agent-advanced-evaluation-20261010.md)。
