# 沙箱就绪 ID 布局设计

## 目标

沙箱进入 `ready` 状态且存在 `sandboxId` 时，在“沙箱已就绪”文字后直接显示 `ID: {sandboxId}`，让用户无需展开即可看到沙箱 ID。

## 界面行为

- 顶部状态胶囊使用 `CollapsiblePill` 已有的 `suffix` 插槽显示沙箱 ID，顺序为状态文字、ID、展开箭头。
- 展开详情继续保留现有的沙箱 ID 和用时信息，不改变用户当前可查看的内容。
- `sandboxId` 缺失时不显示 ID 后缀，现有启动、错误和取消状态保持不变。
- ID 后缀使用等宽字体并允许截断，避免长 ID 撑破消息区域。

## 实现范围

仅调整 `SandboxItem` 的渲染，不修改事件结构、翻译键或 `CollapsiblePill` 的公共接口。

## 测试

先增加一个失败的前端回归测试，验证 `SandboxItem` 将本地化后的沙箱 ID 传入 `CollapsiblePill.suffix`，同时仍在展开详情中渲染 ID；随后完成最小实现并运行相关 Vitest 测试。
