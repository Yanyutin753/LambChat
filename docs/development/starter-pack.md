# 默认技能包与助手角色

LambChat 自带研究、写作、文档、表格、演示、编程六类基础技能。普通注册、OAuth 注册和管理员创建用户共用 `UserStorage.create` 安装入口。已有用户在读取个人信息（`/api/auth/me`）、首次列出技能、使用角色或加载聊天技能时补齐，无需批量迁移用户数据。

技能内容位于 `src/infra/onboarding/skills/`，角色与五语名称、说明、开场示例位于 `src/infra/onboarding/catalog.json`。服务启动时发布六个全局公开角色，用户可以复制为自己的角色。研究、写作等角色绑定配套技能，支持交付文档文件。

每份技能是用户自己的可编辑副本，沿用现有技能列表、禁用、文件读取与执行机制。已完成的技能名称记录在用户 `metadata.starter_skills`；重复调用不覆盖内容，删除后不重新安装。同名自定义技能保留，禁用状态也保留。中断安装通过技能元数据中的 `starter_pack` 标记恢复，逐文件仅插入缺失内容。安装失败记录日志，不让已创建的账号返回注册失败；下次读取个人信息或加载聊天技能会重试。

全局角色使用固定 ObjectId 和仅插入的 upsert，支持多个服务进程同时启动，并保留管理员修改。管理员若希望隐藏默认角色，可将角色归档；删除默认角色会在服务下次启动时重新建立。默认名称、说明及开场示例支持 zh / en / ja / ko / ru，列表及角色使用接口按 `Accept-Language` 返回未修改的默认标签。

文档技能附带简单 DOCX / PDF 生成脚本；表格和演示技能附带 XLSX / PPTX 生成脚本。DOCX 使用 Python 标准库，PDF、XLSX、PPTX 分别需要执行沙箱里的 reportlab、openpyxl、python-pptx。技能包含依赖检查及沙箱内隔离运行指引，服务端安装包不意味着执行沙箱已有同一套依赖。`/skills/` 可能是虚拟路径，需通过现有文件工具读取并复制到执行路径。高级排版、PDF 字体、渲染预览依赖具体沙箱的工具条件，不能仅以文件存在声称视觉验证通过。

已初始化的技能不会自动跟随服务器升级，以免覆盖用户编辑；新增技能名会在后续初始化时补齐。`ENABLE_SKILLS=false` 时不安装技能。

验证：

```bash
uv run pytest tests/infra/onboarding tests/persona_preset tests/infra/skill -q
make lint
make typecheck
```
