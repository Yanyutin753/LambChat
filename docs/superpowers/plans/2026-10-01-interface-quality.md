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
