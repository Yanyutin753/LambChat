# 全界面品质检查与优化计划

> 使用 superpowers:executing-plans 在本会话逐项实现；所有结论以当前截图、操作与测试为依据。

**目标：** 全部界面按排版、留白、视觉层级、色彩、动效、微交互、响应式、原创性八项复查并修复可观察问题。
**架构：** 保留 LambChat 视觉语言、阅读留白和现有组件。先修共享 primitive，再修页面特例；不为装饰扩大依赖或 eager JS。
**技术：** React / TypeScript / CSS / Vitest / 内置浏览器。
**依据：** 根目录 DESIGN.md、PRODUCT.md 及本会话请求。

## 约束与验证

- 沿用主题 token；手机按钮组紧凑，保留 44px 触控尺寸。
- 宽度按当前浏览器实际 innerWidth 记录；移动、平板、桌面，浅色、深色、sepia。
- 长标题、长标签、空、错、加载；滚动与分页；弹层关闭、焦点归还、键盘；reduced motion。
- 文案变化同步五语；保留无关用户改动。
- 所有修复先写失败测试，再最小实现、目标测试、浏览器复核；最终全量 test / lint / build。
- fixture 不证明保存、权限、真实聊天或原生安全区。未验证项不计完成。

## 执行清单

- [ ] 主界面：聊天/欢迎/分享、导航和侧栏、文件/文档预览。
- [x] 资源界面：MCP、技能/商店、角色广场、团队、收藏、记忆（常规内容走查）。
- [x] 管理界面：用户、角色、助手/模型、渠道、通知、反馈、任务、用量、系统设置（常规内容走查）。
- [ ] 编辑弹层：各资源创建/编辑、个人设置七类、选择器、分享、确认和搜索。
- [x] 公开界面：主页及五个 section、GitHub、下载、404（常规内容走查）。
- [x] 认证界面：登录、注册、找回/重置、邮件验证、待审核、OAuth 回调（只读视觉检查）。
- [ ] 全部页面的空/错/加载状态、五语长文案抽检和交付检查。

## 本轮证据

实际截图保存在本会话 visualizations 目录。每批完成后在此追加发现、修复与验证；只有当前证据覆盖上述清单才宣告全局完成。

### 2026-10-02：移动操作间距与共享交互

基于最新 origin/develop（24615115），在独立 worktree 实现。主 checkout 的未提交内容未覆盖。

| 检查方向 | 修复与证据 |
| --- | --- |
| 排版 | 长会话标题可收缩；团队标题下去除重复活跃数量；模型展开控件、设置和角色表单补语义名称。 |
| 留白 | 正文和资源卡片内边距保留；只收紧手机顶部、文档/工具和模型按钮组；公告关闭时去除空正文内边距。 |
| 层级 | 保留已有标题、标签和次级元数据规范；公开设备截图居中。 |
| 色彩 | 复选框使用主题 token，移除硬编码 amber 与发光；浅色、深色、护眼主题抽检。 |
| 动效 | 资源卡片延迟最多 180ms；公开区块 240ms / 12px 入场；保留 reduced-motion 规则。 |
| 微交互 | 原生复选框支持标签点击、Space、disabled 和焦点可见；语言子菜单进入/返回、Escape、外部点击；关闭公告正文 inert。 |
| 响应式 | 实际 innerWidth 320、390/410、768、1440；手机操作保留 44px 目标；抽检页无整页横向溢出。 |
| 原创性 | 沿用 LambChat 衬线字、羊场景和视觉语言；未增加装饰、依赖或另一套设计系统。 |

补充浏览器证据：个人设置七类、技能编辑器、角色编辑器、通知编辑器；登录、找回、无效重置、邮件验证空 token、待验证（测试邮箱）、下载、404；/github 正常跳转仓库。俄语长文案在模型配置、技能编辑器和待验证页面可用。MCP 的 empty/error/loading 已查看。聊天语言菜单浏览器复核：Escape 焦点归还，手机按钮宽约 44px、gap 0；桌面资源复选框焦点 outline 与 opacity 1。

代码审查发现语言子菜单切换时焦点丢失，已用失败测试复现后修复。复选框调用点均复核；测试覆盖 label、Space、事件隔离与 disabled。Impeccable 检查器不可用，按 DESIGN.md 交付清单人工检查。

验证：最后新增公告 inert 后重新执行，679 个测试文件、3299 项测试；lint 与 build 通过。eager JS 558674 / 559104 字节；precache 5001595 / 5242880 字节。

后续补充：公开架构与控制台最终截图；中/英/日/韩/俄通知页抽检，无整页横向溢出。

继续覆盖：全部资源编辑/选择/分享/搜索弹层；认证注册与重置表单的最终截图；各页面空/错/加载的组合。真实服务保存、聊天、邮件/OAuth 成功链路与 Android/iOS/Tauri 真机不由只读 fixture 证明。

### 2026-10-02：编辑、搜索、分享和错误恢复

团队成员动作、模式/模型选择器及共享编辑弹层底部按钮在手机上实测约 44px；成员身份与动作分行，动作 gap 为 0，正文留白保持。折叠设置 inert，模式/模型/指令都有可访问名称；共享焦点循环排除 inert/aria-hidden 的后代。团队折叠和开关尊重 reduced motion。

搜索弹层有语义名称、44px 清除/取消按钮；清除后输入框保留焦点，Escape 归还搜索入口焦点。独立审查发现高亮结果后 Enter 会截获取消按钮，已用失败测试复现，再限定输入框快捷键；浏览器复核 ArrowDown → Tab → Enter 会正常取消，URL 不变。

会话和项目分享都有命名关闭按钮、范围/访问权限 pressed 状态及固定底部。只读预览补充 65 条会话、65 个轮次和项目，实际检查长列表滚动、Space 选择及项目 50 条上限；未创建真实分享。注册完整表单（含底部滚动）与重置密码表单使用演示 token 只读检查，未填写密码或提交。

在 320px 深色逐页检查技能、商店、团队、角色、文件、书签、记忆、用户、权限角色、公告、反馈、任务、助手、渠道、用量的 empty/error 参数。注意 empty 参数仅清空实现的列表，不清空助手内置目录、渠道目录和用量统计。发现角色、记忆、公告、反馈、任务、用量和渠道将加载失败显示成空列表；补持续可见的 alert 与重试，并保留已有数据。用户/权限角色补内联重试，去除重复 toast；团队失败不再同时显示空态。共享面板 alert 操作在窄容器中为 44px，浅色团队失败态已复核。书签提示改为触屏适用的指引，同步五语。

所有上述检查无整页横向溢出。已完成技能、团队加载骨架截图；商店在延迟设置期间短暂出现“技能已禁用”，需继续核查 settings/feature flag 的加载边界，不能将该截图计为加载验收通过。剩余页面的加载矩阵与未覆盖资源编辑/选择器仍保持待检查。

八项自检：排版和正文留白维持既有基线；身份/动作层级清晰；沿用主题色与焦点 token；折叠/开关 reduced motion；原生键盘与焦点、命名/选中语义完成上述修复；320px、长列表和固定底部验证；保留羊形象与衬线品牌语言，无新依赖/装饰系统。

验证记录：新增修复均先看到相关测试失败，再转绿。独立审查仅发现上述搜索取消 P2，已修复；最后完整测试 684 文件、3316 项，lint 无警告，build/类型检查与体积门禁通过（随后追加手机选择器与 footer 高度 CSS，相关测试 13 文件 / 52 项和最终 build 已通过；eager JS 558643 / 559104 字节，precache 5002878 / 5242880 字节）。不以本批结果宣告全界面完成。


### 2026-10-02：配置加载与编辑表单触控补齐

商店/技能入口在配置尚未返回时使用现有 SkillsHubSkeleton，不再先宣告功能禁用；已配置为禁用的服务器仍保持禁用。三个失败测试覆盖两条路由的 pending → disabled → enabled 及 effect 前首帧，再转绿。

320px 浏览器走查发现 MCP 表单内动作未走 footer，仍为 32–38px；在共享 editor-sidebar 规则补齐 Button、Select、IconButton 和附件入口 44px，保留正文留白与桌面尺寸。MCP 名称/URL 原生标签、传输类型、HTTP 头及角色配额补名称；动态 HTTP 头两列与删除按钮无溢出。记忆四个字段关联标签，类型/来源补 pressed 与 44px 触控；任务所有字段、选择器、六项 Cron 及触发类型补名称/pressed。

共享 ToggleSwitch 覆盖公告、模型、助手和任务调用点：手机外层 44px，视觉轨道仍 28px；桌面实测 28px，减少动效与焦点可见，并显式 type=button 避免表单提交。新增原生行为测试先红再绿。浏览器在 320px 浅/深色及 1440px 深色验证这些修复，无页面/编辑器横向溢出。用户编辑器长角色列表与固定底部只读视觉查看，字段名称仍需补齐；MCP RoleSelector 的可点击 div 键盘语义仍待核查。

最终验证：688 个测试文件、3323 项测试通过；lint 无警告，build/类型检查及体积门禁通过。eager JS 558641 / 559104 字节，precache 5003056 / 5242880 字节。未提交真实表单；剩余加载矩阵、编辑器/选择器、文件/分享预览仍继续，目标保持进行中。

### 2026-10-02：角色选择、用户草稿和加载矩阵

MCP RoleSelector 三个调用点统一使用原生按钮、命名搜索与复选框，复用现有主题下拉和定位 hook，portal 避免编辑器裁切。选中值在单行截断，取消选择通过列表完成，去除小尺寸嵌套删除按钮。角色 API 失败持续显示 alert 与重试，不再伪装成无角色。浏览器验证 Enter 打开、Shift+Tab 退出列表、Escape 仅关闭列表并返回入口焦点，编辑器保持打开；未点击保存。

独立代码审查发现两项 P2：软键盘的 visualViewport 高度误用于 CSS bottom 锚点；反向 Tab 越过 portaled 列表却留下弹层。均先用失败测试复现后修复。布局锚点使用 innerHeight，visualViewport 仅约束可用空间。软键盘 offsetTop 0/300 用 jsdom 模拟，不声称真机键盘验证。320px 浅色、768px 护眼色、1440px 深色截图均无下拉裁切或整页横向溢出，65 条角色可独立滚动。

用户编辑器用户名、邮箱和密码关联原生标签，角色行手机 44px。角色请求独立重试，不卸载编辑器；失败→重试成功时保留已输入用户名的测试通过。320px 浏览器确认错误提示持续可见、重试不关闭编辑器和底部操作可见，未填写密码或保存真实用户。

补齐 320px 加载截图：商店、角色广场、记忆、用户、权限角色、公告、反馈、任务、助手、渠道、用量、文件、书签、设置，结合此前 MCP/技能/团队覆盖管理和资源页加载矩阵。沿用原有骨架与正文留白，均无整页横向溢出；商店首帧不再显示误导的禁用态。设置页发现 pending 时显示“0 项设置”，先红后绿改为已有“加载中”文案。预览供应商 fixture 修正为 API 契约的数组，避免演示数据导致模型表单报错；GET-only/非 GET 405 保持。

八项复核：排版保持单行选中值、描述为次级元数据；正文/卡片留白未压缩；错误与加载状态层级明确；复用主题色与焦点 token；复用全局 reduced-motion 下拉规则；补原生键盘与焦点返回；上述三种宽度/主题无溢出；维持 LambChat 品牌、无新依赖或装饰系统。

最终验证：690 个测试文件、3331 项测试通过，lint 无警告，build/类型检查和体积门禁通过；eager JS 558649 / 559104 字节，precache 5002376 / 5242880 字节。第一次并行全量检查中，既有 previewTabs 异步加载测试超时；单独复查和随后两次完整运行均通过，未改测试或生产预览逻辑。

下一批明确待查：主聊天/文件/文档/分享预览；剩余资源导入发布、助手/模型/批量/渠道编辑器。模型表单只读初查确认字段标签未关联、手机 es-input 约 36px，高级配置 summary 与供应商/图标选择器键盘行为需补齐。AgentPanel/shared/RoleSelector 仅有旧 AgentConfigPanel 调用链，当前应用未引用该面板，不能据源码存在将其算为在用缺陷。真实写入、认证成功和原生设备覆盖仍未验证；目标保持进行中。

### 2026-10-02：模型字段与品牌选择器

模型创建/编辑的 13 个输入字段关联原生标签，备用模型、API 格式和图片链接处理补字段名称。手机共享 editor 规则将 input.ui-input 与 summary 补到 44px，浏览器全部 12 个单行输入及高级配置入口实测约 44px；桌面仍约 36px。正文间距、双列价格字段与固定底部维持原有层级，不扩大卡片压缩范围。

供应商和图标的两套搜索下拉收敛为 ModelBrandPicker，两者在普通与批量模型表单中复用。保留搜索、品牌图标、自动识别/匹配、供应商 API 回退；复用 PickerTrigger、PanelSearchInput、主题下拉和定位 hook。portal 下拉按可用视口选择上下方向、限制高度并独立滚动；手机选项约 44px，桌面约 36px。Enter 打开、搜索焦点、方向键/Home/End、边界 Tab、Escape、选择后焦点返回均有检查。测试发现搜索中 ArrowUp 跳到倒数第二项，先红后绿修正为最后一项。

独立审查发现一项 P2：字段 aria-label 覆盖选中品牌文字。先用两条失败测试复现，再用 aria-describedby 关联当前显示值；受控选择 OpenAI 后描述更新，浏览器也确认焦点回入口、描述为 OpenAI、编辑器仍在。没有提交真实模型或输入密钥。

最终截图：320px 深色模型字段和两种下拉；1440px 浅色、768px 护眼主题的长图标列表，均无整页横向溢出或下拉裁切。排版/层级沿用 es-field 与次级说明；留白维持原值；主题和焦点使用既有 token；动效使用现有 reduced-motion 下拉规则；原生标签、键盘与选中描述补齐；三个宽度实测；保持 LambChat 品牌与图标，不增加依赖或另一套视觉系统。

最终验证：目标 11 文件 / 104 项通过；全量 692 文件 / 3335 项通过，lint 无警告，build/类型检查及体积门禁通过。eager JS 558648 / 559104 字节，precache 5002405 / 5242880 字节。

仍待继续：主聊天/文件/文档/分享预览、资源导入发布、助手、批量字段标签与渠道编辑器，以及剩余状态/语言组合。上述已修模型表单与品牌选择器不再列为待修项；不据本批宣告全界面完成。

### 2026-10-02：聊天触控、导航焦点与共享阅读

聊天页手机按钮组移除额外 gap，composer、消息动作、浮动滚动控制与 Markdown 表格/代码动作补到 44px。消息操作多于一行容量时换行；未压缩正文、卡片或阅读区域。320px 下助手文字只剩一个字，自查后在小于 360px 时显示完整图标入口并保留 aria-label，390px 仍显示助手名称。桌面按钮实测仍为 36px。页头展开侧栏与模型/标题入口补 44px 高度，右侧维持此前 gap 0。

ToolbarChip 的 SVG 内嵌点击清除改成独立原生兄弟按钮，桌面 hover/focus 可见且键盘可操作；手机仍通过已有角色/团队选择器清除，避免新增一个 44px 按钮挤出 composer。组件测试验证清除不打开选择器和没有嵌套 button。浏览器预览的角色激活走写接口，被 GET-only fixture 拒绝，未据此声称桌面真实角色选择/清除端到端成功。

从 ModalSurface 提取现有键盘边界为 useDialogFocus，复用于移动导航；关闭 drawer 和未启用的桌面 rail 使用 inert/aria-hidden。实际浏览器验证打开聚焦、Shift+Tab 留在导航、搜索子弹层 Escape 先关闭子层、第二次 Escape 关闭 drawer 并归还页头焦点。独立审查未发现 P1/P2。最终自查发现提取后自动标题在聚焦之后才设置；新增测试捕捉首次 focusin 空名称并修正调用顺序，恢复先命名再聚焦。

聊天与共享/官网的隐藏滚动按钮同步 disabled + aria-hidden，不再进入键盘序列，补显式 type 和聊天名称；共享 320px 实际点击滚动到底部后，向下按钮隐藏/禁用、向上按钮启用，状态正确。修改均先红后绿，延续已有动效与全局 reduced-motion 规则。

视觉证据：chat-320-light-final、chat-390-dark-final、chat-768-sepia-final、chat-1440-light-final，均无整页横向溢出，正文和卡片留白保持。shared-320-dark-scroll-final 实测表格和滚动按钮 44px。文件首个 Markdown 文档在 320px 浅色打开，四个工具栏按钮均 44px，标题截断、正文层级正常；预览/源码切换加载完成，无溢出（document-md-320-light-review）。未下载文件或写入真实数据。

八项自检：排版保持标题/正文/元数据层级；阅读留白未改；身份和动作分组明确；使用已有主题与焦点 token；原有动效/reduced motion 保持；键盘、焦点返回与隐藏控件补齐；上述四宽度及三主题实测；维持 LambChat 衬线、羊品牌和克制视觉，无新依赖/装饰系统。

最终全量 696 文件 / 3345 项测试通过，lint 无警告，build/类型检查及体积门禁通过，eager JS 558644 / 559104 字节、precache 5004431 / 5242880 字节。随后仅移除无关 CSS 格式 diff，目标 2 文件 / 8 项通过，CSS 值不变。

继续待查：侧栏内部关闭/导航/分组/项目/会话动作仍为 32–40px；SessionItem 的会话标题尚无原生键盘入口，需要保留拖动/选择/重命名/右键路径并修复。FeatureMenu 折叠分组的隐藏焦点、角色/团队选择器的关闭/清除/搜索尺寸与命名继续核查。主聊天欢迎/更多状态、文件卡片/代码/CSV/文档多主题及错误恢复、资源导入发布、助手/批量/渠道编辑器和剩余语言组合仍未全覆盖；保持目标进行中。原生设备、真实写入/认证/发送仍未验证。

### 2026-10-02：侧栏触控与菜单键盘路径

移动导航、分组/项目/会话动作及两类底部菜单统一为 44px；动作组 gap 0、导航行移除额外间距，保留正文和卡片留白。256px drawer 内项目/会话长标题截断，选择模式 header 同为 44px，重命名输入 44px/16px。品牌链接、关闭入口、项目与会话重命名字段有名称。桌面会话标题实测仍约 32px，未把手机尺寸带到桌面。

SessionItem 会话标题改为独立原生按钮，More 为兄弟控件，保留拖动、选择、重命名、右键路径。选择模式以标题 pressed 状态表达选中，原 16px 圆点仅作装饰，避免两个重复焦点入口。浏览器验证 Enter 激活、Space 选择不导航、Escape 取消草稿后回到标题；没有保存真实名称。

独立审查发现异步失焦保存结束会抢走新弹窗的焦点。两个失败测试覆盖 blur/Enter 保存期间转到下一个动作，修复为仅键盘完成编辑且焦点落到 body 时返回标题；失焦保存不主动抢焦点。桌面会话菜单补 group 名称、打开及子面板首项焦点、逐层 Escape 与边界 Tab；项目当前归属有 pressed 状态。三个失败测试后转绿，实际浏览器确认子面板 Escape 回主层、再次 Escape 回 More，末项 Tab 回下一个会话标题。

FeatureMenu 折叠分组 inert/aria-hidden，切换按钮 expanded/controls；打开先聚焦首个可见入口，Escape 返回功能按钮，边界 Tab 退出 portal 并移到相邻 composer 动作。弹层高度按入口上方可用空间约束，visualViewport offsetTop 只参与空间计算。320px 短屏实测无裁切，隐藏分组不会进入 Tab；展开增强后角色入口焦点环可见。软键盘偏移使用单测模拟，未据此声称真机键盘验证。

最终视觉自查发现菜单入口的 hover tooltip 悬浮遮挡菜单。在共享 Tooltip 的原生 child click 处理收起内部显示并清理触摸计时器，保留外部 open=true 的强制显示语义；相关测试先失败再转绿，独立复查未发现新 P1/P2。平板护眼主题实际确认菜单仍打开、重命名已聚焦、tooltip 数量 0。

截图记录：sidebar-320-dark-final、sidebar-more-390-light-final、sidebar-768-sepia-final、sidebar-1440-light-final、feature-menu-320-short-light-final。上述视口没有整页横向溢出；320px drawer 自身也无横向溢出，手机动作实测约 44px/gap 0。嵌套 More sheet Escape 只关闭子层并返回导航入口。宽度变化后已保存的折叠偏好可能在首帧后生效，按实际展开后的状态检查菜单，未把隐藏节点的 DOM 快照当作可见操作证据。

八项人工自检：排版保留衬线品牌/标题及次级元数据；正文留白保持；动作与内容层级分开；复用主题色及 theme-ring；保留已有过渡和全局 reduced motion；补原生按钮、命名、焦点边界和点击后 tooltip 收起；手机/短屏/平板/桌面及浅深护眼主题实测；维持 LambChat 视觉语言，无新依赖或装饰体系。未新增用户文案，复用现有五语 key；Impeccable 检查器仍不可用，按 DESIGN.md 清单人工检查。

最终验证：699 个测试文件 / 3359 项通过，lint 无警告，build/类型检查及体积门禁通过；eager JS 558642 / 559104 字节，precache 5007488 / 5242880 字节。未据当前批次宣告全界面完成。

继续待查：角色/团队选择器的关闭、清除、搜索尺寸与命名；主聊天欢迎/更多/流式状态；文件卡片、代码/CSV/文档多主题与错误恢复；资源导入发布、助手/批量/渠道编辑器以及剩余语言组合。原生设备、真实写入/认证/发送仍未验证，目标保持进行中。

### 2026-10-02：角色与团队选择器、共享网格和分页

开工同步 origin/develop 至 23715d9d，rebase 当前分支，保留远端关闭按钮与焦点修复。320px 深色实测角色卡片被两层 320px 下限裁切：pps-card 最小宽度与共享 auto-grid-cols 的轨道下限。分别改为 min-width:0、minmax(min(100%,320px),1fr)，同时覆盖使用同一网格的资源页与骨架。卡片正文/描述留白保持，手机右上动作 gap 0；手机及 coarse pointer 的按钮/搜索为 44px，搜索字为 16px。触屏规则的平板覆盖是 CSS 契约验证，未据此声称真机实测。

角色标题提供独立原生预览按钮，关闭有名称，筛选/置顶/收藏有 pressed 状态，复用 ResourceCardTags 保持单行标签与 +N。错误和重试沿现有 hook 经 composer 透传；无匹配与空库区分。长文案动作可换行；320px 浅色俄语实际确认按钮不溢出，整体横向溢出为 0。卡片入场延迟封顶 180ms，补 reduced-motion 的动画/位移回退。模式/工具/技能共享关闭按钮补名称、type、44px 和焦点环，未改正文节奏或增加依赖。

团队沿既有 API 支持的名称/描述/标签/成员字段进行服务端搜索与 20 条分页，替代只加载前 50 条的本地筛选。请求序号屏蔽过期响应，关闭时失效；错误提供重试，无匹配独立说明。实测第 4 页可达 61–65，搜索回第一页；新建先关闭旧弹层再交接。两个选择器持续挂载 Pagination，空页脚由 empty:hidden 隐藏，保证总数缩减的页码校正。共享分页增加最近 modal-surface 的滚动容器，浏览器从约 316px 滚动位置翻页后 scrollTop 为 0。

只读 preview 的 Agent ID 修正为真实注册 fast/search/team，团队入口可正常呈现。增加 fixture=error&failure=teams|persona-presets 精准列表故障，实际截图验证两类错误与重试；非 GET 仍 405，未执行真实写入。320px 深色角色/团队、320px 浅色俄语角色、390px 浅色错误、768px 护眼两列与 1440px 护眼三列均已截图；角色标题 Enter 打开、Escape 返回标题焦点、前后翻页均已操作。

八项自检：衬线实体标题及次级元数据保留；正文/卡片留白未压缩；主次动作与状态层级清楚；复用主题与焦点 token，团队去掉局部 stone 主题盲点；入场延迟缩短并尊重 reduced motion；原生入口/命名/焦点返回/错误重试补齐；上述四种宽度、三主题与俄语实测；维持 LambChat 品牌、现有卡片语言与原创产品结构，无新增装饰体系。Impeccable 检查器沿前轮确认的不可用状态，按 DESIGN.md 人工交付清单检查。

最终全量 723 文件 / 3444 项测试通过，lint 无警告，build/类型检查和体积门禁通过；eager JS 558787 / 559104 字节，precache 5018791 / 5242880 字节。中途一次全量出现既有 projectAndSearchComposition IME 测试不稳定，单独复查及之后两次全量均通过，未改该测试或搜索实现。三个独立代码复核未发现新 P1/P2；最终分页补充有两条先失败后通过的回归测试。

继续待查：主聊天欢迎/更多/流式状态；文件卡片、代码/CSV/文档多主题与错误恢复；资源导入发布、助手/批量/渠道编辑器，以及其余语言与选择器状态组合。原生设备/软键盘、真实写入/认证/对话未验证，目标保持进行中，不以本批代替全部界面验收。

### 2026-10-02：文件预览菜单、表格编码与主题

开工 fetch origin，origin/develop 保持 23715d9d，确认是当前分支祖先；仅在隔离 worktree 修改。手机文件库和预览工具栏本来已为 44px/gap 0，未再次压缩正文或卡片。实际发现 DocumentPreviewToolbar 的 More 菜单只有约 36px、无名称、打开焦点留在入口且方向键无效。复用现有 ResourceCardMenu，移除本地菜单 Escape 实现；共享菜单补默认已处理事件/IME guard，并消费 Escape，避免关闭上层预览。实测首项聚焦、方向键切换、Escape 只关闭菜单并回入口、Tab 到相邻关闭按钮；文件卡片菜单 Escape 同样回 More 入口。

修正只读 preview 的代码/CSV 卡片：分别提供对应文件 key、路径、URL 与内容，不再全部读取 Markdown。Markdown 样例增加多列表格、长代码和正文，Python 与 CSV 有实际长行/中文。真实浏览器代码、CSV 横向滚动均达到约 337px，整页横向溢出为 0。未用滚动容器存在冒充已操作滚动；未执行收藏、写入、下载或真实对话。

实际 CSV 中文乱码由 XLSX.read 的默认非 UTF-8 文本解析引起。先用真实组件测试观察失败，再对有效 UTF-8 的 csv/tsv 指定 65001。独立复核发现初版强制编码会回归 Windows-1252；增加旧编码 Résumé 字节用例，原生 TextDecoder fatal 检查无效 UTF-8 时保留原解析默认。UTF-8 无 BOM/有 BOM、旧编码、空 CSV、真实带图片 XLSX 均通过。空工作表不再由无范围/全空文本生成假空行，图片的网格范围仍单独保留。表头悬停内容栏由错误首数据行改为表头值，地址不再显示 A0；对应测试先失败后通过。

表格工作表切换补名称、pressed、原生 type、主题焦点环；手机/coarse pointer 控件至少 44px、按钮组 gap 0，桌面密度保持。768px 护眼主题实际发现表格大片纯白背景，ExcelPreview 与滚动条全部换用现有主题 token；深色同步复核。未改非交互表格的字号/行距。只读样例范围与编码验证用途补入 PANEL_PREVIEW.md。

视觉证据：document-more-320-dark-final、document-code-320-dark-scroll-final、document-csv-320-dark-final、document-md-390-light-final、document-csv-768-sepia-final、document-md-768-sepia-final、document-more-768-sepia-final、document-md-1440-light-final。上述手机/平板/桌面与三主题无整页横向溢出；390px 工具栏按钮约 44px、gap 0，桌面仍约 32px。长标题按现有 truncate 保留 title，阅读列和正文留白未改。

八项自检：标题/正文/元数据层级保留；阅读与卡片留白未压缩；主要动作与菜单分工明确；表格复用全部主题色；保留已有动效/reduced-motion，移除自定义滚动条过渡；原生菜单焦点、IME、Escape/Tab、表头反馈与错误编码补齐；上述四宽度/三主题实际检查；延续 LambChat 品牌与现有视觉语言，无新装饰体系/依赖。Impeccable 检查器沿先前不可用状态按 DESIGN.md 人工清单执行。

最终全量 723 个文件 / 3450 项测试通过，lint 无警告，build/类型与体积门禁通过；eager JS 558788 / 559104 字节，precache 5018613 / 5242880 字节。独立审查的编码 P2 已修正，最终复核无新增 P1/P2。

继续待查：文件/文档下载错误恢复、更多格式和图表导出菜单；主聊天欢迎/更多/流式状态；资源导入发布、助手/批量/渠道编辑器，以及剩余语言/选择器状态组合。原生触屏/软键盘和真实认证/写入/对话尚未验证。目标保持进行中，本批不是全界面验收结论。

### 2026-10-02：文档恢复与图表菜单、全屏触控

开工 fetch origin，origin/develop 保持 23715d9d，确认是当前分支祖先。文档加载错误在原有全高居中状态内提供重试，复用 common.retry 与 Button；手机实测 44px。HTML 请求失败不再被内部 catch 吞掉，旧文件异步请求在 cleanup 后失效，不能覆盖后来打开的文档或分配过期 blob。没有可读取来源的内联文档不提供无效重试。四条真实组件测试先失败后通过；Markdown 和 HTML 均可原位恢复，重试把焦点交给仍然存在的下载入口。

追踪 MarkdownRenderer 的实际调用链后修改 chat/ChatMessage/MermaidDiagram；documents/previews/MermaidDiagram 当前没有生产调用，未据文件名修改未使用组件。图表导出复用 ResourceCardMenu，portal 防裁切，首项聚焦、方向键、IME、Escape 和焦点归还沿共享实现。全屏复用 useDialogFocus，补 dialog 名称与 modal 语义；实际浏览器验证 Tab/Shift+Tab 留在全屏，Escape 仅关闭图表并回到原入口，文档保持打开。两个交互测试先红后绿。

手机图表动作 44px/gap 0，正文与卡片留白不改。视觉复查发现两个实际遗漏：内层 flex item min-width:auto 与 SVG inline max-width 使 320px 初始图表两端裁切；共享 ViewerToolbar 底部按钮仍只有 32px。补内层 min-width:0/max-width:100%，共享 SVG 样式优先约束实际容器宽度；初始 320px 画布 284px、SVG 252px，无图表自身横向溢出。共享 ViewerToolbar 手机/coarse pointer 的旋转、缩放、重置均 44px/gap 0，320px 控件整组约 290px，位于视口内；桌面实测仍 32px。保留手动缩放与拖动，图表过渡尊重 reduced motion。两条布局契约测试先红后绿，独立复核无新增 P1/P2。

只读 fixture 增加 failure=document：每个页面查询组合的文档首次请求 503，重试恢复；Markdown 样例包含真实 Mermaid 图表。浏览器标签页在预览服务重启后失去连接，使用同一浏览器的新检查页完成验证，没有把超时算作视觉证明。SVG 下载事件等待超时，但随后在本机找到当次生成的 diagram.svg，XML 有研究/设计/验证三个节点；PNG 当次文件为 787×139，实际查看确认三个节点与护眼背景完整。下载测试仅使用本机只读样例。

截图证据：document-error-320-dark-final、document-recovery-320-dark-final、mermaid-menu-320-dark-final、mermaid-fullscreen-320-dark-final、mermaid-inline-390-light-final、mermaid-inline-768-sepia-final、mermaid-menu-768-sepia-final、mermaid-inline-1440-light-final。上述四宽度与三主题整页横向溢出均为 0。八项自检：标题/正文/次级说明层级维持；内容留白保持；错误和恢复动作清楚；复用主题 token 与现有图表主题；保留原交互并补 reduced motion；菜单键盘、焦点边界、重试与实际导出核实；手机/平板/桌面实测；延续 LambChat 羊场景与既有视觉语言，无新增依赖或装饰体系。Impeccable 沿此前确认的不可用状态，按 DESIGN.md 清单人工检查。

最终全量 725 个测试文件 / 3458 项测试通过，lint 无警告，build/类型与体积门禁通过；eager JS 558776 / 559104 字节，precache 5018694 / 5242880 字节。代码和布局补充两次独立复核无新增 P1/P2。

继续待查：文件下载失败反馈、更多预览格式、Excalidraw 导出与大图表状态；主聊天欢迎/更多/流式状态；资源导入发布、助手/批量/渠道编辑器及其余语言组合。原生触屏/软键盘、真实认证/写入/对话尚未验证。目标继续进行，本批不代表全界面验收完成。

### 2026-10-02：绘图预览、恢复与导出

同步 origin/develop 至 b5a8930a 并 rebase 当前隔离分支；主 checkout 未修改。沿实际文件卡片调用链检查 ExcalidrawDirectViewer、ExcalidrawPreview 及两类缩略图。全屏的加载、错误、成功共用原有 ViewerTopBar / ViewerToolbar 与 useDialogFocus，补命名 dialog、键盘入口、IME Escape 边界和焦点归还。下载菜单改用 ResourceCardMenu；手机/coarse pointer 顶栏按钮 44px，底部继续复用此前共享的 44px/gap 0 规则，桌面底部仍 32px。内容和卡片留白保留。

实际发现成功后仍显示骨架的 imgLoading 条件反转，已修复。直接请求失败提供原位重试，重试先把焦点交给仍存在的关闭按钮；图片成功加载后骨架消失。ExcalidrawPreview 和 Thumbnail 用每次 effect 的取消标志屏蔽旧导出，缩略图及文件卡在 URL 切换时清空旧图。PNG 解码、canvas 或编码失败使用现有五语 downloadFailed 提示，临时 URL 在 finally 释放；不新增依赖或文案。九条组件回归测试均先观察失败，再转绿。

只读 fixture 增加真实三节点研究/设计/验证图，文件数更新为 196；failure=excalidraw 让缩略图和直接预览首次失败，实屏点击重试恢复。320px 深色、390px 浅色、768px 护眼和 1440px 浅色均截图，无整页横向溢出。实际操作菜单 ArrowDown、Escape、全屏 Tab 循环/关闭、重试、放大、旋转和重置；菜单 44px 且在视口内。SVG 当次本地文件 XML 有三个中文节点，PNG 1040×200 已查看，图形完整。加载未完成时的关闭由组件 pending-request 测试验证，未宣称实屏慢网或真机验证。

截图：excalidraw-320-dark-before / after / error、excalidraw-390-light、excalidraw-768-sepia、excalidraw-1440-light。八项自检：正文排版与阅读留白保持；主次操作及错误恢复清楚；内联表面复用主题 token，图形保留文件原色；过渡补 reduced motion；键盘入口、菜单、重试及导出已复核；四宽度三主题实际检查；沿用 LambChat 的组件和品牌结构，无另建装饰系统。Impeccable 沿已确认不可用的状态，按 DESIGN.md 清单人工检查。

最终全量 726 文件 / 3467 项测试通过，lint 无警告，build/类型与体积门禁通过：eager JS 558774 / 559104 字节，precache 5018820 / 5242880 字节。首次全量的 direct-viewer 安全区源码断言更新为共享 fullscreen owner；同轮既有搜索 IME 用例不稳定，单独复测及最终全量通过，未改搜索代码或该用例。独立代码审查未发现新增 P1/P2。

继续待查：通用文件下载失败反馈、其他预览格式、绘图内嵌图片和大图状态；主聊天欢迎/更多/流式状态；资源导入发布、助手/批量/渠道编辑器和剩余语言组合。真实服务认证/保存/聊天、原生触屏和软键盘尚未验证。目标保持进行中，不将本批作为全界面验收。

### 2026-10-02：欢迎页辅助操作、快捷键与聊天终态

开工 fetch origin，origin/develop 保持 b5a8930a，确认是隔离分支祖先。手机主聊天的顶部与输入栏原本已为 44px/gap 0，未继续压缩正文或卡片。欢迎页帮助入口实测约 22px、管理入口约 26px，改为共享按钮及手机/coarse pointer 的 44px；角色说明去掉叠加于主题次级文字上的额外 opacity，保留卡片留白和字号。推荐操作补主题焦点环；欢迎页在 reduced motion 下停用入场、悬停位移、滚动吸附与 shimmer。

帮助菜单复用 ResourceCardMenu，删除局部鼠标悬停与关闭实现。共享菜单增加原生 anchor 分支，帮助文档保留链接行为；箭头、IME、Escape/Tab、视口约束和焦点归还继续共用。快捷键弹窗补名称、具名 44px 关闭按钮，分类去掉额外淡化。320px 中文与俄语实际打开，长标签换行；俄语底部 goal 行经真实滚动可达，关闭后焦点回帮助。FeatureMenu 补 IME/defaultPrevented guard，避免候选确认 Escape 误关功能层。

RunStepsCollapse 工作行补稳定名称的 status，aria-live=off 避免每秒播报计时；工作和已完成文字均使用主题次级色。完成后的展开入口手机/coarse pointer 为 44px，有主题焦点环，桌面原密度保持。停止状态的重新回答改用共享 Button，容器可换行；独立复核指出内部 ui-button__label 的 nowrap 仍会截断，已对该入口的 label 补 normal/anywhere。320px 俄语实测重试 44px、内部 white-space normal、label 和整页溢出均为 0；未执行真实重试生成写操作。

只读 preview 新增 chat-state=working/streaming/error/cancelled；streaming 使用本机 GET SSE，6/12/18 秒逐段输出、24 秒结束，连接关闭清理定时器，API 写请求仍 405。实际观察等待→首段→完整正文→停止按钮恢复发送入口。错误样例揭示已有思考/工具 parts 时 message.content 的错误文字被渲染忽略，修复流式/历史共用 eventProcessor，追加去重的可见 text part，既有过程保留、取消分支保持。先失败后通过的测试覆盖两条共用路径和重复终态；浏览器失败态从只剩步骤变为显示请求超时。

截图：welcome-320-light-before/after、chat-help-320-light-after、chat-shortcuts-320-light-final、chat-shortcuts-320-ru-light/scrolled、chat-working-320-dark、chat-streaming-320-dark、chat-stream-complete-320-dark、chat-error-320-dark-after、chat-cancelled-320-ru-light、chat-report-390-light/768-sepia/1440-light。四种宽度与三主题整页横向溢出为 0，正文阅读与卡片留白保留；平板触屏规则由 CSS 契约覆盖，不据浏览器视口声称原生触屏验证。

八项自检：实体标题、正文、次级说明层级维持；内容留白保留；任务等待/完成/失败/停止可区分；次级文字与按钮复用主题 token；欢迎页 reduced motion 补齐、去掉局部重试旋转；原生链接、菜单导航、IME、焦点、滚动与状态反馈验证；上述宽度、主题与俄语实屏检查；沿用 LambChat 品牌与既有组件，无新装饰体系或依赖。Impeccable 按已确认不可用的环境状态使用 DESIGN.md 人工清单。

最终 727 文件 / 3477 项测试通过，lint 无警告，build/类型与体积门禁通过：eager JS 558790 / 559104 字节，precache 5017183 / 5242880 字节。独立复核的长标签 P2 已修正，最后复核无新增 P1/P2。

继续待查：欢迎页资源请求错误/空状态、Header More 的完整语义和关闭交互、消息内表格/代码辅助按钮的手机尺寸、其他工具过程及图片状态；通用文件下载失败、其他格式、绘图内嵌图片与大图；资源导入发布、助手/批量/渠道编辑器及剩余语言组合。真实服务认证/写入/聊天和原生触屏/软键盘尚未验证，目标继续进行，本批不代表全界面验收完成。

### 2026-10-02：顶部菜单、欢迎页恢复与原生焦点

Header More 复用 ResourceCardMenu，删除局部菜单、语言弹层和重复关闭逻辑。入口补 menu/expanded/controls，语言为 menuitemradio，返回后聚焦父菜单语言项。共享菜单支持初始项索引，箭头导航同时覆盖普通动作和 radio；菜单动作保持 44px，正文与卡片留白未压缩。实际检查 ArrowDown、Escape、语言 Back、通知打开/关闭；320px 俄语长主题标签换行到约 58px，没有横向溢出。独立复核指出外部侧栏通知事件不应强制聚焦 More，已用真实 opener 测试先失败后修复。

欢迎页角色加载失败原先误显示空列表/新建，现在区分错误，复用已有错误文案和共享重试按钮；团队请求状态保留失败标记。重试不卸载输入框，焦点回输入区；请求编号继续排除过期结果。只读样例支持 welcome-personas/welcome-teams 首次失败，团队样例默认 team，避免切换模式预取干扰首次故障。320px 深色角色与 390px 深色团队均实际重试恢复，组件测试验证输入框节点保留。

消息表格/代码的手机按钮原本已 44px，本轮保留布局，仅补 pointer:coarse 规则。实屏代码与表格复制均显示成功，表格 284px 容器内有 512px 内容，横向滚动实际到 227px；代码长行在自身 284px 容器内，整页不溢出。CSV 下载事件等待超时，随后确认本次生成的 table-1790886273621.csv，UTF-8 中文三列四行内容完整，未把超时本身当作成功证据。

原生浏览器关闭通知后焦点落在 BODY，揭示 jsdom 未实现 inert 导致既有测试漏报。共享 useDialogFocus 的恢复执行早于背景锁 cleanup，原生 inert 会拒绝聚焦；仅在 opener 仍处于 inert 区域时延迟到微任务，重新检查连接状态并复用新弹窗 ownership 保护。新增模拟原生 inert 拒绝焦点的测试先失败后通过，交接测试扩展为 inert 根节点；手机 More 与平板侧栏通知关闭后均实屏确认回到原入口。

截图：header-more-320-dark-after、header-more-390-light、header-more-320-ru-light、header-more-report-1440-light、welcome-error-320-dark-after、welcome-recovered-320-dark、welcome-team-error/recovered-390-dark、welcome-error-768-sepia、report-controls-320-dark。320/390/768/1440px、浅色/深色/护眼和中俄文字均无整页横向溢出。八项自检沿用既有排版与内容留白，菜单/状态层级明确，主题色和焦点环共用，未增加装饰或动效；此前 reduced-motion 规则保持，品牌与原生交互一致。Impeccable 按 DESIGN.md 人工清单检查。

最终 728 文件 / 3483 项测试通过，lint 无警告，build/类型与体积门禁通过：eager JS 558783 / 559104 字节，precache 5015083 / 5242880 字节。独立复核两次无新增 P1/P2，git diff --check 通过。

继续待查：欢迎页 @ 搜索无匹配与真实空状态的语义、消息复制失败反馈、其他工具过程和图片；通用文件下载失败、其他格式、绘图内嵌图片与大图；资源导入发布、助手/批量/渠道编辑器和剩余语言组合。真实服务认证/写入/聊天及原生触屏/软键盘仍未验证，目标保持进行中，本批不是全界面验收完成。

### 2026-10-02：助手与批量模型编辑器

同步远端并确认 origin/develop b5a8930a 已在当前隔离分支历史中。助手编辑器原有语言与图标入口约 22px，字段没有关联可见标签。本批复用 Button、Input、Textarea 与 useId，手机语言/图标入口 44px，语言组按容器自然换行，排序、名称和描述都有可读取标签；切换语言保留各自草稿。选中语言和图标使用已有 secondary 按钮样式，避免 ghost 样式覆盖局部背景，默认 Bot/空图标与实际渲染的机器人选项一致。

图标选择复用 ModalSurface，删除局部 outside-click 弹层和动画 emoji，沿用既有静态 3D 图标。实屏发现默认 300 层被 fullscreen editor 的 1000 层遮挡，先补回归再改用已有 1200 层。手机关闭按钮 44px、网格按钮约 46px；Escape 与选择均返回入口，外层编辑器保留。桌面亦确认 Escape 返回入口。

批量编辑复用 useId 关联共享字段与独立行字段，每行用编号命名 group；四种价格有持续可见标签。删除、添加、高级 disclosure 使用现有控件或原生 summary，手机删除入口 44px，删除行前聚焦仍保留的相邻行输入框。文件选择由可点击 div 改为原生 button，hidden input 放在按钮外；JSON 输入补 invalid/describedBy，解析反馈为 status。原导入 payload helpers 和共享配置补齐语义保留。俄语实屏发现旧 Base64 键缺失，改复用单模型编辑器已有五语键。

保存和导入失败保留草稿并可重试，批量校验/读取/API 错误统一进入现有 callout。实屏滚到底部后 body 顶部错误不可见，已改放固定 footer，在按钮上方。独立复核指出限高 callout 的垂直居中可能裁掉长文字开头，共享 owner 改顶部对齐和长词换行；受限错误支持键盘聚焦与原生滚动。只读 fixture 新增 editor-long-error，非 GET 仍返回 405，不保存或转发请求。1139 字符错误在 320px 下 top 481.71、文字 top 493.70，scrollTop 0 可读开头，128px 容器内 scrollHeight 763；PageDown 实际滚到 111.58px，底部按钮保持可见，整页横向溢出为 0。

TDD 先失败后通过：字段标签、语言草稿、图标 Escape/选择/默认状态、弹层层级、行分组/价格/删除焦点、持续保存与导入错误、footer 可见边界、无效 headers 不发送请求、JSON 文件键盘入口与解析状态、长错误顶部对齐。最后目标检查 5 文件 / 14 项通过，全量 732 文件 / 3492 项通过；lint 无警告，build/类型与体积门禁通过：eager JS 558787 / 559104 字节，precache 88 项 5015107 / 5242880 字节。独立复核的问题已修正，后续复核无新增 P1/P2；git diff --check 通过。

实屏截图：agent-editor-320-dark-after、agent-icon-320-dark-after、agent-editor-320-ru-dark、agent-long-error-320-ru-dark、batch-editor-320-dark-after、batch-editor-320-ru-dark、batch-long-error-320-ru-dark、batch-json-invalid-320-ru-dark、batch-editor-390-ru-light、batch-advanced-390-ru-light、batch-editor-768-ru-sepia、batch-editor-1440-ru-light、agent-editor-1440-ru-light、agent-editor-390-zh-light-final。320/390/768/1440px 与深色/浅色/护眼均无整页横向溢出；最终 390px 实屏再次确认语言选中背景/边框与默认图标状态。增删行保留已填价格 1.5，保存失败实屏保留本地草稿；成功重试由 API mock 测试覆盖，不据只读 fixture 声称真实保存成功。

八项自检：可见字段标签与标题层级清晰；正文和卡片留白保留；选中/加载/失败/可重试状态明确；控件和焦点环复用主题 token；去掉局部动画 emoji，弹窗沿用 reduced-motion；原生文件入口、键盘、Escape、焦点返回与错误滚动验证；上述宽度、主题、中俄语言检查；延续 LambChat 品牌和既有图标，无新依赖或装饰体系。Impeccable 按已确认不可用的环境使用 DESIGN.md 人工清单。

下一批优先：1440px 同时打开 docked 编辑器时，外层模型配置工具栏挤压说明文字，需按实际内容容器响应；助手全局/角色分配入口和 coarse pointer、角色分配保存路径；Feishu 与通用渠道编辑器字段/开关/QR/错误状态。其他待查仍包括欢迎页无匹配/真实空状态、复制失败、工具和图片、文件下载失败及其他格式、绘图内嵌图片与大图、资源导入发布及剩余语言。真实服务认证/写入/聊天和原生触屏/软键盘未验证，本批不代表全界面验收完成，目标保持进行中。

### 2026-10-02：模型工具栏与渠道编辑器

开工 fetch origin，确认 origin/develop b5a8930a 已在当前隔离分支历史中。模型配置的六个辅助动作占据桌面并列编辑器外层大量宽度，本批保留主动作添加，将导出/导入/批量/同步价格/重算费用放入现有 ResourceCardMenu。按实际 panel 容器响应说明与工具栏，正文和模型卡留白保留。共享菜单新增 disabled，禁用按钮不参与键盘导航，禁用链接移除 href 防止中键/右键打开；原先可用项的 initialFocusIndex 语义保留，无可用项时安全退出导航。同步与重算保留既有 API/结果/成功反馈，失败持续显示 callout，避免手机巨大重复 toast 遮挡操作。

Feishu 与通用渠道表单字段用 useId 关联可见标签，Select 和 shared ToggleSwitch 有可读取名称与状态，显式 false 和空串保留，缺失值按原 metadata default 显示。密码的留空保留提示移到输入框下并用 aria-describedby 关联，修复 320px 俄语提示挤压 App Secret 标签。保存失败保留草稿，复用 footer ConfigPanelErrorCallout；长错误顶部可读、限高可键盘滚动，不重复错误 toast，原成功提示保持。已有配置的空 secret 仍不发送，新配置必填验证与请求组装保留。Feishu 删除/保存复用 PanelFooterActions，手机保持单行 44px；原 native 删除确认未触发。

Feishu 扫码/手填和策略使用原生按钮与 pressed，长文案自然换行，表情使用共享 Button。固定 4 列手机/8 列宽编辑器避免 5 列布局的孤立末项，16 个按钮均至少 44px。补齐原来缺失的十个表情标签与音频提示词标签五语；扫码创建入口改共享 Button，loading/disabled 保留，320px 俄语实测从 36px、侵入卡片内边距改为 44px、完整落在卡片内。二维码保持正方形且受容器宽度约束。注册状态复核发现终态保留 QR 图时仍显示 Preparing QR，四条 success/error/expired/cancelled 测试先失败后修复：注册中按是否已有图显示等待扫码/准备二维码，结束后显示既有成功/失败翻译。未启动真实扫码注册。

共享 editor-sidebar 的 44px 规则覆盖 narrow 与 pointer:coarse；横屏/平板粗指针契约测试通过，Mac fine pointer 宽屏尺寸保持。只读 preview 增加通用渠道 text/password/select/toggle metadata，所有非 GET 仍返回 405、无转发或保存。实屏检查：模型 1440px 中俄并列编辑器、320px 俄语 More→Import JSON→关闭并返回 More 焦点、768px 俄语工具栏；Feishu 320px 中俄浅/深色、390px 俄语浅色、768px 俄语护眼、1440px 俄语深色；通用渠道 320px 俄语深色 Select/开关/失败保存。整页横向溢出均为 0。128px footer 错误容器内 763px 长文，PageDown 实际滚到 111.58px，按钮保持可见；成功重试由组件 API mock 覆盖，不把只读失败样例当作真实保存成功。

主要截图：model-toolbar-docked-before/after/menu-after、model-toolbar-1440-ru-light-final、model-toolbar-menu-320-ru-light-final、model-toolbar-320-ru-light-final、model-toolbar-768-ru-light-final、feishu-long-error-320-zh-dark-final、feishu-editor-390-ru-light-final、feishu-editor-768-ru-sepia-after、feishu-editor-1440-ru-dark-after、feishu-scan-320-ru-dark-before/after、channel-long-error-320-ru-dark-after。feishu-reaction-320-ru-dark-after 的文件名含 dark，但 HMR 后实际截图为浅色，不作为深色证据。

八项自检：可见标签/密码说明与说明文字排版清楚；正文/卡片留白保留；主动作/More、选中/禁用/等待/终态/可重试层级明确；复用主题 token 与已有 Button 变体；原有 reduced-motion 保持、策略切换补 reduced-motion；键盘菜单、焦点归还、状态命名、独立错误滚动与草稿保留验证；上述四宽度三主题和中俄实屏，五语标签契约验证；延续 LambChat 品牌及现有组件，无新增依赖或装饰体系。Impeccable 按已确认不可用的环境使用 DESIGN.md 人工清单。

所有新行为均观察 RED→GREEN。最终全量 736 文件 / 3508 项测试通过，lint 无警告，build/类型与体积门禁通过：eager JS 559051 / 559104 字节，precache 88 项 5016620 / 5242880 字节。初次全量的旧 mobile CSS 正则仅匹配单一屏宽 media，更新为 narrow/coarse 联合契约后通过；二维码终态补充后重新完成全量。首次新增五语翻译超过 eager 门禁，确认无代码调用后删除原已弃用的六个表情及两个飞书翻译键，未提高预算或删除在用翻译。终态 P2 修正后独立复核无新增 P1/P2；git diff --check 通过。

下一批优先：通用渠道与 Feishu 加载失败、连接测试/注册状态的持续反馈；助手全局/角色分配入口及 coarse pointer、角色分配保存路径。其他待查包括欢迎页无匹配/真实空状态、复制失败、工具和图片、文件下载失败及其他格式、绘图内嵌图片与大图、资源导入发布和剩余语言。真实服务认证/写入/对话、扫码注册端到端、原生触屏与软键盘尚未验证。目标保持进行中，本批不代表全界面达到验收标准。

### 当前执行：渠道请求恢复与状态反馈

- [x] ChannelPanel / FeishuPanel：已有配置加载失败不显示空白新建表单或写入按钮，保留 EditorSidebar 关闭路径，复用 EmptyState / panel-channels 场景与 Retry；测试先 RED 再 GREEN。
- [x] 两类连接测试失败使用既有持续 callout，可再次尝试；保存后的 status 请求独立处理，不把已完成的更新报告为保存失败。保留 credential payload 与五语文案，测试覆盖拒绝和恢复。
- [x] 只读 panel-preview 加首请求失败/重试恢复的配置 fixture，所有非 GET 仍 405。实屏检查手机、平板、桌面/三主题，错误、恢复、长文本和焦点；全量测试/lint/build、独立代码复核后提交。
- [ ] 继续助手角色入口及其他明确待查项，全界面完成仍需独立验收证据。

本批复核记录：加载请求和保存后状态刷新以现有实例加载代次保护；重试在按钮卸载前把焦点交给既有面板 root 或全页持久容器；扫码轮询忽略已完成/已清理请求的迟到结果。新增 15 个行为测试，初轮 10 个 RED，复核追加 5 个 RED，状态重试焦点追加 2 个 RED 后修复。独立复核最后未发现本批新增 P1/P2。

最终生产代码后验证：pnpm test 737 文件 / 3523 测试全部通过；pnpm run lint 零错误/零警告；pnpm run build（含 tsc）通过。Eager JS 559056 / 559104 bytes，precache 5016623 / 5242880 bytes；保留原有 chunk-size 提示，未提升预算。git diff --check 通过。没有新增依赖或文案，复用五种语言现有 key。

八项人工检查：排版使用原有标题和正文；留白保留正文节奏并居中错误态；视觉层级为关闭入口、错误说明、重试；色彩沿用主题和既有错误 callout；动效不新增，使用现有 reduced-motion 规则；微交互覆盖持续错误、重新尝试、焦点及迟到请求；响应式实屏核对 320 / 390 / 768 / 1440 CSS px 和 light / dark / sepia，俄语长文案没有横向溢出；原创性沿用 LambChat 自有羊角色场景。320 / 390 的重试实测约 44px，加载恢复后焦点位于持久面板容器。

截图在本地 interface-quality 目录：channel-load-error-320-ru-light-final.png、channel-test-error-320-ru-light-final.png、feishu-load-error-390-ru-dark-final.png、feishu-register-error-390-ru-dark-final.png、channel-load-error-768-ru-sepia-final.png、feishu-load-error-1440-ru-light-final.png、feishu-recovered-1440-ru-light-final.png。预览的失败注册请求由 405 拦截，不等同真实扫码端到端；软键盘、原生触屏和真实认证/写入未验证。ChannelsPage 列表失败/状态未知仍待下一批，未与编辑器恢复混作已完成。Impeccable 检查器在该环境不可用，按 DESIGN.md 交付清单人工检查。

### 当前执行：渠道列表与实例入口

- [x] 用测试区分实例列表 loading / empty / failed / recovered；目录失败在选中渠道也可恢复，避免重复初始化请求和迟到结果。
- [x] 未收到状态不标为禁用；状态失败可单独重试。保持渠道原有 banner，实例以原生链接支持键盘和新标签，窄屏名称与状态分层。
- [x] 只读预览故障恢复，四宽度/三主题实屏复查、完整测试/lint/build和独立复核后提交；助手角色项仍需继续。

本批 11 个行为测试都有 RED→GREEN 证据：初轮 5 个、目录刷新焦点 1 个、状态请求 pending 1 个、禁用摘要 1 个、后续导航读取 1 个、关闭刷新焦点 1 个、移动背景 inert 焦点恢复 1 个。保留后续选择渠道时刷新，仅跳过首轮重复读取；关闭编辑器刷新实例，详情路由退出后在下一帧检查当前焦点及新面板接管情况，再把空焦点恢复至持久页面；避免移动背景尚为 inert 时焦点被拒绝。Feishu 编辑器自行读取配置，父列表不再传可重复覆盖草稿的 initialConfig/status；1440 原生浏览器在只读 fixture 输入 cli_draft_preview 后刷新父列表状态，App ID 草稿未被覆盖。真实凭据、创建、删除和注册均未执行。

最终完整验证：pnpm test 738 文件 / 3534 测试通过；pnpm run lint 零错误/零警告；pnpm run build（含 tsc）通过，eager JS 559079 / 559104 bytes，precache 5016665 / 5242880 bytes；保留既有 chunk-size 提示。初轮 build 超预算 1 byte，删除五语已无引用的 channel.moreOptions 后恢复预算，未提高阈值。独立复核发现的再次导航不刷新问题已修复并覆盖；最后移动关闭焦点修复也有实屏与回归证据：320 下 #root.inert 由 true 变 false，最终 activeElement 为 DIV、tabIndex=-1、connected=true；独立复核最后未发现新增 P1/P2。git diff --check 通过。

八项自检：排版保留原有字体，实例名称独占主行；留白沿用 panel-body / panel-stack，正文没有整体压缩；层级把状态和创建时间降到次行；色彩为连接/断开/禁用/不可用提供文字区分并沿用主题；无新增动画，保留 reduced-motion；微交互覆盖链接键盘进入、关闭、失败持续展示、重试和草稿；响应式核对 320 light 列表失败/恢复、390 dark 状态失败/恢复、768 sepia 渠道卡片失败/恢复、1440 light 实例列表及 sepia 编辑草稿，均无横向溢出；原创性保留原渠道 banner 和 LambChat 羊角色场景。截图：channel-instance-list-320-ru-light-before.png / after.png、channel-instance-list-error-320-ru-light.png、channel-status-error-390-ru-dark.png、channel-catalog-error-768-ru-sepia.png、channel-instance-list-1440-ru-light-after.png、feishu-list-status-retry-preserves-draft-1440-ru-sepia.png、channel-mobile-close-focus-320-ru.png。

下一批：AgentSection / RolesAgentTab 的角色分配读取失败、持续保存反馈、tab 语义与触屏可用性；继续此前欢迎、文件/图片/工具、资源导入发布及剩余语言项目。真实移动触屏/软键盘、认证/写入/对话与扫码端到端未验证，整体目标保持进行中。Impeccable 仍不可用，本批按 DESIGN.md 清单人工检查。

### 当前执行：助手角色分配与窄屏入口

- [x] 先补行为回归：角色读取失败阻止编辑并可重试；保存失败保留草稿，保存一个角色不覆盖其他角色草稿，切换全局/角色不丢编辑；选择器键盘/焦点。
- [x] 复用共享 Select、Button、Checkbox、错误和空态，保留正文间距；长标题不被页头切换器挤掉，分配说明自然换行、移除无目的闪烁。
- [x] 四宽度/三主题实屏与只读保存失败、完整测试/lint/build、独立复核后提交。真实权限写入不在预览执行。


本批完成记录：角色分配读取异常不再转换为 []，AgentSection 与仍导出的 AgentConfigPanel 均阻止编辑，复用持续 callout / Retry；读取完整性以整区恢复保证，未把失败请求当作权限空值。加载代次和卸载清理阻止迟到结果，语言切换不再重新读取并清空草稿。RolesAgentTab 只持有修改过的角色草稿，保存仅清理当前角色，其他角色保持；保存期间禁用勾选和角色切换，失败持续显示、重试保留草稿，成功/失败的焦点均转至稳定容器。AgentSection 的全局/角色内容以原生 hidden 保持状态并从焦点/可访问树排除非活动内容。RoleSelector 删除 60 行自建菜单，改复用共享 Select，助手/模型两处都获得 portal、视口限制、方向键、Escape 和焦点归还；共享 Select 有 ariaLabel 时用原有可见值 id 提供 accessible description。

测试先看到 9 条角色恢复/保存/切换/选择器/空态 RED，再修复；页头布局 1 条 RED、共享选择器当前值描述 1 条 RED、matching skeleton 1 条 RED 后修复。初轮角色 tab 测试使用了错误的英文单数 label，改为 locale 的实际 Role Assignments 后验证通过；不将错误标签引发的失败作为相关逻辑缺陷证据。独立复核提出的当前角色读屏 P2 已关闭，最终未发现新增 P1/P2。最终生产代码之后全量 739 文件 / 3544 项测试通过、lint 零错误零警告、build（含 tsc）及体积门禁通过：eager JS 559079 / 559104 bytes，precache 5016888 / 5242880 bytes；保留既有 chunk-size 提示，未新增依赖或提高预算。git diff --check 通过。

八项自检：排版让助手页手机长标题完整显示、角色分配说明自然换行；正文留白沿用 panel-stack 与原有列表行，不全局压缩；页头/分配选择/状态/保存分层；主题沿用既有 token 和共享 primitive；移除角色草稿无目的闪烁与无效 animationDelay，切换尊重 reduced-motion；微交互覆盖整行 label 勾选、失败恢复、持久草稿、键盘和稳定焦点；实屏 320 dark、390 light、768 sepia、1440 light 的俄语和长中文角色名，无整页横向溢出；原创性保留 LambChat 羊角色场景及 serif 实体名，不加入无目的装饰。320/390 控件约 44px，整行勾选约 65px。1440 同时验证模型角色共用选择器的 ArrowDown / Escape；preview 保存请求返回 405，截图中失败不代表真实权限更新已验证。

截图：agent-roles-320-ru-dark-before.png / after.png、agent-role-load-error-320-ru-dark.png、agent-role-select-320-ru-dark.png、agent-role-save-error-320-ru-dark.png、agent-roles-390-ru-light-after.png、agent-roles-768-ru-sepia-after.png、agent-roles-1440-ru-light-after.png。浏览器 viewport 已恢复，原用户 tab 未操作。

继续优先：ModelSection / RolesModelTab 的相同读取失败与跨角色草稿风险，以及助手/模型顶级切换导致 section 卸载的草稿；审查所有 profile/user menu 的 Escape（本次 UI 在 profile 按钮按 Escape 后菜单仍可见，需定位实际 handler 与操作焦点）。继续此前欢迎无匹配/真实空态、复制失败、工具/图片、文件下载及其他格式、绘图大图与内嵌图片、资源导入发布和剩余语言。真实移动触屏/软键盘、认证/写入/对话与扫码端到端尚未验证。整体目标保持进行中，Impeccable 仍按已确认不可用环境使用 DESIGN.md 人工检查。

### 当前执行：模型角色分配与跨区草稿

- [x] 先补 RED：ModelSection / ModelPanel 读取失败不可当空配置，重试焦点；配置 None / [] 语义保持，删除全部模型后无旧数据；保存错误持久、跨角色草稿、等待锁定、分页、展开按钮与 label 分离。
- [x] 手机分配说明与批量操作分层，移除重计数 pill，复用共有控件、主题和间距；长模型名允许两行，保存操作在长列表可达；助手/模型和模型子区切换保留草稿，首次按需加载。
- [x] 四宽度/三主题实屏、长列表勾选/分页/失败保存、完整门禁和独立复核。权限只验证本地 fixture / mock，不写入真实服务。


本批记录：ModelSection 与仍导出的 ModelPanel 不再吞掉角色模型 GET 错误，完整读取成功后才同步模型列表与映射；configured=false 保持默认全模型语义，configured=true 的 [] 保持不允许任何模型语义。空模型刷新不保留旧列表。角色草稿仅清理已保存角色，保存期间锁定角色/勾选/批量动作，失败持续显示并保留选择。顶级助手/模型首次按需加载，访问后使用 hidden 保持状态；模型配置/角色子区同样保持挂载，后台读取用 inert 阻止编辑、稳定根容器接管焦点，读取失败隐藏编辑区，重试恢复原草稿。

手机分配说明独占主行，计数降为次级文字，批量动作相邻；移除多余蓝色 pill 和 List 图标，长模型名允许两行，详情展开按钮从 label 分离。原生实屏发现共享 .ui-button 的规则覆盖 min-h-11，当前模型批量/保存和助手角色保存以局部 !min-h-11 确保 44px；未改变全局按钮体系。模型保存栏粘在底部，错误与 Save 在同一可见区；分页位于保存栏之后，避免错误展开覆盖分页。320 长列表底部实际点击 Next 成功且前一页草稿保留。

独立复核发现两个 P2 并关闭：后台刷新卸载角色草稿（两项 delayed refresh / successful config mutation 明确 RED 2 failed 13 passed，再到 GREEN），以及独立模型编辑器保持打开时切到 hidden 分区，关闭后原 opener 不可聚焦。后一问题实屏 1440 复现 BODY，并用真实 EditorSidebar hidden/inert 两项 RED 2 failed 22 passed 后修共享焦点恢复；下一帧重新检查新 right-panel owner、可见 modal 和已有页面焦点，opener 不可见或 focus 失败时回到邻近可见分区按钮。原生顶级 Assistants 和子区 Models 两条路径修复后均聚焦可见 BUTTON。最终独立只读复核未发现新增 P1/P2。

新增共 19 项行为回归，None/[] 和跨页 bulk 保留原正确语义；错误标签 Select All 改为 locale 实际 Select all，hidden 配置区重复空态按可见容器判断，不把这些测试定位错误当成逻辑 RED。最终生产代码后：pnpm test 740 文件 / 3563 测试通过；pnpm run lint 零错误零警告；pnpm run build（含 tsc）与体积门禁通过，eager JS 559080 / 559104 bytes，precache 5017663 / 5242880 bytes，未新增依赖或提高预算，保留既有 chunk-size 提示。git diff --check 通过。

八项自检：排版保留 serif 实体名、长名称两行；正文留白沿用 panel-body / panel-stack，不整体收紧；页头分区、角色、分配说明、计数和批量操作分层；三套主题沿用已有 token，无新增品牌色；无新装饰动效，切换/展开/行反馈尊重 reduced-motion；微交互核对整行勾选、展开不勾选、分页、跨角色/顶级/子区草稿、持续错误、重试和焦点；实屏 320 dark、390 light、768 sepia、1440 light 及 dark 的俄语/长中文名称，无整页横向溢出，触控按钮约 44px；原创性保留 LambChat 羊场景和原产品视觉语言。ArrowDown 打开后应从实际聚焦的 option 按 Escape，菜单关闭且焦点回触发器；把工具 press 目标强制指回 trigger 的一次操作未当作正确键盘验证。

只读 fixture 新增 failure=model-role 首次角色模型 GET 失败，原生320 验证阻止编辑并重试恢复，focus=DIV/tabIndex=-1。保存 fixture 返回 405；真实权限更新未执行，成功 config mutation 的后台刷新由 mock 回归覆盖。截图：model-roles-320-ru-dark-before.png / after.png、model-roles-320-ru-dark-load-error.png、model-roles-320-ru-dark-save-error.png、model-roles-390-ru-light-after.png、model-roles-768-ru-sepia-after.png、model-roles-1440-ru-dark-after.png / light-after.png。viewport 已恢复，用户原 tab 未操作。Impeccable 仍按已确认不可用环境使用 DESIGN.md 人工清单。

下一批继续：profile/user menu Escape、欢迎无匹配与真实空态、复制失败、工具/图片、文件下载和其他格式、绘图大图与内嵌图片、资源导入发布、其余语言。真实触屏/软键盘、认证/写入/对话、扫码 E2E 尚未验证，整体目标保持进行中。


### 当前执行：头像菜单与页头弹层

- [x] 先补 RED：头像触发器命名/展开状态与桌面菜单语义；方向键、Escape/Tab、IME 保护及焦点归还；手机关闭按钮与独立 Profile 弹层交接；权限过滤、页面导航和 resize 清理。
- [x] UserMenu 桌面复用 ResourceCardMenu 的 portal、视口限制和键盘；共享菜单支持已有界面的分隔/分组标题，手机保持 ModalSurface，点击区域至少44px，分组文字沿用主题并改善可读性，动效尊重 reduced-motion。
- [ ] 四宽度/三主题及短屏实屏复查，核对头像与更多菜单互斥、遮挡/滚动和焦点；全量测试、lint、build 与独立复核后提交。继续整体界面审查，真实 logout/权限写入不执行。

本批 UserMenu 移除重复桌面 portal、click-outside 和遮罩，复用 ResourceCardMenu 的视口限制、语义、键盘与焦点。共享 action 支持现有账号菜单的组标题、分隔和当前页面；权限过滤与导航保持原语义。手机仍复用 ModalSurface，增加 sticky 账号/Close 区域，按钮44px，分组由10px低透明文字改为12px主题次级文字；移除重复入场动画，保留共享 reduced-motion。

最初命名缺失阻止10项行为测试进入后续路径；补最小ARIA后再运行，9失败/1通过明确后续行为RED。共享分组独立RED 1失败/9通过。实测 resize 触发非Node target的 contains TypeError，独立RED后以 instanceof Node 修共享owner。独立复核指出 resize 焦点掉到 BODY，增加仅原菜单持有焦点时归还（新对话控件已聚焦时不抢焦点），3项RED后GREEN。窗口resize capture监听先于响应式owner的bubble卸载，flushSync回归RED 1失败/12通过后修，目标套件24项GREEN。

原生手机 Profile→个人设置→关闭曾返回BODY：最初jsdom缺少inert边界误通过，随后沿用 modalSurface 测试的native inert模拟，确见RED 1失败/10通过。Profile action下一帧先解除sheet背景锁，再聚焦稳定头像并打开新dialog，测试与原生390验证关闭后焦点均回头像。Tab按浏览器默认顺序进入下一页面控件，不要求停留头像；手机fireEvent opener先明确focus，修正这两项测试期望，不当作生产故障。

实屏覆盖320 light、390 dark、768 sepia和1440 light；390×480手机短屏内部滚动约116px，Close仍可见，所有动作约44px、整页横向溢出0。768×360桌面菜单视口内限高344px，End使退出项完整可见并聚焦，仅按Escape退出而未执行Logout。1440方向键、Home/End、Escape，More→头像及头像→More均只保留一个menu；390 More→头像交接与关闭焦点通过。before桌面截图文件名含1440，但当时实际CSS视口1347×757，不能当成1440证据。原生 pressKey(null)曾使菜单消失/焦点BODY，之后从实际聚焦menuitem用locator press完成正确键盘验证。

浏览器 viewport API 的1440→768操作仍在关闭菜单后呈现BODY焦点；capture顺序修正与临时BODY恢复探测都未改变该工具结果，BODY探测已移除，不做猜测补丁。这条原生焦点验证未通过，后续需区分viewport API的焦点重置和实际窗口resize；目前行为测试证明菜单有焦点时归还、新dialog已有焦点时不抢、owner卸载前处理。用户原tab未操作，临时viewport已reset。

八项自检：保留serif账号与14px动作、组标题12px；正文和卡片留白不整体压缩；个人/管理/系统/危险操作分层、当前页柔和高亮；light/dark/sepia沿用主题token；无新增装饰动画、尊重reduced-motion；操作名/aria-expanded/aria-controls、键盘、IME、菜单互斥、滚动和modal交接已核对；四宽度及两种短屏无横向溢出；沿用LambChat头像与视觉语言，无新增依赖/品牌体系。Impeccable按已确认不可用环境使用DESIGN.md人工清单。

截图位于既有interface-quality目录：user-menu-320-ru-light-before.png / after.png、user-menu-390-ru-dark-after.png、user-menu-390-short-dark-top.png / scrolled.png、user-menu-768-short-sepia-after.png / end.png、user-menu-1440-ru-light-after.png。继续欢迎无匹配/真实空态、复制失败、工具/图片、文件下载与其他格式、绘图大图/内嵌图片、资源导入发布和其余语言；真实触屏/软键盘、认证/写入/对话与扫码E2E尚未验证。整体目标保持进行中。

最终生产修改后验证：pnpm test 741文件/3578项通过（新增15项）；pnpm run lint零错误零警告；pnpm run build含tsc与体积门禁通过，eager JS 559076/559104 bytes、precache 5018025/5242880 bytes，未提高预算，保留既有chunk-size提示。git diff --check通过。独立只读复核关闭resize焦点与Profile交接问题，最后capture监听/cleanup成对及flushSync回归未发现新增P1/P2；明确不把测试证明等同原生viewport操作焦点通过。继续整体审查，当前第三项因这条验证边界保持未全勾选。

### 当前执行：欢迎页无匹配与真实空态

- [x] RED：persona/team 搜索无匹配不可称真实空库、保留draft与composer；成功空库以status反馈，loading/error不伪空；入口管理导航。
- [x] 复用既有五语文本和Button；管理入口合并重复分支，筛选时保留gallery区域/宽度使编辑位置稳定，真实空库紧凑展示；不清空用户草稿、不新增组件或依赖。
- [x] 四宽度/三主题、匹配/无匹配/空库/错误/恢复实屏和焦点，完整门禁与独立复核后提交；记录移动键盘/原生viewport焦点等未验证边界，继续整体目标。


本批完成：空库判断改用已加载完整persona/team集合，筛选结果为空独立展示既有五语no-match和筛选提示；成功空库以status展示，loading/error不伪装空库。管理入口合并四个重复分支并复用Button，导航到原资源管理页，移除没有打开创建流程的“New”暗示。筛选开始时记录实际gallery高度，以min(40dvh, prior height)维持区域，清空查询/更换资源/停止welcome投影时清理记录；输入草稿与focus保持，单行小集合不被强制撑成两行。删除无内容prompt-grid，gallery宽度不因筛选归零切换。

先看到四项persona/team空库与无匹配行为RED（4失败/2通过）再修复；现有管理导航source断言改为两个真实MemoryRouter路由行为测试，共新增六项。目标5文件55项通过。fill空字符串未清Lexical实际状态，改用真实Meta+A/Backspace确认清空，不把工具清空失败当逻辑回归。

原生320发现共享ToolbarChip外层缩到约10px但内部button44px：Agent中心点击实际命中Sandbox，真实选择器也打开Sandbox。修包装器最小44px与左组两目标88px底线，整组空间不足则换行；桌面html:has(workspace) nowrap覆盖手机规则，现仅640px起应用。独立复核指出min-content会锁住长名称，改固定两个目标底线，让label照常truncate；390选“跨部门项目协作与长期计划复盘 06”后六主按钮同一行、各在composer内、无交叠。Clear hidden被chat-tool-btn display:flex覆盖，改!hidden sm:!flex，手机AX移除该不可见入口、display:none/rect0；更换入口仍可达。

继续640断点时，侧栏留下211px composer，发现按钮中心hit虽正确但实际区域部分重叠；已有composer容器查询max320px新增组换行和72/36px桌面底线，手机后加载保留88/44。修后640 pairwise overlaps=[]且全在容器内，1440仍nowrap；原composerSingleRowSource全局禁止wrap断言先失败，更新为宽栏单行/窄容器换行，不把旧断言失败当行为RED。窄栏绝对placeholder换三行超出45.6px editor并覆盖toolbar，共享提示加右内距、单行ellipsis；实际draft仍多行，修后placeholderBottom370.82 < toolbarTop380.43。

最终生产修改后：pnpm test 741文件/3584项通过；pnpm run lint零错误零警告；pnpm run build含tsc及体积门禁通过，eager JS 559065/559104 bytes、precache 5017991/5242880 bytes。未新增依赖或提高预算，保留既有chunk-size提示；git diff --check通过。独立只读复核关闭长名称P2，容器查询与提示文字最后复核未发现新增P1/P2；未把源码复核当原生验证。

八项自检：排版保留serif及14px状态，提示截断不改变输入内容；正文/卡片留白沿用原有节奏，仅工具栏间距收紧和必要换行；资源标题/管理入口/无匹配说明分层；三套主题使用原token和已有五语；无新装饰动效，保留reduced-motion；微交互实点Agent、团队选择、更换入口、无匹配恢复、失败retry及composer焦点；320 dark/390 light/768 sepia/1440 dark和640 light断点无整页横向溢出，320主按钮约44px且pairwise overlaps=[]；保留LambChat羊角色场景，无新增品牌体系。768 persona失败retry后20卡片恢复、focus=textbox；390真实persona/team空库分别status=Нет персон/Нет команд；1440 persona无匹配保持focus=textbox，320 team无匹配输入top206.97不变。一次persona卡片选择被只读fixture拒绝，不当成真实persona选择成功；long-name采用本地team选择路径验证。

截图保存在既有interface-quality目录：welcome-320-dark-start.png、welcome-320-dark-no-match-before.png/after.png、welcome-320-dark-toolbar-after.png、welcome-320-light-empty-before.png、welcome-390-light-empty-after.png、welcome-390-light-team-empty.png、welcome-390-light-long-name-after.png、welcome-768-sepia-error.png/recovered.png、welcome-1440-dark-after.png/no-match.png、welcome-640-light-toolbar-after.png。320/390/640截图在最后placeholder调整后重拍；768截图记录读取失败和恢复时状态，不能当作最后placeholder单行变化的截图。viewport已恢复，用户原tab未操作。

继续整体审查：选定团队无starter prompts时欢迎区标题仍回退“角色”而非团队（现有路径，下一批修）；复制失败、工具/图片、文件下载和其他格式、大图/内嵌图片、资源导入发布及其余语言。原生viewport API关闭菜单后的BODY焦点边界仍未证实；真实触屏/软键盘、认证/写入/对话、扫码E2E仍未验证。整体目标保持进行中。Impeccable沿用已确认不可用环境的DESIGN.md人工清单。


### 当前执行：共享复制反馈与工具参数操作

- [x] RED：失败不显示已复制且可重试、pending不重复、legacy失败清理/焦点；工具参数复制与展开分离、undefined保留；选定无starter prompts团队标题。
- [x] 复用共享CopyButton与IconButton，删除重复参数复制handler；手机44px与键盘可见，沿用主题、五语反馈；预览只读clipboard首次失败和tools样例。
- [x] 四宽度/三主题复制失败/重试、参数展开和键盘、团队路径实屏；最终全量测试/lint/build、独立复核、清理后提交，继续独立消息/代码/表格复制和其他整体事项。


本批完成：共享 CopyButton 复用 IconButton，确认 clipboard 成功后才显示已复制；失败保留可重试按钮、五语短提示和 aria-description，pending 阻止重复，text 改变/卸载忽略旧请求并清 timer。legacy execCommand false/throw 均拒绝 Promise，finally 删除 textarea 并恢复键盘焦点。ToolArgsBlock/ToolArgsDisplay 删除重复 handler，复杂参数改展开 button 与 CopyButton 并列，undefined 保留；手机和 coarse pointer 44px，桌面 hover/focus 可见，参数复制图标12px。ToolHoverCopyButton/CodeMirrorViewer 的 hover 容器同时支持 focus-within；选定无starter prompts团队仍显示团队标题。

TDD：核心失败/重复/legacy清理及团队标题5项行为RED后GREEN；参数命名/键盘展开分离/undefined与本地化3项RED后GREEN；补3项旧请求、卸载、timer覆盖。完整套件原snapshot路径断言因新的独立button层级失败，改为真实收起后恢复行为，未削弱恢复契约。第一次Toaster测试缺matchMedia只是环境失败，补stub后明确inert祖先断言RED再修，不计环境失败为行为RED。

原生发现Toaster在inert root内，提示虽可见但AX忽略；把既有Toaster提取为lazy AppToaster并portal到body，沿用sidebar offset，默认反馈使用主题token、14px正文和共享关闭按钮44px，自定义toast保留原路径。实际inert RED→GREEN。鼠标关闭Toast原会抢焦点，1秒卸载后落BODY：onMouseDown保留当前操作，键盘关闭时归还当前顶层modal。独立复核与原生继续发现ToolResultPanel外dialog不可focus且内panelRef使Tab/Escape equality守卫不生效；外层加tabIndex=-1，共享Tab/Escape改contains关系，surface Tab/ShiftTab进入first/last。真实ToolResultPanel focus1项、Tab2项、Escape/嵌套2项分别RED后GREEN，IME/defaultPrevented/fullscreen守卫保留。

实屏：320×673 light、390×844 dark、768×1024 sepia、1440×900 light均整页横向溢出0。320/390三个工具copy均约44×44；768/1440当前fine pointer约32×32，768键盘focus-visible opacity=1。320/390/768首次失败与重试实际clipboard匹配query JSON字符串/compact options JSON；第一次把显示的pretty JSON当复制格式导致校验false，复核源码后以原compact契约确认true，不当作复制失败。390键盘关闭Toast→focus=dialog，ShiftTab→末copy，末copy Tab→selected tab；鼠标关闭Toast保持原copy焦点。320 Escape关闭工具且返回原工具入口；嵌套弹层边界由行为测试覆盖，未声称原生嵌套通过。390本地团队选择/更换均保留草稿，标题为Площадка команд；两次操作焦点仍落BODY，这条后续继续处理。未执行真实API写入或模型请求。

八项自检：参数原有排版/serif保留、copy图标12及提示14；正文卡片留白不整体压缩；参数/结果/失败反馈层级清晰；三套主题及五语沿用token；无新增装饰动效，沿用reduced-motion；复制成功/失败、重试、展开、焦点与键盘边界实际核对；四宽度无横向溢出，触屏规则44px但真实触摸/软键盘未验证；保持LambChat视觉语言，无新依赖/品牌体系。Impeccable沿用已确认不可用环境的DESIGN.md人工清单。

最终生产修改（含14px Toast文字）后：pnpm test 745文件/3603项通过（新增19项）；pnpm run lint零错误零警告；pnpm run build含tsc与体积门禁通过，eager JS 558782/559104 bytes、precache 5019661/5242880 bytes，未提高预算，保留既有chunk-size提示。独立最后只读复核未发现剩余P1/P2，未把源码复核当原生或全量验证。git diff --check通过。首次构建559271超限，精简重复提示/clipboard语法后仍559188超限；共享Toaster独立lazy owner后回到预算内，未绕过门禁。

截图在既有interface-quality目录：copy-320-light-failed-final.png、copy-390-dark-final.png、copy-768-sepia-final.png / keyboard-final.png、copy-1440-light-final.png、welcome-390-dark-selected-team-final.png。早期copy-390-dark-success.png曾记录首次失败，不能当成功证据；最终截图以上述final文件及实际clipboard布尔结果为准。临时viewport已reset，用户原tab未操作；原clipboard为空项数组，write([])接口拒绝后以空文本恢复空内容，未输出用户clipboard。

继续：欢迎团队选择/更换后的编辑焦点、独立消息/代码/表格/绘图复制及文件路径/分享的失败反馈；其余图片、下载、格式、大图/内嵌图片、资源导入发布、语言与真实触屏/软键盘、认证/写入/对话、扫码E2E。原生viewport API关闭菜单后的BODY焦点边界仍未证实。整体目标保持进行中。

### 当前执行：团队编辑焦点与消息、代码、表格复制

- [x] RED：选择/更换团队保留草稿并请求编辑焦点；用户/助手消息、代码块、表格等待实际复制，失败可重试；同一按钮重试替换旧错误反馈。
- [x] 复用已有 Lexical focusRequest 与 CopyButton，删除四处重复状态、timer 和乐观成功反馈；复用 Button 支持表格文字标签与点击时读取内容，保持正文留白及原复制格式。
- [x] 手机、平板、桌面实屏与键盘/剪贴板核对，完整门禁、独立复核后提交，继续行内代码、绘图、文档、文件路径与分享等剩余入口。

本批完成：WelcomePage 的本地 composerFocusRequest 与既有外部计数相加，选/换团队沿用 RichChatComposer 的实际 Lexical selectEnd 路径，不重新挂载或清空草稿。用户/助手消息、Markdown 代码块和表格改用共享 CopyButton，确认成功后才反馈、pending 禁止重复、失败可重试；删除四处复制状态与 timer。共享组件复用 Button，图标形态保留 ui-icon-button，表格 showLabel 保留文字和11/12px层级；表格 getter 仅在激活时读取 DOM 并保留原 Markdown 序列化，代码仍去掉尾部换行。新增 useId 对每个按钮的 Toast 单独更新：同一按钮成功重试替换旧失败提示，其他入口不互相清除。

TDD：首轮两个测试因 i18n mock 缺 initReactI18next 与 Welcome 尚处 skeleton 而失败，修测试环境并等待实际 composer 后，明确团队焦点和用户/助手 pending 三项行为 RED；代码块/表格 pending 与延迟内容 getter 三项 RED；实屏发现重试后旧失败提示仍与成功共存，新增同一 Toast 更新契约一项 RED 后修。新增七项，原 action-order 源码守卫随真实 CopyButton 入口更新，顺序不变。Welcome 行为测试使用模拟 composer 的 focusRequest 契约，真实 Lexical 光标由下述原生证据补充，未把模拟 focus 当 selection 证明。

原生：旧临时 tab 7 的 CDP focus 命令超时，按浏览器文档创建同一浏览器内独立 tab 8 后继续，未借用其他控制方式或操作用户原 tab。390 dark 选择/更换团队均保留“保留这段待发送草稿”，焦点为 textbox、DOM selection collapsed 且 offset=9、位于真实编辑器内；从实际 :focus 继续输入得到“保留这段待发送草稿，继续”。1440 light 以 Enter 选/换团队，offset=6 并续写得到“保留桌面草稿继续”。320 light、390 dark、768 sepia、1440 light 整页横向溢出均0，手机复制约44px；768/1440 fine pointer 图标按钮约32px，768 Enter 复制时 focus-visible=true。真实 coarse pointer/软键盘没有验证。

390 表格首次失败后 aria-description 清除，随后按已观测实际 class 定位，不把 selector timeout 当复制失败；此前格式化产生 HMR，但没有证明这次状态重置的原因。重试实际剪贴板与整张对齐 Markdown 精确匹配，代码完整精确匹配，用户消息原文精确匹配，助手复制保留 Markdown 标题、表格和完整代码围栏。320 首次代码失败后 Enter 重试实际代码匹配；最初两个 Toast 同时出现，修 useId 后重新加载，实屏只剩一个“Скопировано!” status。一次紧邻 press 的 snapshot 仍含旧文案，但之后同次只读 DOM 与最终截图已是单一成功状态，不以早期 snapshot 当最终结果。390 几何检查的下方两个 hit=false 位于视口外，实际点击会滚入可见区域；320 当前可见代码按钮中心 hit=true，不称所有离屏元素点击命中。

八项自检：保留正文与 serif 层级、表格小字和代码图标；不整体压缩卡片/正文留白；图标行动、表格动作和状态分层；沿用 light/dark/sepia token 及已有五语文案；无新增装饰动效、沿用 reduced-motion；真实复制失败/重试、提示更新、Enter、团队焦点/续写；四宽度无横向页面溢出，手机44px与桌面32px；保留 LambChat 视觉语言，没有引入新品牌、依赖或组件体系。Impeccable 沿用已确认不可用环境的 DESIGN.md 人工检查。

最终修改后门禁：pnpm test 746文件/3610项通过；pnpm run lint 零错误零警告；pnpm run build 含 tsc 与预算通过，eager JS 558778/559104 bytes、precache 5017922/5242880 bytes、91 entries，未提高预算，保留既有 chunk-size 提示。初次构建发现误删了比较单元格仍使用的 Check import，恢复后重新构建；最终 useId 修改后全量三门重新运行并通过。独立两次只读复核未发现本批剩余 P1/P2，复核者未重复执行原生/全量门禁，边界明确。git diff --check 通过。

截图位于既有 interface-quality 目录：team-focus-390-dark-after.png、team-focus-1440-light-after.png；message-copy-320-light-failed-final.png / retry-final.png、message-copy-390-dark-final.png、message-copy-768-sepia-keyboard-final.png、message-copy-1440-light-final.png。早期 message-copy-390-dark-failed.png / code.png / user.png 与 message-copy-320-light-failed.png 在 Toast ID 修正前，不能当最终提示更新证明。剪贴板在确认仍是本批写入的代码后恢复测试前内容；临时 viewport 已 reset，tab 8 保留供继续检查。旧临时 tab 7 的关闭尝试仍在 CDP focus 超时，未声称已关闭，也不再重复操作。

继续：行内代码、绘图、文档、文件路径与分享复制；图片、下载与其他格式、大图/内嵌图片、资源导入发布、其余语言和真实触屏/软键盘、认证/写入/对话、扫码 E2E。原生 viewport API 关闭菜单后的 BODY 焦点边界仍未证实。整体目标保持进行中。

### 当前执行：绘图、文档与行内代码复制

- [x] RED：文档链接与绘图等待确认时禁止重复；行内代码可通过原生按钮操作；失败反馈保留重试。
- [x] 提取已存在的复制状态处理供实际入口复用，保留菜单/全屏工具栏语义及正文留白。
- [x] 实屏、键盘、剪贴板和响应式核对，完成测试/lint/build 与独立复核后提交；整体目标继续。


本批完成：把既有 CopyButton 的复制请求、反馈、失败、timer 与旧请求忽略逻辑原样提取为 useClipboardCopy，供实际文档正文、文档链接、行内代码和 Mermaid 全屏复用；普通/streaming/错误 Mermaid 复用 CopyButton，删除原重复状态与 handler。菜单复制等待时 disabled，失败可重试，链接使用共享 clipboard helper 保留绝对 URL 与 legacy 路径。行内代码改原生 button，保持正文中的小尺寸和阅读节奏；useId/aria-describedby 保留实际代码值，失败同时追加可读错误。真实文档 Markdown 经过共享 chat MarkdownContent/MermaidDiagram；旧 documents/previews/MermaidDiagram 无生产 caller，本批没有修这个死副本或将其源码守卫当实际视觉证明。

TDD：文档链接 pending、普通/全屏绘图 pending、行内按钮四项明确 RED→GREEN；补三项链接/绘图失败恢复，共享 CopyButton 原七项继续保护生命周期。独立复核发现行内 aria-label 覆盖代码值，补 accessible description 断言明确 RED 后修；后续 retry 的即时断言失败是测试未等待 async completion，改 findByRole 后通过，未将此当生产问题。原生发现 sepia 默认 Mermaid 紫色，与产品暖底不协调，新增 palette 行为一项 RED→GREEN；真实共享 Mermaid 使用 base 主题并读取现有 card/text/border/secondary/cluster tokens，background 继续 themeExportBackground，darkMode 随主题。已有 chat theme source 守卫更新到真实 token 契约，未修改死副本守卫。新增8项测试，未新增依赖或提高预算。

原生：旧临时 tab8 CDP focus 超时，按文档用同一浏览器新 tab9 继续，未操作用户原 tab。为新增行内样例重启已确认的 preview session85826；当前运行 session35138，3002 只读 fixture。首次聊天文件正文读取的是已有精简样例，其复制实际成功；早期截图已改名 document-content-390-dark-early-success.png，不当失败证明。含绘图样例在文件库实际 Markdown 卡片，未把相似路径的精简样例当同一内容。

390 dark 行内 Enter 首次失败，aria-describedby 同时保留 delivery_count 与错误；Space 重试实际 clipboard 精确 delivery_count，单一成功 status。390 绘图全屏 Enter 复制实际原 chart 精确匹配，Escape 保留父文档并返回 fullscreen 入口；320 light 全屏首次失败，aria-description 确认错误后 Enter 重试原 chart 精确匹配；普通绘图复制同样精确。320 文档链接为 http://127.0.0.1:3002/preview-document.md 精确匹配；768 sepia 链接首次失败后键盘重试精确匹配、单一链接成功 status、焦点返回 More。1440 light 正文首次失败后重试与完整447字符 Markdown 精确匹配，保留标题、行内 token、表格、两段代码围栏；焦点返回 More。桌面预览实际为 complementary，第一次沿用手机 dialog selector 超时后从新 DOM 纠正，不当加载失败。

最终 palette 后重新实屏：320 light、390 dark、768 sepia、1440 light 整页横向溢出均0。手机顶部 source/download/more/close 与绘图动作约44px，间隔沿用紧凑 gap；行内代码约28px高且宽130px，属于正文内文本行动，保持阅读节奏。768 sepia 节点实际 fill rgb(250,246,234)、stroke rgb(221,210,184)；390 dark fill rgb(30,27,24)、stroke rgb(61,56,53)，不再套默认紫色。主题修改 HMR 重置了预览面板，按实际卡片重新打开并等代码加载后保留最终截图。

八项自检：正文 serif 与层级、14px 行内代码和小动作字保留；正文/卡片留白不统一压缩；标题/辅助 metadata/动作与复制反馈分层；三主题节点沿用 token，失败/成功状态可辨；无新增装饰动效并沿用 reduced-motion；Enter/Space、失败/重试、单一提示和 Escape/focus 证实；四宽度无整页溢出、长行/宽表格局部滚动沿用；保留 LambChat 品牌语言，未新造设计系统。Impeccable 沿用已确认不可用环境的 DESIGN.md 人工检查。不同 Mermaid 图形类型、大图阅读/缩放、PNG/SVG 导出以及真机触摸/软键盘仍待后续验证，未由三节点样例推断全部通过。

最终配色修改后门禁：pnpm test 746文件/3618项通过；pnpm run lint 零错误零警告；pnpm run build 含 tsc、Vite、PWA 与体积门禁通过，eager JS 558771/559104 bytes，precache 5017151/5242880 bytes、91 entries，未提高预算，保留既有 chunk-size 提示。独立最后两轮复核已关闭行内 P2，最终复制链路和追加主题 diff 未发现剩余 P1/P2；复核者只读核对实际库实现和调用链，不声称运行原生或全量门禁。git diff --check通过。

最终截图沿用 interface-quality 目录：document-copy-320-light-final.png、document-copy-390-dark-final.png、document-copy-768-sepia-final.png、document-copy-1440-light-final.png；inline-copy-390-dark-failed.png；mermaid-copy-320-light-failed.png / retry-final.png、mermaid-copy-390-dark-final.png；document-link-768-sepia-failed.png、document-content-1440-light-failed.png。复制流程截图在节点 palette 调整前，最终页面 screenshot 在配色后；不混同两者。剪贴板在确认仍是本批完整 Markdown 后恢复测试前内容，临时 viewport reset，tab9 handoff 供继续。旧 tab8 仍有 CDP focus 问题，不重复操作、不声称已清理。

继续：文件路径和分享复制、图片/下载/格式、大图与内嵌图片、资源导入发布、其余语言、真机触屏/软键盘、认证/写入/真实对话、扫码 E2E；小屏大图缩放与节点文字可读性需继续检查。整体目标保持进行中，不以本批复制和三节点主题样例宣称全界面没有可提升之处。

### 当前执行：分享复制与文件路径菜单

- [x] RED：会话/项目分享等待复制且失败可重试；创建已成功时复制失败不误报创建失败；路径菜单等待、返回实际入口与 IME Escape 边界。
- [x] 复用 CopyButton、useClipboardCopy 和 ResourceCardMenu，紧凑动作保持触屏尺寸、列表文字不挤压。
- [x] 实际四宽度三主题、键盘和 clipboard 核对，完整门禁与只读复核后提交；保留全界面后续范围。

本批完成：会话/项目分享列表删除重复复制状态，复用 CopyButton；会话创建已成功但自动复制失败时只报告复制失败并刷新实际列表，保留真正创建失败的外层错误分支。手机 metadata 与右侧动作分行，保留 p-3 正文空间和 gap-1 紧凑动作；编辑/删除复用 ToolbarIconButton，手机44px、桌面32px。WorkspacePanel 路径菜单复用 ResourceCardMenu，删除独立键盘/外部点击实现，键盘 More 用按钮几何定位，右键保留指针定位；独立 copyPath 保留关菜单期间的复制请求，同路径重开等待状态，切换路径/工作区则忽略旧结果，关闭返回真正触发菜单的按钮。

TDD：分享和路径5项先明确 RED；初次 green 的分享 pending 偶发失败后，额外用父 layout effect 在子按钮挂载时激活复制，稳定复现 passive reset 清除 pending 的共享生命周期问题，明确 RED 后把 useClipboardCopy 初始化改 useLayoutEffect。初次偶发失败不当作已证明唯一原因；受控回归独立证明这个共享时序漏洞。实屏与只读复核发现新增 IconButton sm 仍32px，手机尺寸契约2项明确 RED 后改已有 ToolbarIconButton，再26项目标测试全绿。完整测试新增6项，无新依赖/新组件体系/预算提高。

原生：旧 tab9 的 goto CDP focus 超时，按文档复用同一浏览器建 tab10 继续，未操作用户原页；新只读现有分享 fixture 需重启确认运行中的 preview session35138，当前 session86494/3002。现有分享是演示链接，所有写入仍405，未创建、删除或扩大真实访问。390 dark 会话分享首复制失败后 Enter 重试真实 clipboard 精确为 http://127.0.0.1:3002/shared/preview-report；Escape 返回“Поделиться сессией”。HMR 关闭分享窗口一次，按新 DOM 重开后复制/编辑/删除实测均43.9967px。320 light 路径首复制失败，关闭返回对应长文件名 More，Enter 重开后重试 clipboard 精确为交付计划与下一阶段验证清单.md，菜单项44px；Escape 返回同一 More；无页面横向溢出。IME Escape 由目标组件测试保护，未声称真机输入法验证。

768 sepia 项目分享真实链接复制成功，稳定布局无横向 dialog 溢出，桌面操作32px；1440 light 会话分享列表动作32px、文字完整、无 dialog 溢出。项目分享从桌面临时 resize 手机后，立即几何读数曾14px且 overflow=true；下一次稳定 DOM 读数320px dialog client/scroll均320、copy/delete均44px，不把 resize 中间帧当稳定最终结果或声称瞬时布局全部通过。320 light 项目现有链接也实际复制成功，footer 长俄文按钮自然分行。已确认 clipboard 仍是本批演示链接后恢复测试前内容，viewport reset，tab10 handoff；旧 tab9 未声称已关闭。

八项自检：保留 serif 标题与正文/metadata层级；只调整动作和小屏分行，不统一压缩正文留白；链接说明、访问选择和动作主次明确；沿用已有 light/dark/sepia 色彩与五语文案；无新增装饰动画，沿用共享 reduced-motion；真实复制失败/重试、焦点返回和键盘可达；320/390/768/1440稳定结果无本批溢出、手机44px与桌面32px；保留 LambChat 视觉语言。Impeccable 沿用已确认不可用环境的 DESIGN.md 人工清单。sepia 分享主体仍沿用既有白色 modal，主题覆盖留待后续整体复查，不以局部暖色截图称所有色彩已最优。

最终门禁：pnpm test 747文件/3624项全通过；pnpm run lint 零错误零警告；pnpm run build 含 tsc/Vite/PWA/预算通过，eager JS 558775/559104 bytes，precache 5016271/5242880 bytes、91 entries，保留既有 chunk-size 提示。最终改按钮后完整三门重跑通过；只读复核关闭手机尺寸 P2，无新增 P1/P2，复核者未重复原生或全量门禁。git diff --check 通过。

截图沿用 interface-quality 目录：share-copy-390-dark-final.png、workspace-path-320-light.png、project-share-320-light-final.png、project-share-768-sepia.png、share-1440-light.png；早期 share-copy-390-dark-failed.png / share-copy-390-dark.png 在 ToolbarIconButton 修正前，不作为最终三个手机动作尺寸证明。

继续：实际聊天产物文件树仍有嵌套 span 下载/复制、乐观复制反馈，需要沿真实 caller 逐项修；图片/下载/格式、大图/内嵌图片、资源导入发布、其余语言、真机触屏/软键盘、认证/写入/真实对话、扫码 E2E 等保持待完成。整体目标进行中，不由本批分享、路径和演示数据推断全部界面无明显可提升之处。

### 当前执行：聊天成果与项目文件树

- [x] RED：文件预览与辅助操作独立可达、复制等待真实结果并可重试、ZIP 等待/失败/重试、相对路径保持原内容。
- [x] 复用 CopyButton、ToolbarIconButton、Button 与 Tooltip，手机操作44px、紧凑 gap-1，文件名保留两行空间；鼠标悬停/键盘聚焦显示辅助操作，触屏直接显示。
- [x] 修复目录面板快照双入口互相抵消、特殊文件名继承对象属性崩溃、中文文件字符数误标为字节数；实际下载内容、四宽度三主题、完整门禁与只读复核。

本批完成：RevealArtifactsSummary 和 FileTreeView 的文件行拆为独立预览按钮与下载/复制兄弟按钮，删除 span role=button 与乐观复制状态；沿用现有反馈与五语文案，ZIP 等待禁用且失败反馈可重试，严格下载不生成漏文件的包。保留正文密度、36px文件图标及文件名两行/Tooltip；不新增组件体系或依赖。目录两个展开入口使用同一目标状态，让 snapshot 批量恢复幂等。文件叶子保留原始路径，二进制与共享 FileTypeInfo 查表改 Object.hasOwn，修复 constructor/__proto__ 文件名问题；文本大小使用 UTF-8 字节数，与下载编码一致。

TDD：先完成8项失败行为，随后受控证明两个目录恢复测试 RED；已有文件类型查表的 constructor 名称导致 undefined icon，新增3项纯函数 RED 后修共享根因，再验证文件树不误判为二进制。实屏发现中文文件25字符误报25 B，中文+emoji 用例明确4 B→10 B RED/GREEN。新文件12项行为、共享类型3项回归，均通过。首轮全量被禁止 native title 的源码守卫拦截，改用现有 Tooltip 后重新通过，未放宽守卫。

实际预览新增 artifacts=1 只读成果与内联文件项目，写入仍405、不执行项目代码。390 dark 基线看到复制/下载 span 为32px且 opacity0，改后文件动作约44px直接可见；320 light 使用 Enter 复制失败后 Space 重试，真实剪贴板精确匹配完整中文 Markdown。390 dark 实际单文件下载731 bytes、内容含 Markdown、Mermaid 和代码。ZIP 的浏览器 download 事件等待超时，但 UI 已完成，随后核对实际生成的磁盘文件证明已下载；未由事件超时推断任务仍在执行。第一版 CSV fixture URL 错误导致ZIP包含HTML，修正 fixture URL和真实731/421 bytes元数据后重新下载，最终ZIP含两个正确文件；项目ZIP含67/51 bytes完整文本。仅已验证版本保存至截图目录的 artifact-files-verified.zip、project-files-verified.zip、artifact-report-verified.md，测试下载已清理。

320 light、390 dark、768 sepia、1440 light 页面横向溢出均0；手机辅助操作44px，桌面32px，768/1440 Tab 到复制按钮 focus-visible=true 且动作显现。最后将隐藏条件限定为≥640px且 hover/fine pointer，Tailwind 实际编译确认条件有效；未模拟或宣称真实 coarse pointer/真机软键盘已验证。320截图在复制成功Toast可见时；最终390项目截图在UTF-8修复及正确ParsedProjectRevealData fixture后。目录状态恢复由组件测试证明，未把简单浏览器展开当跨面板恢复证据。

八项自检：保留 serif 层级与清晰文件名/metadata；不统一压缩正文/卡片留白；预览与辅助操作职责和焦点清晰；沿用 light/dark/sepia token；无新增装饰动效、沿用 reduced-motion；复制等待/失败/重试、真实下载及键盘可达；四宽度无本批页面溢出、触屏条件和移动44px；保持 LambChat 视觉语言与现有文件类型图标。Impeccable 仍按已确认不可用环境的 DESIGN.md 清单人工检查。

最终生产修改后门禁：pnpm test 748文件/3639项通过；pnpm run lint 零错误零警告；pnpm run build 含 tsc/Vite/PWA/预算通过，eager JS 558782/559104 bytes、precache 5016819/5242880 bytes、91 entries，未提高预算，保留既有 chunk-size 提示。最后 fixture 数据格式修正不改变生产代码。独立只读复核先发现并关闭快照 P2，最后UTF-8与触屏媒体条件检查无新增P1/P2；复核者未重复原生或全量门禁。git diff --check通过。

截图：artifact-tree-390-dark-final.png、project-files-390-dark-final.png、project-files-320-light-final.png、artifact-tree-768-sepia-final.png、artifact-tree-1440-light-final.png；artifact-tree-390-dark-before.png和artifact-copy-390-dark-failed.png记录原布局与复制失败。320/768截图在最后触屏媒体条件微调前，fine pointer视觉行为不变；最终390已核对最新生产代码。继续图片/下载其他格式、大图/内嵌图片、资源导入发布、其余语言与真机/认证/写入/真实对话/扫码E2E，整体目标保持进行中。

### 当前执行：图片预览、错误恢复与全屏隔离

- [x] 原生图片入口支持键盘；失败提示、同 URL 重试与切换恢复，消失控件不会把焦点丢到 body。
- [x] 图片链接只保留链接操作，避免链接里嵌按钮；普通图片、图片组和二进制文件预览沿用共享入口。
- [x] 四宽度三主题核对、真实图片下载、桌面右面板打开时完整全屏与原生焦点恢复；完整门禁及只读复核。

本批完成：ImageWithSkeleton 的可操作入口采用原生 button，无操作时仍为 div；MessageImageGallery 图片入口和 BinaryFilePreview 复用此语义。图片组手机展开入口至少44px且有键盘焦点环，正文/卡片留白不统一压缩。Markdown 图片链接通过现有 React children 处理保留单一链接，包括嵌在 strong 中的图片和文件链接；普通图片继续打开灯箱。ImageViewer 失败时隐藏坏图、展示既有 files 羊场景与五语错误、禁用下载并收起无效变换控件，Retry remount 同 URL，未修改签名链接。消失的 Next/Retry 控件焦点回到当前顶层预览；layout effect 捕获真实 opener，关闭沿用已有防抢焦点恢复。

TDD：加载失败、重试、错误切换、两种共享图片入口、图片组和二进制预览均先 RED；消失 Next 的焦点断言独立 RED。只读复核发现图片链接嵌套控件 P2，外链/文件链接两项真实 Markdown 渲染 RED 后修，裸图片回归通过。首次全量仅旧 fileLibrary 源码守卫不接受 multiline load/error handler，更新到保留 loading 并追加 error 的实际契约后通过。桌面实屏发现 data-yields-sidebar 将灯箱压成半屏，no-yield 断言明确 RED 后删除标记；AX 继续发现右面板 portal 留在背景树，隔离/还原用例 RED 后仅在 ImageViewer 内记录并还原 body 直属 right-panel inert，先捕获 opener 再隔离。关闭同步解除 inert，microtask 返回入口；没有扩大通用 modal 的侧栏策略。

实屏：images=1 使用两个现有 WebP 与明确404的坏图，所有 API 写入405。390 dark 基线坏图仅显示破图且变换/下载仍启用；改后失败提示和 Retry 可达，Space 重试固定404仍诚实失败，Next 切换成功，焦点为新的 dialog。390实际图片125%及90°旋转；坏图在图片组不再高度0。实际下载 mobile-view.webp 为18678 bytes，RIFF/WEBP 且与仓库源文件逐字节相同，保存 image-download-verified.webp 后清理本批测试下载。关闭回原图片按钮，focus-visible=true。320 light toolbar left15/right305、查看器控件44px、Tab从最后控件回首控件；320 sepia 最终展开入口约44px且焦点环可见。768 sepia 125%变换、toolbar left253/right515，键盘焦点可见。四宽度页面横向溢出均0；1440 light 最后右面板 docked 时灯箱 left0/right1440，右侧命中灯箱，背景 AX 不再包含面板。实际从文件面板图片 Enter 打开、Escape 关闭，inert true→false 且 focus 回面板原图片入口。桌面 topbar40px、变换控件32px、切换44px，不混称统一32px。

八项自检：保持现有字体与正文层级；阅读留白不整体压缩；错误/主操作/变换层级明确；沿用 light/dark/sepia 与五语；图片与灯箱 transition 纳入既有 reduced-motion，未声称原生 OS 该模式已测试；Enter/Space/Tab/Escape、焦点恢复、链接单操作、失败与下载实际验证；320/390/768/1440无本批页面溢出，真实触摸/软键盘未验证；沿用 LambChat 羊场景与视觉语言，无新依赖/品牌体系。Impeccable 继续按已确认不可用环境的 DESIGN.md 人工清单核对。

最终修改后：pnpm test 751文件/3649项通过（本批新增10项），pnpm run lint 零错误零警告，pnpm run build 含 tsc/Vite/PWA/预算通过；eager JS 558811/559104 bytes，precache 5019539/5242880 bytes、91 entries，未提高预算，保留既有 chunk-size 提示。最后只读复核关闭图片链接 P2，后续 fullscreen/inert 两轮无新增 P1/P2；复核者未重复原生或全量门禁。git diff --check通过。最后格式化用此前已安装缓存中的 Prettier；dlx 网络 ECONNRESET 后停止该确认运行的安装会话，未新增依赖。

截图沿用 interface-quality 目录：image-viewer-390-dark-before.png；image-viewer-320-light-final.png、image-gallery-320-sepia-final.png、image-viewer-390-dark-error-final.png / final.png、image-viewer-768-sepia-final.png、image-viewer-1440-light-final.png。1440 半屏旧截图已改名 before-fullscreen，最终1440在最后 inert 修正后重新保存；320/390/768在最后仅影响已开右面板隔离的修改前，不作为该隔离证明。临时 viewport reset，tab10 handoff；用户原tab和剪贴板未操作。

继续：其他下载格式、大图/内嵌图片、绘图与视频全屏的侧栏关系、资源导入发布、其余语言、真实触屏/软键盘、认证/写入/真实对话与扫码 E2E。整体目标保持进行中，不以本批图片样例推断全部界面已无明显提升空间。

### 当前执行：视频原生控件与绘图全屏

- [x] 视频入口与播放控件分离；图片/绘图入口采用原生按钮，视频失败说明与同 URL 重试，下载保持可用。
- [x] 绘图和 Markdown Mermaid 全屏完整覆盖桌面右面板，复用独立面板锁计数，关闭恢复原入口与原始 inert 状态。
- [x] 实际播放、暂停、原生控件键盘顺序、下载内容和四宽度三主题检查；旧 WebView 回退、完整门禁与只读复核。

本批完成：FileRevealItem 原内联视频外层不再响应点击打开第二播放器，沿用 ViewerTopBarButton 提供独立右上角预览入口，手机44px、桌面40px，文件 footer 使用原生按钮；图像和绘图 preview 不再是不可键盘操作的 div。打开视频预览或手动侧栏前暂停原内联视频，避免两个播放器同时播放。VideoViewer 复用顶栏、files 羊场景及五语错误，失败隐藏无效播放器，Retry remount 同签名 URL；下载仍能供不支持该格式的用户在其他播放器打开。无新组件体系、生产资产或依赖。

视频采用原生 dialog.showModal 管理背景隔离和浏览器播放器内部焦点；仅在不支持 API 的 WebView 使用现有 useDialogFocus 与背景/右面板锁。旧模式 nativeMediaControls 选项让媒体 Tab 不被错误截断，focusin 越出顶层 surface 后按前后方向收回，其他调用者保留原行为。Excalidraw 和实际 Markdown Mermaid 删除 yield-sidebar 标记，useBodyScrollLock 的第三参数独立计数右面板锁；ImageViewer 删除重复的局部 panel effect 并复用同一锁。独立计数保持已经存在的普通 modal root lock，不放大通用 modal 的侧栏策略。

TDD：视频 dialog/error、嵌套 fullscreen 面板计数、两种绘图 no-yield 共5项先 RED；内联视频不打开第二播放器与独立图片键盘入口2项 RED 后 GREEN。原生实测发现 JS Tab trap 跳过播放器内部控件，DIALOG 断言明确 RED 后改原生弹窗。只读复核发现 iOS最低版本14、showModal API兼容 P2，删除API的用例明确 TypeError RED 后补能力检测和回退，覆盖开启、媒体Tab放行、正反向焦点回收、IME/Escape和关闭还原。最后 pause 断言明确0调用 RED 后修实际 opener。最终共新增6项行为测试，既有 drawing/Mermaid 测试增添 no-yield 断言，不降低既有守卫。

原生浏览器：videos=1 固定404与可选本机媒体，preview session27314/3002，API写入仍405。本机样例来自 MDN flower.webm（仅 /tmp，不提交仓库）；960×540、duration5.059、readyState4。390 inline Space 实际 paused=false 且 time前进，未打开第二播放器；点击独立入口后 inline paused=true/time0.205、预览 paused=true/time0。预览 Space 播放/暂停均实际改变 paused/currentTime；播放中 Escape 移除预览，剩余内联/侧栏播放器均暂停，焦点回原预览按钮。下载 preview-video.webm 为554058 bytes，SHA256 与本机源精确一致，已保存 video-download-verified.webm 后清理本批下载。

原生键盘逐项经过播放、音量、静音、播放器全屏、更多、时间进度；末端有一次浏览器/body焦点过渡，再回 Close/Download，没有进入背景应用。原生播放器全屏按钮 Space 在 IAB 未实际进入 document.fullscreenElement，因此只证明入口可达，不声称 OS 视频全屏或退出层次已验证；旧 iOS回退内部Tab顺序仍需真机。320 light 错误文案完整换行、Retry Space 对固定404仍诚实失败，关闭/下载/Retry均约44px；390 dark 播放预览，768 sepia 稳定播放/暂停后截图，1440 light 预览顶栏40px。四宽度本批页面横向溢出均0。浏览器 viewport 请求尺寸按当前浏览器缩放换算成CSS320/390/768/1440，截图边缘包含浏览器表面，不由截图像素直接推断CSS尺寸。

1440 light 先打开实际 docked Markdown右面板再开 Excalidraw，绘图 dialog left0/right1440（修前仅749px），背景右面板 inert属性存在且 AX 消失；Escape清除锁、返回文件库原绘图按钮。Markdown实际 Mermaid full dialog 同样0–1440，关闭背景panel inert恢复false，focus回面板里的原Fullscreen按钮。样例只有三节点，不作为大图可读性或触摸缩放证明。

八项自检：沿用既有文字与文件名层级；保持正文/卡片阅读留白，仅收紧动作；播放控件与预览入口分离、失败恢复明确；媒体沿用黑色观看表面，周边 light/dark/sepia 不另建色彩体系；VideoViewer transition 纳入已有 reduced-motion，无装饰动效，OS偏好未实测；原生播放、键盘路径、焦点回退、失败与真实下载验证；四宽度、手机44px与桌面40px且无本批横向溢出，触屏/软键盘未验证；沿用 LambChat 场景与现有视觉语言。Impeccable 继续按已确认不可用环境的 DESIGN.md 清单人工检查。

截图：video-320-light-error-final.png、video-390-dark-final.png、video-768-sepia-final.png、video-1440-light-final.png、drawing-fullscreen-1440-light-final.png、mermaid-fullscreen-1440-light-final.png；drawing-fullscreen-1440-dark-before.png 仅基线。320 error 与桌面 drawing/Mermaid 的最后视频 pause 修改不影响其布局；390在该修改后重拍。原生 Top Layer 最新 diff 和旧 WebView回退已独立只读复核，兼容 P2关闭；最终媒体 pause 行单独复核。复核者未重复全量门禁或原生交互。

继续：其他格式下载、大图与内嵌图片、资源导入发布、其余语言、旧 iOS/真实触屏/软键盘、原生视频全屏、认证/写入/真实对话与扫码E2E。整体目标保持进行中，不以本批演示数据和媒体路径称全界面已无明显提升空间。

最终修改后门禁：pnpm test 754文件/3655项全通过；pnpm run lint 零错误零警告；pnpm run build 含 tsc/Vite/PWA/预算通过，eager JS559004/559104 bytes、precache5022614/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。最终pause行只读复核无新增P1/P2，git diff --check通过。构建首次动态div/dialog ref类型失败已修为明确类型callback后重跑通过。截图与验证资产在仓库外；临时viewport reset，tab10 handoff，用户原tab及剪贴板未操作。

### 当前执行：技能导入与发布表单

- [x] GitHub 与 ZIP 复用共享表单和按钮，字段有标签，手机安装按钮显示数量，长名称与说明换行，候选使用原生 label/Checkbox，移除列表内部第二滚动条。
- [x] 发布移除重复装饰卡片，保留原生 form 提交，正文独立滚动，手机操作44px，标签复用单行+N，真实 isPublishing 接入编辑/关闭/取消/重复提交边界。
- [x] 错误留在表单可重试；旧预览不能污染新仓库/分支/关闭表单，部分成功只重试剩余候选，pending ZIP 禁止换文件。

GitHub 删除197行未使用的渐变/自定义控件CSS，复用 Input/FormField/Button/ConfigPanelErrorCallout；分支标签同步五语。原GitHub“导出”实际先安装选中项后只导出第一项，移除此误导入口，已安装技能菜单的ZIP导出保留，未新增远程导出API。ZIP chooser改原生按钮，文件计数复用 project.fileCount。发布沿用 ModalSurface 与主题/字体，滚动body与固定footer；原生测到 min-h 类被primitive覆盖，改important类，手机三按钮均44px。提交前focus共享modal surface，失败后ShiftTab由既有trap接管，避免聚焦内部form后越界。

TDD：交互4项与恢复5项先RED后GREEN；复核三项P2（Retry焦点卸载、部分GitHub成功重新全选重复提交、上传中drop新ZIP使busy永久保留）对应4失败先RED再修复。发布禁用后焦点与失败恢复反向Tab另1项RED，最终共11项新增行为测试。动态disabled选择器在jsdom的末项与浏览器不同，测试断言按键被拦截且焦点回弹窗内控件；真实IAB1440提交405失败后ShiftTab实际回末尾发布按钮。最后只读复核无新增P1/P2，复核者未重复原生或全量门禁。

原生IAB：390×844深色GitHub首次503后Retry得到24长名称候选，focus稳定panel root，Space仅选一次；滚动后安装按钮仍可用且44px。320×568浅色ZIP原生filechooser选择本批/tmp生成样例，首次503后Retry保留同文件并恢复24候选，8已安装禁选、16新项自动选中，页面无横向溢出；俄语长按钮短屏换为两行footer，每按钮44px且未挤出。320浅色发布长标签+2、405失败与正文滚动验证；390深色8秒延迟发布，busy=true、close/cancel/submit disabled且44px，Escape不关闭，失败恢复编辑。768档请求实际CSS769×905暖色发布，1440×900浅色GitHub停靠489.6px，页面横向溢出均0。已安装菜单仍有ZIP导出。

imports=1仅为两个只读POST返回预设数据，消费并丢弃上传body，不存储、不连接GitHub或真实API；安装/发布仍405。不声称真实ZIP解析、GitHub抓取、安装或公开发布成功。服务器重启时旧agent tab10陷入连接错误页，用同浏览器新tab11恢复，未绕过安全警告，用户原tab及剪贴板未操作。

八项自检：保留正文可读性/衬线标题；收紧动作gap并移除冗余卡片，未整体压缩正文；数量、错误恢复、已安装状态分层；沿用light/dark/sepia与五语；共享transition/reduced-motion无装饰动效，OS偏好未实测；Space/chooser/Retry/提交等待/ShiftTab原生验证；320/390/769/1440无本批横向溢出，触屏/软键盘未验证；沿用LambChat视觉语言无新生产资产或依赖。Impeccable按已确认不可用环境的DESIGN.md清单人工检查。

截图在仓库外interface-quality目录：github-import-390-dark-before.png/after.png、github-import-1440-light-after.png、zip-import-320-light-after.png、skill-publish-390-dark-before.png/after.png/pending.png、skill-publish-320-light-after.png、skill-publish-768-sepia-after.png、skill-publish-1440-light-after.png。pending截图在最后focus目标改surface前，仅作busy/禁用/尺寸证据；最后桌面ShiftTab在修正后。

继续：真实导入/发布、其余语言、触屏/软键盘、旧iOS/原生媒体全屏、认证/写入/真实对话和其他下载格式。整体目标保持进行中，不以本批fixture推断全界面已无明显提升空间。

最终门禁：pnpm test 756文件/3666项全通过；pnpm run lint零错误零警告；pnpm run build含tsc/Vite/PWA/预算通过，eager JS559085/559104 bytes、precache5017943/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。最后390深色失败恢复后ShiftTab实际回发布按钮，重拍最终手机截图；最后只读复核无新增P1/P2，git diff --check通过。临时viewport已恢复，tab11 handoff，用户原tab和剪贴板未操作。

### 当前执行：技能编辑表单与全屏文件管理

- [x] 元数据复用 FormField，名称、描述、标签、文件路径关联标签与错误；移除重复标签标题/占位提示、启用文字和名称装饰图标，保留五行描述与阅读间距。
- [x] 普通工具栏复用 ToolbarIconButton，删除重复 Pencil 入口；启用复用 ToggleSwitch，删除专属 Toggle 文件，沿用主题/字体/i18n，无新资产、依赖或文案键。
- [x] 全屏退出纳入顶部工具栏，修复上传遮挡；两处 min-w-0 防止多文件标签挤出动作，当前标签 nearest 定位。手机/coarse pointer 按钮最小44px，桌面工具栏32px。
- [x] 文件/树删除为具名独立原生按钮，桌面 hover/focus 显示、触屏始终可用；文件删除保持选中项并回可见控件，标签删除回输入框，错误定位首个可编辑字段。
- [x] 全屏复用 useDialogFocus/useBodyScrollLock，支持 IME/Escape、键盘边界、背景/右面板隔离与关闭保留内容/焦点。真实 CodeMirror 放行 Tab，不将导航写入缩进；删除遮住正文的硬编码黑色 Esc toast。

TDD：元数据关联、文件/树独立删除、全屏隔离四项明确 RED；验证定位/删除索引与焦点两处断言 RED；折叠当前目录后删末项 zzz.md 的 BODY 焦点问题、标签 Space 删除焦点问题分别新增 RED；真实 CodeMirror Tab 用例明确 false RED。修复后共两个新文件8项行为测试 GREEN。全量三条旧结构守卫写死浮动按钮/Pencil，更新为父容器安全区内 Toolbar、FormField/ToggleSwitch，保留原安全区和共享组件检查。

原生 IAB tab11、3002只读 fixture：320×568浅色空提交错误完整显示，focus回名称，滚动后固定操作可用；390×844深色标签/文件 Space 删除、开关状态、正反向 Tab、输入保留/退出焦点实测。最终 Escape 只退出全屏，右面板 inert 属性 true→false，元数据与正文保留，focus回原入口。多文件动作保持视口内，手机名义44px（实测43.9967px舍入）、动作 gap4px。768×905暖色普通/全屏重拍无黑色提示遮挡；1440×900浅色停靠489.6px，选 docs/help.md→折叠 docs→Space删zzz，focus回可见SKILL，编辑header/内容仍help，退出后保留。四档横向溢出均0；viewport按现有浏览器缩放换算成CSS实际尺寸。

复核建议查搜索关闭动作：390/320原生 Cmd+F 打开/关闭；320 previous x195.066–257.220，close x260.016–304.013，不相交，all自动换行，未复现重叠。只证明入口、尺寸、关闭；不声称查找替换内容正确性。原库搜索样式、checkbox触控与locale列入下一批共享编辑器检查。

八项自检：保留产品字体/阅读留白；去除冗余表面，操作紧凑；字段/提示/文件/提交层级清晰；沿用light/dark/sepia和既有五语，删除硬编码提示；此form动画/transition/按钮缩放尊重 reduced-motion，无新装饰动效，OS偏好未实测；键盘、焦点、删除、开关和草稿保留原生验证；四宽度无本批溢出，coarse由CSS覆盖，真实触屏/软键盘/旧iOS未验证；沿用 LambChat 组件与视觉语言。Impeccable依此前确认不可用环境，按 DESIGN.md 清单人工检查。

最终门禁：pnpm test 758文件/3674项全部通过；lint零错误零警告；build含tsc/Vite/PWA与预算通过，eager JS559067/559104 bytes，precache5016902/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。最终只读复核无确定P1/P2，git diff --check通过。Prettier registry重试期间用既有缓存完成，原dlx最终也成功。门禁后只有文档/原生检查，无生产代码变化。

截图在仓库外 interface-quality：skill-editor-390-dark-before.png、skill-editor-fullscreen-390-dark-before.png为基线；最终 skill-editor-320-light-validation.png、skill-editor-320-light-files.png、skill-editor-fullscreen-320-light-final.png、skill-editor-390-dark-final.png、skill-editor-fullscreen-390-dark-final.png、skill-editor-768-sepia-final.png、skill-editor-fullscreen-768-sepia-final.png、skill-editor-1440-light-final.png、skill-editor-fullscreen-1440-light-final.png。临时viewport恢复、tab11 handoff，用户原tab/剪贴板未操作。

继续：共享编辑器搜索和弹层、技能文件懒加载错误/竞态、二进制保存恢复、真实创建/更新/上传、其余语言/真机和未覆盖界面。本批未向真实API写入fixture内容，不作为认证、写入或真实对话E2E证明。整体目标保持进行中，不以本批截图称全部界面已无明显提升空间。

### 当前执行：共享代码查找与键盘交互

- [x] SkillEditor 与 CodeMirrorViewer 共用已有 CodeMirror 原生搜索、顶部入口及主题样式；复制动作移入工具栏，不遮正文。
- [x] 按容器宽度适配搜索/替换：窄面板按钮和标签至少44px、操作gap4px、输入16px，桌面约32px；长俄语完整换行，短屏面板可滚动。
- [x] 五语查找/替换/公告跟随应用语言，随编辑器懒加载；只读预览设置真实 readOnly，不提供替换。Tab可导航，关闭查找回正文，IME候选Enter/Escape不执行搜索或关闭外层。

沿用 ToolbarIconButton、CopyButton 与主题token，未另写搜索引擎或自定义搜索面板。@codemirror/search 6.7.0原本已由UIW安装，仅显式声明依赖；没有升级库。最初五语加入全局locale导致eager预算超限，改为编辑器懒加载资源注册后通过，未提高预算。只读正文补tabindex=0解决原生关闭查找后BODY焦点；capture仅拦截搜索区内IME候选Enter/Escape的传播，保留默认候选处理。

TDD新增9项实际CodeMirror行为测试：入口/焦点、真实全部替换、只读无替换与Tab、只读技能预览焦点、IME保护、另四语。入口、显式搜索焦点、IME默认事件分别见RED后修；组件未mock CodeMirror。已有布局守卫更新为共享根节点，Keyboard测试保留react-i18next实际初始化导出。独立只读复核最终无P1/P2；没有重复原生或全量门禁。

原生IAB：320×568深色俄语完整搜索/替换布局，390×844深色实际四处skill→guide替换、Escape仅关搜索且草稿保留；390浅色文件只读搜索summarize实际两处匹配，关闭回代码正文，Tab可达下载。正常技能侧栏预览实际683.5px高，未复现180px预览裁切，未加推测性高度补丁。768×905暖色聊天窄代码区按容器走44px样式、选项换行；滚动后面板和代码可见，页面溢出0。1440×900浅色文件预览665px宽、搜索面板84.2px高，按钮约32px，关闭回正文，页面溢出0。

聊天fixture在后续正文重新挂载时两次清空搜索并将焦点落到BODY，原因尚未确定；列为下一批状态保留检查，不把本批共享搜索测试当聊天稳定性证明。平板截图先保存时恰遇正文刷新，不能作为持久状态证据。最终可靠手机截图editor-search-viewer-390-light-final.png，窄俄语editor-search-320-dark-ru-final.png，桌面editor-search-viewer-1440-light-final.png均在仓库外interface-quality目录。临时viewport已恢复，预览语言恢复俄语，tab11 handoff，用户原tab/剪贴板未操作。

八项自检：沿用产品字体、代码等宽和16px移动输入；保留正文阅读留白、收紧动作gap；工具栏/查找/正文层级明确且复制不遮代码；light/dark/sepia主题与匹配高亮使用token；无新增装饰动效、尊重reduced-motion；查找替换、只读、Tab/Escape、焦点与IME测试；四档原生布局核对但非全宽度×主题矩阵，真实触屏/软键盘/候选窗口未验证；保持LambChat视觉语言，无新生产资产。Impeccable依此前确认不可用环境，按DESIGN.md人工清单检查。

最终生产修改后门禁：pnpm test 759文件/3683项全部通过；lint零错误零警告；build含tsc/Vite/PWA/预算通过，eager JS559066/559104 bytes，precache5016622/5242880 bytes、91 entries；保留既有chunk-size提示。git diff --check通过。继续聊天代码预览重建、技能懒加载错误/竞态、二进制保存恢复及真机/真实写入；整体目标保持进行中。

### 当前执行：聊天代码工具栏与正文交互状态

- [x] Python 与搜索、复制合并为同一工具栏，垂直居中，动作gap4px；删除重复外层header。
- [x] 聊天代码块复用原生查找，仅显示关键词、下一处、上一处和关闭。手机保持单行，按钮44px，输入随剩余空间缩放；文件编辑器保留完整搜索能力。
- [x] ReactMarkdown renderer 提到模块级，用Context读取当前流式状态、标题锚点和图片动作；正文追加和流式完成不再重建编辑器、丢失查找状态。
- [x] 表格复制读取实时DOM，稳定getter和回调身份；无关正文更新不会取消尚未完成的复制反馈。

TDD新增3项真实Markdown/CodeMirror行为测试：工具栏语言与搜索/复制同组、追加正文及流式完成保留查找节点/关键词/焦点、延迟表格复制在正文更新后仍保持pending并完成。均先明确RED后GREEN；原复制测试移除CodeMirror mock，结构守卫更新为真实共享toolbar，补jsdom缺失的Range.getClientRects几何接口。旧图片、锚点与文件行为保持。独立只读复核关闭表格pending与coarse label触控尺寸P2，最终无新增确定P1/P2；复核者未重复全量或原生检查。

原生IAB最终简化模式：320×568深色实际summarize匹配一处，AX仅有查找、下一个、上一个和关闭；输入138×44px、三动作44×44px，工具栏搜索/复制44×44px、gap4px，Python与按钮中心差0.008px，页面横向溢出0。320→430×844保留关键词与匹配，单行无溢出。1440×900浅色实际匹配一处，Escape关闭并将焦点还给代码正文，页面溢出0。原先hidden测试tab13默认1280，viewport未应用到该页，因此不将其误记为手机证明；改用独立可见tab14得到上述实际尺寸。用户tab12的输入、语言及匹配偏好未修改。

截图在仓库外interface-quality：code-search-basic-320-dark-final.png、code-search-basic-430-dark-final.png、code-search-basic-1440-light-final.png。之前full选项截图仅作中间基线，不能代表最终基本搜索。临时viewport已reset，测试tab13/14已关闭，用户tab12保留。没有真实SSE追加代码的浏览器E2E，状态保留由真实组件测试证明；真实触屏、软键盘、旧iOS及剩余宽度/主题组合未验证。

八项自检：保留等宽正文与既有字号、语言光学对齐；收紧动作和查找留白而保留阅读节奏；语言/动作/查找/正文层级清楚，去掉聊天高级选项；沿用深浅色和匹配token；无新增动效，保留reduced-motion；原生匹配与关闭焦点、复制pending和流式状态测试；实际320/430/1440无本批溢出，手机44px；沿用LambChat视觉语言与已安装原生搜索，无新依赖或资产。Impeccable按此前确认不可用环境的DESIGN.md清单人工检查。

最终生产修改后门禁：pnpm test 760文件/3686项全部通过；pnpm run lint零错误零警告；pnpm run build含tsc/Vite/PWA/预算通过，eager JS559075/559104 bytes、precache5017021/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。中途全量出现一次Mermaid fullscreen复制用例初始化颜色异常，相关用例随后通过，最终全量也全部通过；未改Mermaid，不声称修复该瞬态异常。最后门禁后仅文档与原生检查，无生产代码变化。

继续：技能懒加载错误/竞态、二进制保存恢复、未覆盖界面、真机与真实写入/对话。整体目标保持进行中，不以本批搜索截图称全部界面无明显提升空间。

### 当前执行：技能文件读取与草稿恢复

- [x] 普通与全屏文件读取失败持续显示已翻译的错误与重试，避免空白可编辑内容冒充读取成功。两视图共享 SkillFileLoadState，复用 LoadingSpinner、ConfigPanelErrorCallout 和 Button。
- [x] 请求按唯一文件路径回写；Map中的请求Symbol隔离旧技能、删除文件及后续请求，活动文件loading从Set派生。未读取成功的文件路径保持禁用。
- [x] 重试先聚焦稳定form，加载及恢复后不会落BODY；描述等元数据保留。文件路径与已有路径冲突时立即保留原路径和草稿，错误关联原生输入字段。
- [x] 删除或改名未命名草稿时，只清理没有剩余条目使用的loaded marker；连续新增两个草稿再删除一个，其余仍可命名并进入保存payload。

走查步骤与证据：①390深色进入普通编辑器，文件操作和固定底部清晰（skill-file-01-390-dark-before）；②同宽全屏文件首次503显示空白可编辑正文且无重试，确定静默失败（skill-file-02-390-dark-failure-before）；③修后390深色和320浅色明确显示路径、错误与44px重试（skill-file-03-390-dark-error-final、skill-file-04-320-light-error-final）；④320浅色Enter重试成功，focus=FORM且connected，退出后描述草稿仍在（skill-file-05-320-light-recovered-final）；⑤320浅色新增两个草稿、移除一项后成功命名new.md，同名b.md被拒绝，原路径不变、aria-invalid=true、aria-describedby指向错误（skill-file-06-320-light-path-final）；⑥1440浅色b.md首次读取失败，文件树与重试可用；768浅色Enter重试恢复，focus=FORM（skill-file-07-1440-light-error-final、skill-file-08-768-light-recovered-final）。实际上述视口无本批整页横向溢出。

TDD最终新增6项真实SkillForm/CodeMirror行为测试：失败恢复普通/全屏两项、移除其他文件后响应归属、旧技能响应隔离、同名路径即时拒绝并保留两个文件正文、未命名草稿删除后命名及两文件进入payload。前三类四测试先RED后GREEN；独立审查的Retry焦点、非空同名路径共享状态、空路径loaded marker三项P2均有明确RED再修，最终只读复核无剩余确定P1/P2。中间试用原条目对象回写使换技能初始化拿到旧条目，原测试失败后收敛为路径唯一性约束；不保留这套身份实现。

八项自检：沿用等宽路径和正文、既有字号；普通编辑阅读留白保持，错误区域有足够空间；路径/错误/恢复动作层级清楚；深浅色沿用主题与错误token，复用五语files.loadFailed/common.retry/common.loading/duplicateFilePaths，无新增文案；加载复用已有spinner及reduced-motion规则，未增装饰动画，OS偏好未实测；键盘重试焦点、字段错误关联、草稿与响应隔离实测/测试；320/390/768/1440布局覆盖，手机重试44px；保持LambChat既有语言，无新依赖或生产图片。Impeccable按此前确认不可用环境的DESIGN.md清单人工检查。

fixture在独立3017预览进程，file-flow=1提供三个文本文件，failure=skill-file每路径首次GET失败、Retry恢复；其余写请求仍405。上述新增/删除/改名仅表单本地草稿，没有保存真实技能；onSave payload通过组件测试验证。HMR更新代码期间会重载整个演示页，检查阶段重新定位，不将开发热更新作为运行时草稿保持证据。用户3002预览及其输入未操作。截图均在仓库外interface-quality目录；此阶段不证明真实并发服务、二进制上传保存、认证或真机触屏/软键盘成功。

继续：二进制预览/保存及部分失败恢复、剩余界面/语言组合、真机与真实服务写入。整体目标保持进行中；本批文件读取缺陷关闭，不据此宣告全界面完成。

最终生产修改后门禁：pnpm test 761文件/3692项全部通过；pnpm run lint零错误零警告；pnpm run build含tsc/Vite/PWA/预算通过，eager JS559076/559104 bytes、precache5017048/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。此前lint的一项effect cleanup ref警告改为捕获该次effect的requests变量后重跑全部门禁通过。git diff --check通过。最后独立只读复核无确定P1/P2，未重复门禁。仅文档/预览清理留在最后门禁之后。

### 当前执行：技能附件保存与部分失败恢复

已同步并rebase最新origin/develop。先在390深色真实表单选择仓库公开图标，记录普通/全屏基线；不连接真实技能写入。追踪发现读取过的二进制占位文字会进入文本payload，父层文本保存成功即关闭，后续附件失败静默丢失恢复入口。

计划：先用实际SkillForm与useSkillsActions的集成测试复现；文本成功与整个保存完成分离，全部附件完成后关闭；部分失败保留草稿，仅重试未完成附件，新建成功后的重试按更新处理。二进制路径暂保持只读（后端没有移动接口），同名选择拒绝覆盖；复用已有错误提示与手机工具栏按钮。最后运行全量测试、lint、build、独立复核及宽窄/深浅色预览，明确真实写入与真机的证据边界。

已完成：所有已知binary路径排除文本payload；onComplete只在全部上传完成后关闭，逐项移除成功上传的pending条目，失败路径与Retry保留在sticky操作栏。提交先focus稳定form，fieldset禁用期间维持焦点，CM正文只读。新建的文本保存完成后锁定名称；重试按更新并读取真实清单，避免删除从未上传成功的文件。form submission与父层session同时隔离关闭/切换期间的迟到响应；切换Edit立即卸载旧form。二进制路径只读，同名附件整批拒绝覆盖；blob URL删除、换技能及卸载均清理。下载复用ToolbarIconButton，桌面32px/手机44px。

补齐全部调用后发现商店直接创建/更新接口仅接受文本，原通用上传会写入错误的用户技能命名空间。商店普通/全屏不再提供此入口，入口函数也受能力约束；商店编辑读取完整商店文件，保留原始binary引用与metadata，保存按当前filePaths合并未改文件，不混入本地副本或删除附件。没有扩张后端权限、增加上传接口或发布能力。两个商店集成测试先RED再GREEN。

TDD本批新增8项：1项payload回归、5项实际SkillForm/useSkillsActions集成、2项商店父层/实际表单集成。关键RED包括loaded binary混入文本、父层提前关闭、允许binary改名、部分失败删除不存在项、关闭后的旧文本请求锁定新草稿、旧upload抢占新Edit、商店误读本地副本及不支持的上传入口；新增的等待焦点与立即卸载断言也先RED再修。独立只读复核的两项焦点/归属P2已关闭，最终增量无确定P1/P2；复核未重复门禁或浏览器操作。

原生IAB步骤：390深色选公开图标记录普通/全屏基线（skill-binary-01/02）；独立3017的320深色读取已有图片，选另一个公开图标，提交模拟保存。等待时focus=FORM/aria-busy=true，首次上传503后草稿保持、Retry可用并获焦点。错误移入sticky footer后实际y457.6/h46.4，Retry高44px、整页overflow0（skill-binary-03/04）；Enter重试，等待焦点再次FORM，模拟200后编辑器关闭（skill-binary-05）。1440浅色full preview与文件树、390浅色同一图片预览均overflow0；download分别32×32和44×44（skill-binary-06/07）。截图在仓库外interface-quality目录。HMR期间焦点重置不作为产品行为证明。

八项自检：沿用路径等宽/正文与元数据字号；保持预览阅读空间、收紧统一工具栏；状态、失败路径和恢复动作层级明确且底部始终可见；主题/错误token、现有五语common.saveFailed/skills.uploadFailed/common.retry，未加单语文案；未加动效，既有组件reduced-motion规则保留但OS偏好未实测；键盘等待/错误/重试焦点与并发归属有实测/测试；320/390/1440和深浅色覆盖，44px触控；使用LambChat已有组件与公开资产，无新依赖或另设视觉体系。Impeccable继续按此前不可用环境的DESIGN.md清单人工检查。

证据边界：save-flow=1仅消费/丢弃字节并返回模拟200/503，没有持久化或真实权限/发布；其它写请求仍405。真实部分成功清单与重试只覆盖外部API模拟的集成测试。技能商店补只读详情/文件/图片fixture，真实存储、设备软键盘/触屏、媒体格式、剩余宽度/语言/主题组合待验。整体目标仍进行中，不据此宣告全部界面无可提升之处。

补充原生商店走查：390浅色直接读取商店全文件并打开图片，普通/全屏均无错误的上传入口；全屏已有图片可预览、download44px、overflow0（skill-binary-08-390-light-marketplace-final）。预览先遇到缺少商店详情GET的fixture404，补齐纯读取样例后重新实测；未将此fixture缺失记为生产读取故障。商店保存没有模拟成功或真实发布。

最终生产修改后的门禁：pnpm test 765文件/3705项通过；pnpm run lint零错误零警告；pnpm run build含tsc/Vite/PWA/预算通过，eager JS559136/561152 bytes，precache5017360/5242880 bytes，91 entries，保留既有chunk-size提示。本批未修改预算；origin/develop rebase后既有预算上限为561152。全量中一次与本批无关的SearchDialog legacy IME断言失败，相关文件单独重跑及最终全量均通过；未改该实现、不声称修复此瞬态异常。diff --check通过，最后只读复核无确定P1/P2。最后门禁后仅文档与临时预览清理。

### 当前执行：技能媒体预览失败恢复

开工 fetch origin 完成，当前 HEAD 已包含最新 origin/develop。先以公开资产构造无法解码的本机临时图片、视频和音频，在真实 SkillForm 普通/全屏入口复现：失败图片仅显示文件名，视频剩不可用原生播放器，没有重试。所有文件仅进入临时表单草稿，未提交、上传或保存真实技能。

BinaryFilePreview 的图片、视频、音频失败统一复用 SkillFileLoadState，使用已有五语错误和 Retry；同 URL 重试重新创建媒体元素，换文件清理失败、图片加载和查看器状态。重试前聚焦稳定内容容器，媒体失败时保留已有区域内的焦点；焦点环使用主题 token。图片直接复用 ImageWithSkeleton 的加载状态，删除第二套 spinner；视频使用原生加载/播放控件，支持 playsInline，去掉渐变、阴影和自定义透明度等待。长 MIME 元数据截断。通用下载复用 Button，type=button 避免提交父表单。

四项新增行为测试先 RED 后 GREEN：图片、视频、音频失败提示、同 URL 重试元素替换/焦点、切换另一文件及返回的状态清理（三项参数化测试）；通用下载确实触发下载而不提交技能表单。独立复核发现商店独立 ModalSurface 不受技能表单的触控兜底保护，min-h-11 会被共享 md 样式覆盖；下载与 SkillFileLoadState Retry 改为共享 size=lg，直接保证44px。最终只读增量复核无确定 P1/P2。

原生 IAB 使用独立3017：390深色记录普通与全屏视频失败基线（skill-media-01/02）；320×568深色图片、视频、音频错误均明确显示 Retry（03/04/05），下载44×44px，最终Retry高44px、宽68.6px，整页横向溢出0。Enter 重试后 focus=DIV 且 connected，无法解码的样例仍显示失败，未伪称重试成功。切换已有公开图标可正常预览/打开 ImageViewer，关闭归还图片按钮焦点。已有本机 MDN flower.webm 样例 readyState4/duration5.059，320下 Space 实际 paused=false/time前进，原生播放控件可用（06）。1440×900浅色通用下载 type=button、高44px、overflow0（07）；390×844浅色 Enter Retry 后同样保留稳定焦点、高44px、overflow0（08）。截图在仓库外 interface-quality，04/07/08 为最终尺寸修复后的证据；03/05 是中间尺寸版本。viewport已reset，临时tab/预览进程清理，用户3002页面和输入保持。

八项自检：保留既有文件标题/等宽路径/元数据字号；图片只保留单套加载层、媒体维持阅读空间；标题、格式、内容及错误恢复层级明确；沿用深浅主题与既有错误色；删除自定义视频动效，无新增动画，既有 skeleton reduced-motion 规则保留；原生播放键盘、图片关闭焦点、Retry稳定焦点和表单下载语义有实测/测试；320/390/1440实际布局和44px按钮覆盖；复用既有插画、primitive及浏览器媒体控件，无新依赖或视觉体系。Impeccable按此前不可用环境的 DESIGN.md 清单人工检查。

最后生产调整后门禁：pnpm test 765文件/3709项通过；lint零错误零警告；build含tsc/Vite/PWA/预算通过，eager JS559147/561152 bytes、precache5017396/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。diff --check通过。真实存储写入、所有媒体格式、音频成功播放、移动系统全屏与真机软键盘/触屏仍待验；这批不扩大既有搜索功能，也不据此宣告全部界面完成。

### 当前执行：商店详情与文件预览

fetch/rebase 最新 origin/develop（6f10c1af）后继续。390深色只读 fixture 首次文件 GET 503，真实 SkillPreviewModal 显示空白编辑器，关闭仅28×28px，独立 modal 没有可读名称（marketplace-preview-01）。文件清单失败也被当作无文件；hook 的单一 loading path 和无请求归属会让迟到响应污染其它技能或清除其它文件加载状态。

useMarketplace 为每次详情使用独立 session 对象，关闭、重开、换技能和卸载均失效旧请求；每文件 Map 请求与 Set loading 防重复读取并保持并发状态。清单/文件失败显示已有五语错误，Retry 可恢复；空文本以 undefined 区分已加载与未加载，不反复请求。SkillPreviewModal 复用 SkillFileLoadState、Button 和 ToolbarIconButton，预览以完整路径命名，手机关闭44px、桌面32px。列表和文件重试先 focus 稳定容器；父层按技能名 key 重置当前文件。删除不再使用的外部缓存 setter prop/导出，避免绕过请求归属。

追踪渲染发现 EditorSidebar 不使用 subtitle，原版本与说明实际未显示。将既有元数据移至正文，版本12px、说明13px；短说明完整显示，长说明可展开/收起并有 aria-expanded。独立复核指出79个中文字符在320px也可能超过三行却无展开入口，改为同一 hasLongDescription 同时控制三行限制与展开入口，不再截断无恢复入口的短说明。未新设颜色/字体/间距体系或新增文案。

6项实际 hook+modal 集成测试均看到关键 RED 再 GREEN：清单失败重试；文件失败重试与空文本缓存；旧技能清单迟到隔离；一个文件完成不清除另一 pending；关闭后旧文件不污染新技能；版本与说明可见。外部 API 模拟，真实 EditorSidebar/ModalSurface/CodeMirror 保留。原有 source 测试和商店编辑保存回归同时通过。最后只读复核关闭说明截断 P2，无本批剩余确定 P1/P2；不将源码审查当作真机证明。

原生 IAB 独立3017：390深色首次读取失败明确错误、Retry/close均44px、dialog名SKILL.md、overflow0（02）；Enter Retry 正文恢复，focus=DIV/connected，Escape关闭回SKILL.md文件按钮（03）。320×568浅色清单失败与44pxRetry（04），Retry后列表恢复且焦点在稳定正文；独立二进制modal加载公开图标，关闭/下载均44px，路径名称正确。320浅色最终详情显示版本、完整短说明、标签、文件列表（05）。1440×900浅色侧栏与独立文件预览同时可读，close32px、dialog名SKILL.md、overflow0（06）。截图在仓库外 interface-quality；02/03/04早于元数据补回，预览恢复/尺寸逻辑未改变，05/06是元数据最终布局。HMR重载不当作运行时状态保持证据。

八项自检：既有标题/等宽路径/版本与正文尺度；详情恢复必要说明留白，预览动作保留紧凑比例；元数据→标签→文件→读取状态层级清楚；深浅色和错误/焦点主题token；无新增动效，既有加载组件保留 reduced-motion；原生关闭/Retry焦点、可读名称、aria-expanded和并发归属；320/390/1440实测无本批横向溢出、手机44px；复用产品既有组件与插画，无新依赖或生产资产。Impeccable按此前不可用环境的 DESIGN.md 清单人工检查。

fixture 新增仅 GET 的 marketplace-files/marketplace-file 首次503并Retry恢复，其它写仍405；未安装、发布或写真实技能。最终修改后门禁：766文件/3715测试通过；lint零错误零警告；build含tsc/Vite/PWA/预算通过，eager JS559137/561152 bytes、precache5017396/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。diff --check通过，最后门禁后仅文档/原生走查/预览清理。

继续检查其它侧栏元数据调用、剩余界面/语言组合、真机和真实服务边界。整体目标保持进行中；本批不声称全界面或真实安装/发布端到端完成。

## 2026-10-02 记忆详情与编辑器完整内容恢复

- [x] 详情与编辑器共用同一全文读取状态：列表的 `has_full_content` 表示内容另存，GET失败不再显示片段或恢复保存；持续错误可重试，loading有status文字。
- [x] 重试聚焦稳定内容容器，完整内容与摘要读取成功后才能编辑；用户修改的标题、类型、来源与标签保留。切换卡片按memory_id重建草稿，旧读取取消，旧保存不能关闭新编辑器。
- [x] 保存期间冻结字段，使用共享Button loading；失败在固定footer保留错误和Retry，不重复toast，不丢草稿。
- [x] 详情类型、来源、时间、访问与标签集中为元信息组，删除额外margin与正文卡片边框；长元信息、标签和正文支持换行。编辑更新时间移到正文，保留单个tab标题，不恢复被忽略的subtitle重复header。

开工fetch/rebase确认origin/develop35af6aff，当前隔离分支基线8bb24f26；未动主checkout未提交内容。沿用Loading、ConfigPanelErrorCallout、Button、主题token与五语已有键，无新依赖、生产资产或翻译键。仅增加两处实际全文调用共享的本地hook，不另建读取/搜索引擎。

六项真实组件行为均见RED→GREEN：全文失败不伪成功并Retry；编辑器失败不可保存、Retry保留标题并提交全文；详情切换隔离；卡片编辑切换隔离；pending保存冻结草稿且迟到成功不关闭新编辑器；失败保存持续提示并重试同一payload。保留真实EditorSidebar/表单，API调用模拟。记忆目标5文件12项通过，独立两次只读复核未发现确定P1/P2。

原生IAB独立3017：390深色GET首次503后明确错误，Retry44px，页面overflow0；Retry实际200恢复完整正文及长URL，focus=DIV/connected、overflow0。320×568浅色编辑器失败时Save禁用，Retry后全文恢复、已修改标题保留、focus=DIV/connected、overflow0。1440×900浅色详情侧栏489.59px，正文长URL换行、overflow0，关闭回原卡片标题。320深色延迟全文读取实际status与Save禁用；在只读fixture尝试保存得到405，保存中fieldset禁用、focus保持，失败后底部error/Retry持续可见，字段与全文保留、overflow0。未点击真实API保存，浏览器中的成功保存未验证。

截图位于仓库外interface-quality：memory-detail-390-dark-before、memory-detail-390-dark-failure-before为基线；memory-detail-390-dark-error-final、memory-detail-390-dark-recovered-final、memory-editor-320-light-error-final、memory-editor-320-light-recovered-final、memory-detail-1440-light-final、memory-editor-320-dark-loading-content-final、memory-editor-320-dark-save-error-final。前面读状态截图早于底部保存错误补充，读取与排版未再改变；最后save-error为最终实现。

八项自检：沿用既有标题/表单/正文尺度；收整元信息留白且保留20px独立分组；tab→元信息→正文→固定操作层级；既有深浅色和error/focus token；无新增动效，使用既有reduced-motion加载样式并移除保存pulse；可读status/error、Retry焦点及旧响应隔离；实际320/390/1440无本批溢出、手机操作44px；沿用LambChat视觉语言和原生字段，不增加装饰或资产。Impeccable仍按此前不可用环境的DESIGN.md清单人工检查。

最后生产修改后的门禁：767文件/3721项测试通过，lint零错误零警告；build含tsc/Vite/PWA/预算通过，eager JS559147/561152 bytes、precache5017375/5242880 bytes、91 entries。没有提高预算，保留既有chunk-size提示。git diff --check通过；门禁之后只补文档和原生证据，不再次重复已通过的检查。

继续检查Persona/Role侧栏有意义元信息、源码长行、其它表单与剩余语言/界面组合；真实存储、服务对话、触屏与软键盘待验。整体目标保持进行中，不以本批截图或门禁宣告全部界面完成。

## 2026-10-02 角色详情与嵌套弹层焦点

开工fetch/rebase确认最新origin/develop35af6aff，基线d2376f00，继续隔离分支，保留主checkout未提交内容。Persona预览的112px装饰横幅改为56px头像和来源/使用次数元信息行；复用既有头像加载/失败回退。提示词原文与Markdown共用外层阅读滚动，原文长行换行且复制原始文本；原文切换复用IconButton，aria-pressed表达当前模式，手机从22px增至44px。标签和技能标题采用语义heading，长技能名可换行。

Role详情补回被忽略subtitle中的系统标识，保留系统角色禁止删除及既有管理权限；无权限明确显示既有零计数。限额使用dl/dt/dd与已有auto-grid-cols，按实际侧栏宽度排列，零值仍显示；删除权限分组重复垂直margin，日期支持换行。

原生320浅色发现详情关闭到剩余Persona选择Modal后焦点落BODY。共享restoreOpenerFocus原先见到任何modal就退出；改为剩余顶层modal包含opener时允许归还，入口不可聚焦则在该modal内找可用控件，无控件时聚焦modal。保留新activeId、其它modal、已获有效焦点及hidden/inert守卫。四项新增真实嵌套关闭行为均RED→GREEN：保留挂载、卸载关闭、隐藏入口有其它控件和无控件；另五项新增行为覆盖两种Persona来源与使用次数、原文模式/原始复制、系统角色删除保护和权限零计数。目标5文件49项通过，独立只读复核的modal fallback P2已关闭，最终无确定新增P1/P2。

IAB独立3017实测：390深色、320浅色Persona原文及正文内部横向overflow均0（原文基线约2088px、hero基线正文8px）；切换与复制44×44px。320浅色Escape关闭实际回首个Persona卡片button，选择器保持。Role390深色/320浅色页与正文overflow0，固定footer编辑/关闭44px，系统角色无删除；1440深色侧栏489.59px，限额按容器单列433.59px，关闭返回角色标题。截图在仓库外interface-quality：persona-detail-390-dark-final、persona-source-390-dark-final、persona-source-320-light-final、persona-picker-320-light-focus-final、role-detail-390-dark-final、role-detail-320-light-final、role-detail-1440-dark-final。

用户明确“能搜就行了”：保持既有聊天代码块simpleSearch，只显示关键词、下一个/上一个和关闭，不扩展高级选项。390深色实际键盘输入report并导航命中，DOM显示一个选中结果，所有搜索/复制/导航按钮44px、整页overflow0；搜索邻接复制，python同行对齐，关闭回代码预览焦点。相关12项测试通过；basic-code-search-390-dark-final为最终截图。没有操作用户3002页面输入、剪贴板或重启其服务；3002现有进程仍使用本隔离worktree源码。

八项自检：沿用现有标题/元信息/等宽原文尺度；移除大块空横幅与重复分组margin，保留分组阅读留白；tab→元信息→提示词/技能→固定操作层级；深浅主题token与头像既有识别；无新增动效，沿用组件reduced-motion；切换aria-pressed、语义权限/限额和关闭焦点有测试/原生证据；320/390/1440与44px触控尺寸实测；复用LambChat头像、按钮和容器布局，无新依赖、资产、翻译键或另一套视觉体系。Impeccable按此前不可用环境的DESIGN.md清单人工检查。

最后生产修改后门禁：769文件/3730项测试通过；lint零错误零警告；build含tsc/Vite/PWA/预算通过，eager JS559135/561152 bytes、precache5016770/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。首轮全量唯一失败是已替换布局的旧sm:grid-cols-2源码断言，更新为容器适配约束后最终全量通过。git diff --check通过。门禁后仅文档/只读原生证据与清理。

这批仅GET fixture和模拟Clipboard行为，不证明真实角色保存、权限写入、服务对话、手机软键盘或触屏。继续其它表单/选择器与剩余语言和状态组合；整体目标保持进行中，不据此宣告全部界面完成。

## 2026-10-02 Persona 编辑器、能力选择器与代码查找

开工 fetch/rebase 确认最新 origin/develop 89f1fbf0，基线 05a7a88d；继续隔离 worktree，保留主 checkout 未提交内容。Persona 字段补齐原生 label、必填语义和范围提示，Select 使用已有命名接口。技能和 MCP 复用 PersonaEditorBindingSelector，保留 useSkills 的远端搜索与分页，删除重复选择器界面；门户定位使用既有 viewport hook。Escape 仅关闭选择器并归还入口，IME 不退出，箭头使用实际选项焦点，Enter/Space 保持原生激活；移除芯片为可命名的原生按钮。目录失败可重试并保留草稿，等待成功读取后才判断缺失，跨页绑定不误报；待加载的 MCP 入口禁用。

手机字段、移除、搜索、清除和关闭操作补齐 44px；长名称折行。狭短可见 viewport 使用内部滚动弹层，省去重复的已选芯片区，避免裁切可操作内容；正常高度的芯片区不收缩。新增 13 项真实编辑器/选择器行为测试均见 RED→GREEN，含失效目录、分页绑定、IME、Escape、键盘删除和短 viewport。更新旧源码断言指向共享选择器，独立复核发现的待加载 MCP 焦点与短 viewport 问题均关闭。

按用户本轮明确反馈，聊天代码搜索使用和复制相同的 IconButton；悬停仅在 24px 图标周围显示轻底色，按钮本身不铺底色。原生 CodeMirror 查找收成右对齐小条，桌面 280×34px、手机最大 280×46px；单层 1px 边框，输入框不再重复描边。继续使用 CodeMirror 已安装搜索能力，聊天和文件阅读保留关键词、前后命中及关闭，不另建搜索引擎。

文件和 HTML 源码预览隐藏代码组件重复的搜索工具栏，将搜索按钮放回已有工具栏；全屏仍保留搜索入口。原生 Cmd/Ctrl+F、匹配高亮和关闭后回代码焦点均保留。搜索 helper 通过动态 import 保持 CodeMirror lazy 边界；首次加载前禁用搜索，以共用 DOM readiness hook 监听真实编辑器挂载，退出时清理。延迟 Suspense 测试见 RED→GREEN，新增文件搜索 4 项验证普通/全屏、HTML 源码和首次加载状态。HTML 手机切换按钮只有图标，保留 aria-label/pressed、44×44px 与 reduced-motion。

IAB 3017：Persona 390 深浅色最终已选区 127px、不收缩、弹层 400px、整页/弹层横向 overflow 0；本批此前 390 深色失败重试、320 浅色失败恢复、320×260 狭短 viewport 与 1440 浅色锚定/键盘关闭验证正常。聊天代码 1105 深色悬停反馈 24px、查找条 280×34px；390 深色查找 280×46px，report 实际命中；320 深色几何 268×46px，整页/查找 overflow 0。文件 390 深色标题和搜索/下载/更多/关闭同一行、无 .code-editor-toolbar，操作 44px、横向 overflow 0；choice 两个实际匹配、一个选中，Escape 回代码，Cmd+F 重新打开。独立文件预览的 CSS 全屏模式也能搜索，最终查找条 top65px、关闭按钮 bottom60px，保留5px间隔。此处为浏览器 viewport 和只读 fixture，不证明真机触屏、软键盘、真实保存或服务对话。

八项人工自检：既有表单与等宽正文排版；保留阅读分组、减去重复搜索行；标题/动作/正文层级；深浅主题 token；无新增动效且 HTML 尊重 reduced-motion；实际焦点/错误/重试/加载有行为测试；手机尺寸和长名称无本批溢出；复用 LambChat 组件与 CodeMirror，无新依赖或资产。沿用此前 Impeccable 不可用环境的 DESIGN.md 人工清单。

最终生产修改后门禁：771 文件 / 3748 项前端测试通过；lint 零错误零警告；build 含 tsc/Vite/PWA/预算通过，eager JavaScript 559140/561152 bytes，precache 5017684/5242880 bytes / 91 entries。未提高预算。最后 gate 后仅补文档及只读视觉证据。

头像上传生命周期、Persona 保存请求归属与其余页面/状态/语言组合继续检查；整体目标保持进行中，不据本批门禁宣告所有界面完成。3017 已被用户采用，继续保留预览和用户标签页；原 3002 服务与用户草稿未操作。

## 2026-10-02 角色编辑器头像、保存与失败恢复

开工 fetch/rebase 确认最新 origin/develop 2bba3d15，基线 81a0fac3；继续隔离工作树并保留主 checkout。上轮文件搜索的补充复查确认标题工具栏和原生 CodeMirror 搜索已满足用户要求，未另建搜索 UI；相关15项测试重新通过。

头像预览改为命名原生按钮，支持直接替换已有头像、键盘激活；合并重复移除分支，移除入口始终可见，手机44px。图片加载失败保留原头像值。使用已有 UploadHandle 在退出时中止，压缩及上传的迟到结果不得修改后来打开的草稿；上传等待期间阻止提交，失败在头像旁持续说明并可重试同一原文件。图标选择器在表单内展开，避免覆盖字段，原生选项可Tab操作、Escape只关闭本层并归还入口、IME不退出、移除也归还稳定入口。静态3D图标替代此编辑器的自动播放动画，沿用既有资源与主题。

保存使用本会话等待与请求归属，阻止双重提交、冻结提交的字段、保留可聚焦容器及取消路径；返回null或抛错均显示既有错误组件与Retry，草稿保留。关闭重开同id及切换角色后，旧保存不关闭新编辑器。复核发现共享isMutating会冻结新稿，修复为只守卫并发提交，不误显示当前保存等待；真实usePersonaPresets集成测试涵盖旧mutation及后续列表GET两个等待阶段。没有改变API、权限或保存payload契约。13项新增行为测试与13项既有恢复测试通过；移除焦点和共享等待问题均先见RED再GREEN，独立复核无剩余确定P1/P2。

独立3018只读/显式模拟fixture：390×844深色图标216×216、选项44px、Escape回入口；保存等待字段禁用、焦点保持在表单，首次503后修改名称和头像保留、底部错误/Retry可见，Retry模拟200后关闭。320×568浅色图标同样无溢出；已有机器人头像上传公开测试icon，等待Save禁用、焦点保持，503后原头像和错误保留，Retry同文件后模拟200恢复、移除回入口。1440×900浅色侧栏489.59px、图标184×184；834×1112浅色编辑器640px，图标184px；上述页面横向overflow0。未提交真实文件、修改真实角色、验证存储、权限写入、真机触屏或软键盘。截图位于仓库外interface-quality：persona-avatar-picker-390-dark-final、persona-save-390-dark-pending-final、persona-save-390-dark-error-final、persona-avatar-picker-320-light-final、persona-avatar-upload-320-light-pending-final、persona-avatar-upload-320-light-error-final、persona-avatar-upload-320-light-recovered-final、persona-avatar-picker-1440-light-final、persona-avatar-picker-834-light-final。测试文件热更新曾重载临时页面，该次错误截图不作为证据；最终截图在最后源码编辑和新query之后重放。

八项自检：既有标签/字段字体与尺度；保留分组留白、删除隐藏移除入口与浮层遮挡；头像/草稿/固定页脚主次清楚；深浅色主题与错误/焦点token；静态资源和reduced-motion过渡；等待、失败、重试、取消、键盘与旧响应归属；实际手机/平板/桌面几何及44px操作；沿用LambChat组件和已有资源，无新依赖或额外视觉体系。沿用Impeccable不可用环境的DESIGN.md人工清单。

最后生产修改后全量772文件/3761项前端测试通过，lint零错误零警告，build含tsc/Vite/PWA/性能预算通过；eager JavaScript 559142/561152 bytes、precache 5017930/5242880 bytes、91 entries。没有提高预算，保留既有chunk-size提示。门禁后只补文档与实际只读视觉证据。3017与用户页面保留；本轮临时3018服务和检查标签页回收，浏览器临时尺寸恢复。

全界面目标继续进行；其它表单、弹层、长语言文案及剩余空/错/加载组合仍需继续核对，不能据本批测试与截图宣告整体完成。

## 2026-10-02 团队编辑器共用控件与窄屏操作

本轮继续现有隔离 worktree，fetch/rebase 确认最新 origin/develop；前一轮文件原生查找浮层已提交为34295d84。团队编辑器基线发现旧头像入口未采用角色编辑器的共用控件，手机“选择图标”样式失配、上传预览无键盘入口；重复实现还会在图片加载失败时清空已存头像，上传时允许提交。

TeamBuilder 删除重复头像上传/图标选择和开场提示词实现，复用现有 AvatarSection / StarterPromptsEditor。AvatarSection 接口收敛为 avatar / onAvatarChange，两个实际调用方共享清理、上传错误重试、静态图标和焦点操作；原 Persona 13 项生命周期测试保持通过。团队上传同步 ref 阻止 imperative 保存，真实 Wrapper 页脚也禁用保存；teamId 切换卸载旧头像组件、中止上传，迟到结果不能覆盖新团队。新旧头像加载失败均保留数据，失败保留原文件供重试。补全团队名称/简介/标签/指令标签关联、必填语义和 hint 描述；开场提示词沿用现有命名控件。角色搜索具备 disclosure 语义、命名输入和局部 Escape/IME 边界，关闭归还入口焦点。指令说明使用现有12px文本 token，去掉11px/0.75透明度内联。页脚复用 Button / PanelFooterActions，保存等待显示 loading/status。未添加依赖、新 API 或设计 token。

TDD：5 项团队可观察行为先全部失败，再通过，覆盖命名/键盘、图片失败保留头像、上传阻止保存/换记录清理、同文件重试、角色搜索 Escape/IME。共享页脚源码断言同样先见失败再通过。相关9文件/43测试通过；最终全部生产修改后773文件/3767项测试通过，lint零错误零警告，build含tsc/Vite/PWA与性能预算通过：eager JavaScript 559139/561152 bytes，precache 5017933/5242880 bytes、91 entries。独立只读复核未发现本批确定P1/P2。未提高预算。

原生 IAB 只读/显式模拟 fixture：390深色长团队名、216px图标区和44px选择按钮无横向溢出；上传等待禁用保存，首次503后名称与编程头像保留，Retry同文件模拟200恢复。成员搜索“跨部门”长名称可读，Escape回添加入口且编辑器保持打开。最终页脚/说明文字修改后在新query重放320×740浅色：图标区216px、按钮/页脚44px、overflow0，上传等待/503/Retry恢复，草稿保留；834×1112浅色及1440×900浅色均overflow0，桌面图标区184px，Escape归还选择入口。截图保存在仓库外interface-quality目录：team-avatar-picker-320-light-final、team-avatar-upload-320-light-pending-final、team-avatar-upload-320-light-error-final、team-avatar-picker-834-light-final、team-avatar-picker-1440-light-final；此前390深色截图用于头像/角色查找行为证据，未作为最后页脚样式证据。浏览器视口与模拟响应不证明真机触屏/软键盘、真实上传存储或团队写入。

八项人工自检：共用字段/标签排版；保持正文分组留白并删除重复控件；头像、草稿、主操作层级清楚；使用深浅主题/错误/焦点token；图标静态且既有过渡尊重reduced-motion；等待、失败、重试、键盘和迟到上传行为有验证；手机/平板/桌面与长名称已走查；沿用LambChat组件与已有资源。Impeccable未安装，按DESIGN.md交付清单人工复核。临时3018服务与本轮标签页回收，临时视口恢复；用户3017、原3002及标签页保留。

整体目标继续进行。团队详情读取/保存请求归属、成员操作、其余编辑器/弹层、长语言及空/错/加载组合仍需下一阶段继续核对，不据本轮局部门禁宣告全界面完成。

## 2026-10-02 团队详情、保存状态与请求归属

继续隔离 worktree，本阶段已 fetch/rebase 到 origin/develop 4ed77d7e，基线 e8013d6d，保留主 checkout。上一用户反馈的文件原生查找浮层补充验证：320px 宽查找条280px，页面横向overflow0，choice两个真实匹配，Escape回代码焦点；桌面打开前后正文top140px、height554.40625px均不变，相关20项测试通过。未另建搜索 UI。

TeamBuilder 详情读取期间不再展示可编辑的空表单，保存保持禁用；失败显示既有错误组件和紧凑44px重试入口，不把既有记录当作新建。重试聚焦稳定表单，错误态aria-busy为false。读取、保存、克隆和删除均记录当前编辑会话，切换记录或卸载使旧请求的状态、toast、关闭回调失效。同步ref阻止重复提交，保存期间原生fieldset冻结字段，焦点保持表单且取消路径保留。失败不丢草稿，Wrapper固定页脚持续提示并显示Retry；克隆切换编辑身份时清除旧保存错误和头像重试文件。

成员模式/模型的门户Select显式禁用；共用Select在disabled时立即隐藏并关闭已展开选项，不对本来关闭的控件发出多余onOpenChange。既有controlled调用方SelectRow已核对，角色编辑器生命周期与选择器恢复回归通过。新增16项行为覆盖详情等待/失败重试、迟到读取、同步双提交、字段冻结/焦点、保存失败保留、旧保存resolve/reject不干扰新保存、卸载关闭、门户选项关闭、真实Wrapper页脚重试、迟到克隆/删除与克隆头像错误隔离。边界测试先见RED再GREEN，相关13文件/77项通过。独立只读复核未发现确定新增P1/P2；lint对cleanup读取ref的通用警告改为以本effect的owner+1失效，最后门禁重跑。

预览复用已有显式模拟分支，增加team-flow=1：团队创建POST和单个团队PUT等待2秒，failure=team-save首次503、重试200；单条详情GET同样延迟，failure=team-detail首次503、重试恢复。请求字节丢弃，无解析、存储、真实列表更新或API转发，其余写请求仍405。PANEL_PREVIEW.md已同步说明。

IAB独立3018：390深色实际编辑已有团队、长名称草稿、打开成员模型门户后保存；等待字段全部禁用、焦点FORM、门户0、整页overflow0。首次503后长名称/成员指导保留、错误和Retry固定页脚可见、页脚overflow0；Retry模拟200后编辑器退出。320浅色详情加载/失败时Save禁用，失败aria-busy=false、重试62.56×44px、整页overflow0；重试期间焦点FORM，恢复原团队名称并启用Save。834浅色页脚638px、1440浅色侧栏432px/页脚430px，整页及页脚overflow0。截图在仓库外interface-quality目录：team-detail-loading-320-light-final、team-detail-error-320-light-final、team-detail-recovered-320-light-final、team-detail-recovered-834-light-final、team-detail-recovered-1440-light-final、team-save-390-dark-pending-final、team-save-390-dark-error-final、team-save-390-dark-error-draft-final。

八项自检：沿用现有表单排版与标签字体；保持分组阅读留白，错误重试不铺满宽度；详情/草稿/固定页脚状态层级清楚；既有深浅主题与错误/焦点token；无新增动效；等待、禁用、失败、重试、取消和迟到响应有测试及实际交互；320/390/834/1440检查无本批横向溢出、手机动作44px；复用LambChat组件及已有模拟机制，无新依赖、资产、API或翻译键。Impeccable未安装，沿用DESIGN.md人工清单。

最后生产修改后全量773文件/3783项测试通过，lint零错误零警告，build含tsc/Vite/PWA与性能预算通过：eager JavaScript559143/561152 bytes，precache5017989/5242880 bytes、91 entries，未提高预算，保留既有chunk-size提示。git diff --check通过。临时3018服务与测试标签页已回收、视口恢复，用户3017/3002及其标签保留。本批模拟响应/浏览器尺寸不证明真实团队存储、权限写入、真机触屏或软键盘。

整体目标保持进行中。此次实际手机截图仍显示多个成员默认展开形成很长的配置列表；下一阶段继续检查成员卡片信息密度、目录失败/长列表，以及其余编辑器、长语言和空/错/加载组合，不以局部门禁作为全界面完成依据。


## 2026-10-02 团队成员摘要、角色目录与窄屏密度

继续隔离 worktree；本轮 fetch 发现 develop 已纳入前批提交，暂存本轮六个未提交文件、rebase 到最新 origin/develop 5523922d，再恢复原改动，无冲突。主 checkout 未操作。上一目标回合获得文件原生查找的当前证据：320/390px 与1440px 查找浮层280px，代码位置/高度不变，choice 两个实际匹配，Escape回代码；23项相关测试通过，未另造搜索组件。

成员不再因已有指导全部自动展开，默认摘要保留姓名、标签、模式/模型；整个摘要是命名原生按钮，44px起、aria-expanded/controls，按需展开。折叠保留指导、禁用隐藏字段并关闭门户Select；局部Escape消费事件、IME不退出、焦点回摘要，父编辑器保持打开。删除元数据换行后悬空的装饰点和两枚没有数值的模式/模型统计。卡片按自身宽度响应：390px手机普通卡片79.02px，320px摘要和动作分行120px，动作仍44px/gap0；834px模态卡片614×70px，1440px侧栏卡片406×70px。隐藏指导margin仅在展开时保留，消除折叠后的空白。长名称两行、标签截断、元数据自然换行，不压缩正文和表单分组留白。

角色目录从首100条本地筛选改为既有API的20项服务端分页/q搜索，200ms查询防抖；取消归属隔离迟到响应，loading隐藏过时选项。错误与空结果分开，既有错误组件和Retry保留团队草稿；Retry/翻页先聚焦稳定搜索输入，结果返回滚动到顶部，查询回第一页。沿用共享Pagination，单页仍挂载以允许页码校正。预览增加failure=team-roles仅20项目录GET首次503，重试恢复，PANEL_PREVIEW.md已说明，写请求仍405。

真实浏览器长名称走查还发现默认星标的primary按钮前景被深色通用样式盖成背景色，透明卡片上近乎不可见。改为ghost，active/danger/hover选择器加成员卡片作用域，保留主题前景与错误色；浅色默认星标rgb(120,113,108)、深色rgb(214,211,209)，均来自当前主题primary。相关样式守卫先RED后GREEN。新增8项回归覆盖默认折叠/指导保留、Escape/IME、门户关闭、目录加载/失败重试、分页及第100条之后服务端搜索、过时响应、上述样式覆盖。此前重试/翻页焦点测试补显式聚焦按钮后先见2项RED再修复，避免fireEvent未聚焦导致假通过。独立只读复核未发现确定P1/P2。

最终生产修改后IAB：320×740浅色首次目录503、Retry恢复、下一页21–40/2–4、搜索跨部门回单页10项、添加长名称角色、Escape回添加入口，团队名称草稿保留；长卡127.02px、整页overflow0。390×844深色默认成员星标、三卡79.02px与44px动作；834×1112深色和1440×900深色均overflow0，实际桌面滚动至成员区域检查三卡完整。先前角色目录390深色失败恢复与局部Escape也已操作；最终截图保存在仓库外interface-quality：team-role-catalog-320-light-error-final、team-members-320-light-long-name-final、team-members-390-dark-collapsed-final、team-members-834-dark-final、team-members-1440-dark-final。只读fixture/浏览器viewport不证明真实团队写入、权限、存储、真机触屏或软键盘。

八项自检：姓名/字段/等宽内容沿用既有尺度；删隐藏空白、保留分组留白；摘要/配置/统计/操作层级明确；深浅色theme token与默认/危险状态可辨；没有新增动效，折叠/角色目录尊重reduced-motion；错误重试/分页/焦点/IME/旧请求有验证；320/390/834/1440实测与长名称；复用LambChat组件，无新依赖/素材/额外设计体系。Impeccable沿现有不可用环境按DESIGN.md清单人工检查。

最终全量773文件/3791项测试通过，lint零错误零警告，最后生产修改后build含tsc/Vite/PWA/性能预算通过：eager JavaScript559140/561152 bytes、precache5018660/5242880 bytes、91 entries。全量中一次userMenu的profile action transfers focus into the new dialog instead of the avatar失败，独立11项通过；其findByRole只等DOM出现而非focus effect，用waitFor保持相同焦点要求后最终全量通过，未改生产焦点逻辑。未提高预算。

整体目标保持进行中。下一阶段核查团队及其它配置中的助手/模型目录加载失败（TeamBuilder仍把目录异常转为空数组）、剩余表单/弹层/长语言与空/错/加载组合，并完成全部执行清单对应证据。不能据本批门禁与截图宣告全界面完成。

## 2026-10-02 模型、助手目录与个人偏好恢复

继续隔离 worktree，开工 fetch/rebase 确认 origin/develop 5523922d，基线6e82fc61；主 checkout 保留。文件预览当前已使用 CodeMirror 原生浮动查找、showToolbar=false，未另建搜索界面。320/390px查找条280×46px、桌面正文打开前后top140px/height554.40625px不变；choice两个实际匹配、Escape回代码、Cmd+F可重新打开，相关16项测试通过。

SettingsContext 显式提供模型加载、失败、重试状态，失败刷新保留已知模型和系统默认；账号/token变化清空旧目录与置顶，取消归属拒绝迟到模型/置顶响应。TeamBuilder 有provider时复用其状态，不再因null重复请求；无provider的读取和助手读取失败保留现有选择，禁用对应选择器并显示一次紧凑反馈，团队名称及指导仍可编辑。成员显式但未知的模型/模式ID继续可读。个人模型页区分加载、失败和成功空目录，个人偏好同时读取助手列表与已存偏好，偏好失败不伪造系统默认。共用CatalogStatus用现有Button/token/i18n，重试先聚焦稳定容器；桌面32px、手机及粗指针44px。聊天标题栏采用既有图标入口，重试先回稳定菜单按钮。原生走查发现个人偏好懒加载主题分区会令整个应用闪空，增加局部Suspense边界保留其它设置；共享spinner响应prefers-reduced-motion。无新依赖、主题token、资产、API或翻译键。

新增12项测试，包含失败/成功空结果、重试、失败刷新保留、账号切换及迟到响应、provider避免重复请求、团队草稿和显式选择保留、已存偏好失败、稳定焦点、冷加载局部边界及减弱动效。行为先RED再GREEN；最后全量中CSS源码守卫因jsdom的import.meta.url不是file协议失败，改用仓库既有cwd相对文件读取后最终777文件/3803项全部通过。独立复核指出重试焦点与手机按钮两个P2，修复后复核无剩余确定P1/P2；主题分区增量复核通过。

IAB独立3018最终视觉与操作证据：390×844深色团队模型503，成员指导/名称草稿保留，44px重试后模型恢复、焦点FORM；320×740浅色个人模型503，44px重试后目录恢复、焦点稳定DIV；834×1112深色个人偏好503，默认助手禁用，32px重试恢复已存偏好；1440×900浅色聊天标题模型重试32×32px，恢复后焦点菜单；320×740暖色团队助手503，44px重试恢复；320×740浅色俄语个人模型错误长文案与44px重试无溢出。上述页面及弹层横向overflow0。截图在仓库外interface-quality目录：catalog-team-390-dark-error-final、catalog-profile-models-320-light-error-final、catalog-preferences-834-dark-error-final、catalog-header-1440-light-error-final、catalog-team-320-sepia-agents-error-final、catalog-profile-models-320-light-ru-error-final。最后CSS热更新后尝试的team-recovered截图已因编辑器关闭失去预期内容，不作为证据。临时语言已恢复中文、临时视口及标签页回收、3018停止；3017与用户页面保留。只读fixture不证明真实认证、保存、存储、真机触屏或软键盘。

八项人工自检：保留表单字体与标签尺度；紧凑状态不铺满新卡片且分组留白保留；标题/字段/状态/重试层级清楚；复用深浅及暖色主题；spinner支持减弱动态且无新增装饰动画；失败、重试、焦点、禁用、草稿与迟到响应可验证；320/390/834/1440和俄语长文案无本批溢出；沿用LambChat组件与原生编辑器。Impeccable未安装，按DESIGN.md同一清单人工检查。最终lint零错误零警告；build含tsc/Vite/PWA/性能预算通过，eager JavaScript559229/561152 bytes、precache5021068/5242880 bytes、91 entries，未提高预算。最后生产修改后的全量测试与build已完成。

全界面目标继续进行。剩余聊天助手目录失败、个人偏好及其它表单写入恢复、选择器/弹层/长语言与空错加载组合，以及真实服务和设备证据继续核查，不以本批门禁宣告整体完成。

## 2026-10-02 聊天助手模式目录与紧凑状态

上一目标回合完成模型/偏好读取恢复并提交，本回合属于实际进展。继续现有隔离worktree，fetch/rebase到最新origin/develop f03e8f88，上一提交rebase为bb983504；主checkout与用户3017服务保留。追踪真实调用链发现AgentSelector已无实际使用，聊天使用ChatInputToolbar→ChatInputSelectors→AgentModeSelector；未改闲置组件。useAgentList原来目录失败只console.error、入口按条数消失；普通刷新和偏好刷新重复实现且迟到响应会覆盖新选择/提前结束loading。

合并两条读取路径，显式加载/失败状态，经useAgent→ChatAppContent→ChatView→ChatInput透传。每次读取记录请求序号，旧请求不能覆盖目录、模型访问范围、当前选择或等待/错误状态，卸载失效；失败保留已知数据。偏好刷新在响应落地时只于无消息状态应用新默认，普通重试保留原选择。模式入口在初始失败、空目录和单助手状态保持可达，加载/错误沿用既有spinner和AlertCircle及已翻译的title；选择器复用CatalogStatus，等待/错误时禁用原选项，重试聚焦稳定内容容器。成功空目录使用现有common.noResults，不伪造失败或空白。选中按钮增加aria-pressed；未知模式入口有具名标签。说明使用现有次级文字token、自然换行，删除truncate与transition-all。沿用共享弹层并复用modal-size-md，外层和可见内容统一448px，取消40vh的空白最小高度；手机保持全宽与已有安全区、手势/焦点/关闭机制。无新API、写入、依赖、素材、主题token或翻译键。

5项新增行为测试先全部RED，再GREEN，覆盖失败刷新保留选择及model access、竞争响应与loading归属、偏好切默认边界、无目录重试恢复稳定焦点、成功空目录与Escape回入口。初轮build揭示ChatView类型/透传缺失，补齐真实中间层后原生错误入口得到正确状态。全量揭示ChatInput及ChatAppContent既有行数门禁越界，删除两层只调用React setter的回调、直接传稳定setter/refreshAgents，将重复agents.find/IIFE提为当前助手信息，i18n使用现有hook返回值；两个门禁保持原阈值并恢复通过，未为预算另建抽象。独立只读复核及两次增量复核无确定P1/P2。

IAB独立3018：390×844深色首次503时入口具名“选择模式·加载失败”，错误sheet紧凑、Retry高44px，输入草稿“目录恢复后保留这段草稿”在重试及Escape后仍在，恢复焦点为稳定DIV，Escape回快速助手入口。320×740浅色2秒重试等待aria-busy=true、焦点DIV、overflow0；恢复选项可用。320×740暖色成功空目录显示未找到结果，sheet181.17px、Escape可关闭。1440×900及834×1112浅色单助手面板448×194.875px、overflow0，仍有可用关闭/选中入口。320×300深色俄语sheet在top16px内、height284px，说明换行，内容344px在173px区域滚动，Tab到最后团队选项时自动滚入可见范围，Escape回原入口；390×844俄语长说明全部可读。临时语言恢复中文，最终390深色普通三选项sheet337.67px、overflow0。截图保存在仓库外interface-quality目录：chat-modes-390-dark-error-final、chat-modes-390-dark-recovered-final、chat-modes-320-light-error-final、chat-modes-320-light-loading-final、chat-modes-320-sepia-empty-final、chat-modes-1440-light-single-final、chat-modes-834-light-single-final、chat-modes-320-dark-ru-short-final、chat-modes-390-dark-ru-final、chat-modes-390-dark-options-complete。早期834/1440宽外壳截图不作为最终尺寸证据。预览只扩展GET等待/空/单助手，其他写请求仍405；不证明真实认证、偏好写入、模型对话、真机触屏或软键盘。

八项人工自检：保持现有标题/衬线模式名称/正文尺度；错误与少量选项按内容收高、保留分组留白；标题、当前模式、说明、重试层级明确；使用当前三主题与次级文字token；无新动画，已有modal/spinner尊重reduced-motion；错误、重试、禁用、选择、焦点、Tab与迟到响应有验证；320/390/834/1440及俄语短屏无本批溢出；复用LambChat组件与既有标准尺寸。沿用Impeccable不可用环境的DESIGN.md交付清单。最后生产修改后779文件/3808项前端测试通过，lint零错误零警告，build含tsc/Vite/PWA/预算通过：eager JavaScript559234/561152 bytes、precache5022200/5242880 bytes、91 entries。git diff --check通过，未提高行数或性能预算。

本轮临时3018服务和走查标签页已回收、视口恢复；原checkout仍只有既有.v2c/.video_agent未跟踪目录，用户3017服务PID92955与其页面保留。

全界面目标保持进行中；个人偏好保存失败、个人资料及其它表单写入恢复、剩余选择器/弹层/长语言/空错加载组合，以及真实服务和设备证据仍需继续，不据本批门禁宣告整体完成。

## 2026-10-02 个人偏好保存等待与同步恢复

继续隔离 worktree，fetch/rebase 到最新 origin/develop 8f4c457f；文件查找入口提交重放为461cfc5e。默认助手保存失败保留选择而不清空；默认模型、语言、字体、发送键、思考强度保留即时本机应用并明确云端同步失败；记忆与云端执行确认策略表达尚未保存。复用CatalogStatus、现有Button和token，逐字段保存禁用、原请求重试，重试不重复本机事件。共享usePreferenceWrites按账号与请求归属阻止旧响应及尚未发送的旧请求，避免重复提交。原生switch与定时时间输入保持语义和手机44px；等待时把禁用选择器焦点移到稳定内容容器。

主题写入收敛到ThemeContext，初始化、已存偏好恢复及定时自动切换不再重复PUT。主题和定时配置共用appearance请求槽，两个操作都提交完整theme+themeSchedule快照（含null），避免失败后改另一外观项清掉错误却漏同步旧字段。快捷主题入口及标题菜单支持同一错误重试。独立只读复核找到此P2，新增两条跨操作回归先RED后修复，再复核无确定P1/P2。共29项相关行为测试通过，覆盖选择保留、准确重试、账号切换迟到/未发送请求、焦点、主题写入次数和跨操作恢复。

安全fixture只在preferences-flow=1允许两项PUT的模拟等待/失败/成功，请求字节丢弃，不解析、保存或转发。IAB390深色默认模型等待焦点DIV；320深色错误保留模型选择、重试44px、重试期间焦点DIV；320浅色俄语完整错误自然换行、无横向溢出，重试成功撤掉错误。834浅色恢复无溢出；1440浅色默认助手失败保留搜索助手、重试32px；切390仍保留错误与选择，重试44px且焦点DIV。临时俄语恢复中文。截图在仓库外interface-quality：preferences-sync-failure-mobile、preferences-sync-failure-320-light-ru、preferences-agent-failure-desktop。此证据不证明真实偏好持久化、认证或真机软键盘。

八项自检：沿用正文与衬线标题尺度；保留字段节奏且无重复分隔；读取/等待/失败/本机同步状态分层；五语文案及深浅色主题token；未新增动效、既有spinner尊重reduced-motion；禁用/重试/账号隔离/焦点经行为验证；320/390/834/1440及俄语长文案实测；复用LambChat标准组件，无新依赖或设计体系。按DESIGN.md交付清单人工检查。最终780文件/3826项测试、lint、build含tsc/Vite/PWA通过；eager JavaScript559727/561152 bytes，precache5026085/5242880 bytes、91 entries，未提高预算。

全界面目标保持进行中。下一阶段继续个人信息用户名/头像、服务地址/本地沙箱设置及标题栏语言保存恢复，剩余选择器和弹层状态矩阵、真实服务及设备验证，不能据本批门禁宣告整体完成。

本轮额外确认最新文件预览请求：390×844浅色代码搜索并入标题工具栏，CodeMirror原生浮层280×46px，choice命中两处，页面无横向溢出；Escape关闭并回到代码预览。截图file-preview-native-find-390-light-final保存在同一仓库外证据目录。临时3018服务、走查标签页已回收，视口恢复，用户3017与主checkout目录保留。

## 2026-10-02 个人信息编辑与头像恢复

上一目标回合属于progress：已提交偏好保存与原生文件查找证据。本轮继续隔离worktree，fetch/rebase到最新origin/develop 58f9d9b2，偏好提交重放为d026effb，主checkout不动。个人用户名改原生具名form：Enter提交，等待冻结输入和取消、同步ref拒绝重复提交；失败保留草稿和具名alert，重试使用当前草稿；Escape局部取消且IME不退出，成功/取消回编辑按钮。账号key重置草稿、卸载后的旧保存不再刷新或toast。

头像改原生Button打开文件选择，手机/粗指针44px，输入清空可重选同文件；复用usePreferenceWrites与CatalogStatus呈现持续上传/删除错误、重试及稳定焦点。删92行独立压缩实现及重复profile GET，复用compressImageFile，512px/100KB；压缩文件缓存用于准确重试，关闭/账号切换中止worker并阻止准备后继续上传。只读复核发现默认original回退会让无Worker浏览器的大JPEG永远撞2MB门限，补已有main-thread回退。两条真实压缩集成验证Worker缺失/unsupported、3MB JPEG降至512×256/90KB并通过模拟2MB上传门限，先RED后GREEN。新11项行为加既有压缩/模态共17项通过，再复核无确定P1/P2。用户名/邮箱与管理员邮箱自然换行，复用五语现有文案，无新token、依赖或素材。

显式profile-flow fixture只模拟用户名POST/头像POST、DELETE并丢弃字节；GET长资料和现有公开头像不是真实持久化。IAB最终320浅色长用户名/邮箱/角色全可读、avatar动作44px、content/page横向overflow0；Enter提交用户名后input/cancel禁用、aria-busy=true、焦点FORM。上传现有公开测试图标后焦点头像DIV、上传/删除按钮禁用；两项失败同时保留，各自重试44px。1440浅色错误分层、头像Retry32px/用户名38px；834浅色overflow0，两项重试后错误消失、编辑结束且焦点回编辑。局部Escape保留设置窗口并回编辑；390深色删除失败/重试维持头像DIV焦点，无横向溢出。截图保存仓库外interface-quality：profile-info-320-light-long-final、profile-info-320-light-errors-final、profile-info-1440-light-errors-final、profile-info-834-light-recovered-final、profile-info-390-dark-delete-error-final。浏览器预览不证明真实头像/用户名写入、权限或真机软键盘。

八项人工自检：复用标题/字段尺度；保留资料分组留白且不新增卡片；头像、身份、错误、操作层级清楚；沿用深浅色token；无新动效、现有spinner遵循reduced-motion；表单/IME/重试/焦点/旧请求经行为验证；320/390/834/1440与长资料无本批溢出；保持LambChat组件语言和五语文案。沿DESIGN.md清单人工检查。最终781文件/3837项测试、lint、build含tsc/Vite/PWA通过，eager JavaScript559725/561152 bytes、precache5027071/5242880 bytes、91 entries，未提高预算。

全界面目标保持进行中。下一阶段重点：AuthProvider已开始的refreshUser在账号切换后的响应归属（本批只保护尚未启动的刷新）；服务地址/本地沙箱设置、标题栏语言保存及其它未完成状态矩阵，随后验证真实服务和设备。不得将本批预览、门禁或局部修复视为全站完成。

最终390深色删除重试成功后alert=0、焦点仍头像DIV、overflow0；已回收本轮3018服务和临时标签页、恢复视口。用户3017服务及主checkout的.v2c/.video_agent未跟踪目录保留。


## 2026-10-02 文件预览原生查找统一

根据最新请求，先处理文件预览搜索。正式DocumentPreview已复用页头按钮和原生浮层，但普通CodeMirrorViewer及市场只读SkillEditor仍会在打开查找时占一行。共享只读Viewer默认启用既有simple/overlay样式；只读SkillEditor浮动按钮及查找框，编辑态保留完整原生查找/替换。复用@codemirror/search，无自制搜索、依赖、文案或token。两项回归先RED（缺少紧凑浮层class）后GREEN，补真实原生匹配高亮/下一个行为；独立复核无确定P1/P2。

IAB实际市场SKILL.md文件：桌面展开前后cm-content top均107.59375px；320深色查找框280px、按钮44px，Escape只关闭查找并回SKILL.md，Cmd/Ctrl+F重新打开；390浅色框280px、匹配1处、页面横向overflow0。文件库Python预览同样无额外工具行，原生匹配2处。截图存仓库外interface-quality/native-file-find-mobile-dark.png、native-file-find-mobile-light.png、native-file-find-desktop-dark.png。该证据是响应式浏览器预览，不代表真机软键盘。

沿DESIGN.md人工检查排版、留白、层级、主题、动效、焦点、响应式与现有组件一致性；无新增动效，已有reduced-motion规则保留。全量781文件/3837测试、lint、build（含tsc、Vite、PWA）通过；eager JS559727/561152、precache5027071/5242880、91项，未提高预算。仅提交本次文件预览改动。未完成的auth刷新测试暂存仓库外/tmp/lambchat-authRefreshOwnership-paused-20261002.test.tsx，后续继续原有全站目标；本批不能视为全站完成。

## 2026-10-02 资料刷新归属与共享语言同步

本轮先fetch/rebase到origin/develop 54ddd574。原mobile-density checkout随后被外部流程reset至origin/codex/interface-quality，reflog确认；未覆盖该现场。改用原生工具创建interface-state worktree及codex/interface-state分支，从最新develop重放此前未集成的资料编辑、文件查找和两行证据文档。后续修改仅在新worktree；原checkout和用户3017服务保留。

refreshUser用请求序号、账号token subject和卸载失效保护已开始的资料刷新；同账号token续期仍可应用身份与权限，登出立即清权限。普通同账号资料更新不再回放旧云端主题/语言覆盖本机新选择，新账号首次OAuth刷新仍恢复云端偏好。8项真实AuthProvider行为测试先6项RED后全部GREEN；范围仅refreshUser，初始化/login/OAuth独立请求仍需继续审查。

语言入口复用ResourceCardMenu和既有usePreferenceWrites，等待禁用、失败保留本机语言并提供准确重试；访客与公开分享只本机切换，删除SharedPage重复菜单。复核发现每入口独立请求会让旧失败重试覆盖设置页新成功选择，新增实际双入口集成先2项RED，改为按账号共享LanguagePreferenceProvider后GREEN。复核还发现共享sm按钮样式覆盖普通44px类，修正手机/coarse important尺寸；两项P2关闭，最终复核无其他确定P1/P2。

IAB独立3018：390深色Header错误说明可读，原语言保留，重试显示禁用Saving后撤错；320浅色访客菜单五语可达，Down/Escape回入口，中文选择后焦点语言按钮、横向overflow0；共享页320深色复用同菜单。登录/共享页语言入口实际44×44，桌面1440为32×32、overflow0。截图在仓库外interface-quality：language-sync-390-dark-error-final、language-menu-320-light-final、language-shared-320-dark-final。独立预览因模块扩展名变更保留了Vite旧解析，确认missing-module后仅重启本轮服务恢复；不是生产加载问题。无真实认证/云端持久化/真机触屏证据。

八项自检沿用现有文字尺度与留白，状态层级清楚，主题token和五语既有文案，无新动效/依赖/素材；复用共享菜单键盘/焦点机制，窄屏触控尺寸实际核对，保持LambChat视觉语言。按DESIGN.md交付清单人工检查。最终47项针对性行为测试及全量783文件/3852项通过，lint零错误零警告，build含tsc/Vite/PWA通过；eager JS560109/561152、precache5028288/5242880、92项，未提高预算。全站目标仍进行中，服务地址/本地沙箱设置、剩余状态组合和真实服务/设备验证留待后续，不据本批门禁宣告整体完成。

最后按用户最新请求复验390深色Python文件：搜索入口在标题工具栏，原生查找浮层280×46px；展开前后文件cm-content top均141px，无额外搜索行，choice命中显示，Escape关闭回代码预览，页面overflow0。截图native-file-find-390-dark-current保存在同一证据目录。3018独立预览及该标签页作为可查看结果保留，浏览器临时尺寸恢复；用户3017和主checkout未覆盖。

## 2026-10-02 服务地址表单与首启响应式

上一目标回合有实际progress：语言同步及资料刷新已提交。本轮继续interface-state worktree，fetch/rebase到最新origin/develop349e2f08；前三个已集成提交由Git跳过，上轮提交重放为1e0f50cc，主checkout与用户3017保持。

两处/health探测收敛到useServerConnection：AbortController与同步请求ref拒绝重复提交，取消、卸载、15秒超时使请求失效；即使fetch忽略abort，迟到成功也不能写地址或reload，旧finally不影响新请求。设置页原来取消只收起表单、首启离开后仍能保存；7项回归先全部RED，再GREEN。表单使用原生submit、具名输入/错误描述、IME Enter保护，设置内Escape局部取消回修改按钮；等待冻结输入并聚焦稳定form，取消仍可用。首启复用Button/Input和theme token，去掉厚卡片、模糊及大阴影，按标题/说明/字段/操作分层；手机44px、输入16px，现有五语文案，无新动效或依赖。

独立复核发现探测失败会抢走用户已移到其他设置的焦点，追加真实外部button+deferred响应测试先RED，加入有效焦点归属判断后GREEN；首启同样保护外部焦点。等待表单移除原生整块outline，交互控件焦点环保留。320×300俄语实际暴露全局body/root overflow:hidden裁掉Connect：将首启改为定高dvh独立滚动和intrinsic表单自动边距；Tab到Connect后scrollTop119、buttonBottom267.7，按钮可见且overflow0。最终复核无确定P1/P2。

隔离3019独立fixture入口渲染实际组件，不注入Tauri/Capacitor桥；健康探测仅2秒后503，绝不转发真实服务或模拟成功保存。390深色Enter等待form aria-busy=true、焦点FORM、input/Connect禁用，输入及按钮44px；失败保留地址并回输入，Escape取消回修改。320浅色俄语等待控件44px、无整块焦点框及横向溢出，短屏滚动如上；834浅色俄语错误完整可读，1440暖色表单448px、overflow0；390深色中文最终错误与连接可读。截图仓库外interface-quality：server-settings-390-dark-error-final、server-setup-320-light-ru-loading-final、server-setup-320-short-ru-focus-final、server-setup-834-light-ru-error-final、server-setup-1440-sepia-final、server-setup-390-dark-error-final。此为响应式组件/键盘证据，不证明原生软键盘、实际换服登录或真实云端网络。

八项人工自检：沿用serif标题及正文尺度、字段留白；平面层级突出内容与连接反馈；全部theme token及现有五语；无新增动画，既有spinner/reduced-motion；取消/超时/重试/IME/焦点经行为测试；320/390/834/1440和300px短屏实测；复用LambChat控件并保持克制视觉。按DESIGN.md交付检查，Impeccable环境沿用人工清单。最终17项针对性、全量783文件/3860项测试通过，lint零警告零错误，build含tsc/Vite/PWA通过；eager JS560133/561152、precache5029787/5242880、93项，未提高预算。git diff --check通过。

本轮3019服务和临时标签页回收，视口恢复；上轮3018结果及用户3017保留。全站目标继续：本地沙箱设置/数据位置读取失败、保存恢复和窄屏操作布局，剩余异步归属及状态组合、真实服务和设备证据尚未完成，不据本批门禁宣告全站完成。

## 2026-10-02 沙箱数据位置错误恢复与响应式

上一回合核对了用户3017文件预览：原生CodeMirror查找已浮动、展开/关闭正文位置不变，17项相关测试通过，没有重复实现。此次继续interface-state worktree，fetch确认origin/develop仍为349e2f08，主checkout和用户3017保持。

数据位置读取、目录选择、保存、恢复默认、重启复用usePreferenceWrites与CatalogStatus。读取失败保留标题和重试；保存失败保留所选目录、迁移选择和原生错误原因；保存期间冻结checkbox与Cancel，稳定section承接本区焦点，卸载忽略迟到成功toast。新增discard仅清失败请求，拒绝清在途请求；取消或改迁移选择清旧快照，新操作启动前清另一个失败槽，避免picker与reset的旧Retry交叉执行。7项恢复回归先RED再GREEN；交叉reset→picker回归先RED，修复并补反向deferred覆盖。独立复核交叉P2已关闭，增量无确定P1/P2。

追到实际Rust响应，SandboxDataLocation没有camelCase serde重命名，原来的桥却直接断言overrideConfigured，导致真实壳“恢复默认”消失。替换不真实的既有fixture为override_configured原生格式，true/false两项先RED，再在共享服务桥显式映射后GREEN；没有改Rust命令、迁移或覆盖文件语义。

布局改为标题/状态、完整根路径、说明、所选路径、迁移选择和操作顺序，去掉重复嵌套卡片及独立硬编码深色。复用Button和主题token，当前卡片以sandbox-data容器宽度控制44px触控，长标签允许换行；原生checkbox保持具名语义且整行可点。没有新增文案、字体、依赖或动画。

3019独立fixture渲染真实组件，仅预览服务器替换此组件的native服务与process插件；所有操作等待1.2秒、指定首次失败后恢复，不调用原生桥、不访问或迁移文件、不重启应用。320浅色俄语读取错误可读、Retry44px、重试焦点DIV、等待aria-busy=true；恢复后的长路径和目录确认无横向溢出，两个按钮44px。390深色保存等待checkbox/Cancel/Save禁用、焦点DIV；错误保留所选目录并显示持久alert，Retry后展示“已保存/需重启”。834深色恢复布局宽576px、overflow0；1440暖色俄语reset失败可重试，恢复后完整说明数据留在原处。320×300暖色俄语Tab可达重启按钮，底边283.77px在300px视口内、overflow0。390浅色relaunch失败保留已保存状态，Retry仅重启、恢复启用。截图保存仓库外interface-quality：sandbox-location-320-light-ru-read-error-final、sandbox-location-320-light-ru-confirm-final、sandbox-location-390-dark-save-error-final、sandbox-location-390-dark-saved-final、sandbox-location-1440-sepia-ru-reset-error-final、sandbox-location-1440-sepia-ru-reset-recovered-final、sandbox-location-320-short-ru-reset-final、sandbox-location-390-light-relaunch-error-final；优化前证据sandbox-location-320-dark-before。

按DESIGN.md八项人工检查：沿用标题/正文尺度，保留分组留白；完整路径、迁移决策、错误与完成状态层级明确；现有深浅/暖色token；无新动效、已有spinner遵循reduced-motion；禁用、重试、键盘焦点与卸载经行为验证；320/390/834/1440及俄语短屏实测；复用LambChat组件，不引入并行视觉系统。Impeccable检查器未安装，使用项目交付清单。最终全量783文件/3869项测试、lint零警告零错误、build含tsc/Vite/PWA通过；eager JS560212/561152、precache5030472/5242880、93项，未提高预算。git diff --check通过。

另外以8019独立临时后端运行uv本地沙箱全量E2E，44/44 PASS，MongoDB/Redis使用本机既有服务，一次性用户与测试目录由脚本回收。临时.env symlink及8019后端已回收，未发布配置或凭据。此E2E证明现有本地daemon执行、传输、skills虚拟挂载、转移整树与下线链路，不证明Tauri数据根真实迁移或实际重启。3019及临时走查标签页回收，视口恢复；3018已交付预览及用户3017保留。

全站目标仍进行中。下一阶段继续LocalSandboxSection配对表单、四列快捷按钮在手机/长语言的布局、状态读取错误被当离线，以及原生数据位置在关闭重开设置/多实例/迁移在途时的状态与待重启提示持久性；还需真实原生窗口、目录迁移和设备证据。不得将本批门禁或fixture视为全部界面完成。

## 2026-10-02 本地沙箱状态、配对表单与窄屏控制

上一目标回合提供了新证据：直接核对用户3017文件查找，确认现有CodeMirror原生浮层不占正文行、320/390px可用，17项测试通过；没有重复实现。此次继续interface-state，当前HEAD为1d1a0a7d，已fetch确认origin/develop仍349e2f08，主checkout、mobile-density及用户3017保持。

LocalSandboxSection将网页状态错误与离线引导分开，原生进程读取失败保留CatalogStatus及重试，不再冒充“已停止”并开放配对。初始/重试加载有具名role=status。读取代次拒绝晚到旧响应覆盖原生推送事件；订阅拒绝回退10秒轮询，卸载后的迟到null不再创建轮询计时器。两种配对共用同步ref锁和loading方法状态，等待冻结两条入口及用户名/密码；具名FormField/Input保持autocomplete，所属焦点移到稳定form。现有无副作用登录、PAT铸造、保存/重启与策略流程未改，无新增文案或依赖。

复用Button及现有token，快捷按钮按容器宽度由四列变两列，长标签自然换行，移动/粗指针44px，输入16px。320俄语实测确认策略值截断，增加小于400px容器的标签/完整宽选择器纵向布局，选择器同样44px。语义与状态新增9项先RED后GREEN，最终本文件23项通过。独立只读复核含增量未发现确定P1/P2。

独立/sandbox-data-preview以shell=unpaired|paired|web渲染真实设置组件，failure=process|status检查读取错误；原生配对、PAT、重启、取消配对和目录打开均等待后拒绝执行，不访问真实桥或凭据。状态替身限定该独立入口，常规面板保留实际useSandboxStatus全局hook及HTTP GET fixture。短屏检查发现仅scripts内使用的h-dvh未被Tailwind扫描，明确inline height100dvh；修复后main.clientHeight300、main.scrollTop455、root.scrollTop0，密码字段底边253.8可见，横向overflow0。此为预览容器校正，不是生产布局改动。

浏览器证据：320深色俄语快捷按钮140px宽、70/50px高，策略当前值完整显示、overflow0；390深色配对输入44px/16px，当前账号配对等待form aria-busy=true、焦点FORM，两个按钮和字段全部disabled；320浅色俄语进程读取错误保留Retry并隐藏配对，Retry后加载和section焦点稳定；390深色网页503仅显示错误/Retry，无安装引导，恢复后才显示离线下载；1440浅色俄语宽宿主720px，快捷按钮四列各174px、overflow0。截图保存在仓库外interface-quality：local-sandbox-320-dark-ru-final、local-sandbox-390-dark-pair-form-final、local-sandbox-320-light-ru-process-error-final、local-sandbox-320-short-light-ru-focus-final、local-sandbox-390-dark-web-status-error-final、local-sandbox-1440-light-ru-final。预览不证明真实PAT持久化、登录、进程操作或真机软键盘。上一批44项本地沙箱E2E记录仍是原链路基线，本批未更改该传输/daemon协议，不将旧结果称为此次新验证。

八项按DESIGN.md人工自检：沿用标题/字段字体；保持分组留白、不压缩整页；加载/在线/错误/配对/快捷操作分层；深浅暖色token及既有五语；无新动效、spinner遵循reduced-motion；同步互锁/重试/语义/焦点/卸载经行为测试；320/390/834/1440及300px短屏实测；复用LambChat组件和容器规则，无并行设计体系。Impeccable未安装，使用项目清单。最终全量783文件/3878测试通过，lint零错误零警告，build含tsc/Vite/PWA通过；eager JS560198/561152 bytes、precache5031495/5242880 bytes、93项，未提高预算。

全站目标继续。尚需配对后保存/重启部分失败时的准确恢复、策略写入失败的选择/反馈、重启/取消配对在途操作互锁与旧账号/卸载响应归属；数据位置关闭重开/多实例/迁移在途及待重启提示持久性、真实Tauri目录迁移和设备证据也未完成。不得将本批门禁与fixture视为全部界面完成。

最终834暖色检查无alert、无横向溢出，四列按钮174px；新增local-sandbox-834-sepia-final截图。已回收本轮3019服务和临时标签页，视口恢复；已有3018结果标签继续保留，用户3017与主checkout未覆盖。下一轮也要检查原生进程可读但服务端status失败时的提示与策略就绪，不据进程running断言服务连接已成功。

## 2026-10-02 原生操作分步恢复与配对反馈收敛

上一回合核对用户指定的文件原生查找，17项相关测试及390px布局/命中/焦点实测提供新证据，分类为progress。本轮继续interface-state现场，HTTPS fetch确认origin/develop仍为349e2f08且是HEAD祖先；主checkout、mobile-density与用户3017保持。接续此前未提交的原生操作修复，没有重新开始全站工作。

LocalSandboxSection复用usePreferenceWrites统一配对、策略、重启和取消配对互锁及持久错误/Retry。配对请求闭包保留PAT回执与已保存步骤：原生保存失败重用同一回执，保存成功后重启失败只重试启动，不再重复生成PAT或错误归咎账号密码。回执确认后隐藏已不能修改的凭据表单，仅其仍拥有焦点时转到稳定section；等待/错误保留紧凑CatalogStatus。新增准确“已保存，重启即可完成”文案同步五语。策略保留失败选择，重试跳过已确认的服务端/本机写入；取消配对清理失败重试不重复吊销。卸载在后续步骤之前失效，迟到成功/错误不继续原生写入或通知。

独立复核发现策略失败后Restart会覆盖原请求并清除错误，但保留未保存选择。新增交叉操作先RED后GREEN，Restart此时复用未完成策略请求。实屏又发现portalled Select选项在onChange之后回焦trigger，抢掉caller焦点后trigger禁用导致BODY焦点；一项集成先RED（35pass/1fail），共享Select仅将回焦移到onChange之前，caller可按归属接住焦点。复核包括SelectRow、直接Select与包装调用，无新确定P1/P2。最终本文件36项，含shared Select针对性42项全部通过。

预览新增显式native-flow=1，仅本独立入口用公开占位符与内存状态模拟步骤首次失败/重试成功；默认操作仍拒绝执行，目录打开始终拒绝。账号内容不解析、存储或转发，不使用真实PAT、原生桥、文件写入或API写入。指南更新边界；fixture只证明UI和恢复路径，不证明实际登录、凭据落盘、服务端保存或原生进程重启。

浏览器最终证据：390深色配对重启失败收起表单，准确说明与44px Retry保留，section焦点稳定、overflow0，Retry后在线/运行控制恢复；320深色俄语策略首次失败保留commands，点Restart显示原策略等待、所有相邻原生操作冻结、焦点section，完成后commands与正常控件恢复；320×300短屏main独立滚动至426，焦点日志按钮top125.4/bottom175.4、宽140/高50可见，overflow0；390浅色取消配对失败保留Retry，重试等待冻结Restart，完成后未配对表单恢复；1440浅色俄语四列各174×50，834暖色无alert，均overflow0。最终截图在仓库外interface-quality目录，文件名local-sandbox-actions-390-dark-pair-restart-error-final、320-dark-ru-policy-error-final、320-dark-ru-policy-recovered-final、320-short-ru-focus-final、390-light-unpair-error-final、1440-light-ru-final、834-sepia-ru-final。

八项按DESIGN.md人工自检：复用既有文字尺度、按钮及分组留白；以状态/说明/行动分层，避免重复表单和闲置反馈空行；颜色沿用theme token且三主题实测；无新增装饰动效，已有reduced-motion保留；互锁、逐步Retry、焦点、卸载用行为测试和实屏核对；320/390/834/1440及300px短屏实际验证；复用LambChat视觉语言、没有额外依赖或并行设计系统。pnpm exec impeccable确认命令不可用，使用项目清单等价人工检查。最终全量783文件/3891测试通过，lint零错误零警告，build含tsc/Vite/PWA通过；eager JS560328/561152 bytes、precache5031924/5242880 bytes、93项，未提高预算。

全站目标继续。下一步需服务端status失败但进程可读时的明确反馈、数据位置与原生操作的跨区互锁、数据位置关闭重开/多实例/待重启持久性、账号切换时在途操作归属、目录打开迟到错误，以及真实Tauri和手机设备验证。PAT创建响应失败的服务端幂等性也不由本UI改动证明；不将fixture或局部门禁宣告为全部界面完成。

最终桌面/平板截图重新等待数据位置读取完成再保存；回收本轮3019服务及临时标签，浏览器尺寸恢复，既有3018结果标签保留。仅停止经过PID和cwd核对的本轮preview进程，用户3017保持。
