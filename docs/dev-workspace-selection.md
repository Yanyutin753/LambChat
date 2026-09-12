# 桌面会话工作目录

桌面开发客户端选中“本地电脑”，且执行机器为当前机器并在线时，输入框上方显示工作目录入口。选择系统文件夹后，目录绑定保存在会话的 `agent_options.sandbox_workspace` 中，同时固定 `sandbox_machine_id`。后续消息及重新打开会话继续使用该目录；新会话恢复默认。执行期间不能更换目录，清除按钮恢复默认会话工作区。

网页和其他机器不显示原生目录入口。切换机器后，原机器的目录绑定不会用于新机器。

## 原生命令

`sandbox_pick_workspace(title: string)` 打开原生文件夹选择器，返回 `{id, machineId, path}`，取消时返回 `null`。权限为 `allow-sandbox-pick-workspace`。命令只接受对话框标题，不接受服务端传来的文件路径。

本机在配置的 `data_root/.selected/<id>.json` 中保存真实路径，服务端仅使用机器绑定的标识，将虚拟工作目录设为 `/workspace/.selected/<id>`。daemon 将命令和结构化文件操作统一映射到选择目录。目录失效时明确报错，不自动创建替代目录。

协议保持向后兼容：默认工作区不变；旧 daemon 不接受带子路径的新虚拟目录，会拒绝执行，因此此功能需使用包含本次变更的桌面壳和 daemon。没有更改认证、执行确认策略或传输帧。

## 本地验证

```bash
uv run pytest tests/client/test_selected_workspace.py tests/infra/backend/test_workspace_selection.py
uv run python scripts/e2e_local_sandbox.py
cd frontend && pnpm test && pnpm run lint && pnpm run build
cd src-tauri && cargo test --lib
```
