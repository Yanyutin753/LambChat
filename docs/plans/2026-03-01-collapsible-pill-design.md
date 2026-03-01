# CollapsiblePill 公共组件设计

## 概述

从 ChatMessage.tsx 中提取公共的 "pill + 展开" 模式，创建可复用的 `CollapsiblePill` 组件。

## 涉及组件

| 组件 | 当前位置 | 改造方式 |
|------|----------|----------|
| ThinkingBlock | ChatMessage.tsx | 使用 CollapsiblePill |
| ToolCallItem | ChatMessage.tsx | 使用 CollapsiblePill |
| SubagentToolItem | ChatMessage.tsx | 使用 CollapsiblePill |
| Sandbox (内联) | ChatMessage.tsx | 提取为独立组件 + CollapsiblePill |
| SubagentBlock | ChatMessage.tsx | **不改造**，保持卡片设计 |

## 组件接口

```tsx
interface CollapsiblePillProps {
  // 状态
  status?: 'idle' | 'loading' | 'success' | 'error';

  // 图标和标签
  icon: React.ReactNode;
  iconColor?: string;
  label: string;

  // 可选的额外元素
  suffix?: React.ReactNode;

  // 交互
  defaultExpanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;

  // 样式变体
  variant?: 'default' | 'tool' | 'thinking';

  // 展开内容
  children?: React.ReactNode;

  // 是否可展开
  expandable?: boolean;
}
```

## 状态颜色映射

### variant="default" (Sandbox)
| status | 背景色 | 状态指示器 |
|--------|--------|-----------|
| loading | emerald | LoadingSpinner |
| success | emerald | CheckCircle |
| error | red | XCircle |

### variant="tool" (ToolCallItem, SubagentToolItem)
| status | 背景色 | 状态指示器 |
|--------|--------|-----------|
| loading | amber | LoadingSpinner |
| success | emerald | CheckCircle |
| error | red | XCircle |
| idle | stone | Wrench |

### variant="thinking" (ThinkingBlock)
| status | 背景色 | 状态指示器 |
|--------|--------|-----------|
| loading | stone | LoadingSpinner |
| success | stone | CheckCircle |
| error | stone | XCircle |
| idle | stone | 无 |

## 文件结构

```
frontend/src/components/common/
├── CollapsiblePill.tsx    # 新组件
├── LoadingSpinner.tsx     # 已存在
└── index.ts               # 更新导出
```

## 使用示例

### ThinkingBlock

```tsx
<CollapsiblePill
  status={isPending ? 'loading' : success ? 'success' : hasResult ? 'error' : 'idle'}
  icon={<Brain size={12} />}
  label={t("chat.message.thinking")}
  variant="thinking"
  suffix={isStreaming && <StreamingDots />}
>
  <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
    <pre className="text-xs ...">{content}</pre>
  </div>
</CollapsiblePill>
```

### ToolCallItem

```tsx
<CollapsiblePill
  status={isPending ? 'loading' : success ? 'success' : hasResult ? 'error' : 'idle'}
  icon={<Wrench size={10} />}
  label={name}
  variant="tool"
  expandable={hasArgs || hasResult}
>
  <div className="mt-2 ml-4 pl-3 border-l-2 ...">
    {/* Args 和 Result 分组框 */}
  </div>
</CollapsiblePill>
```

### SandboxItem (新提取)

```tsx
<CollapsiblePill
  status={status === 'starting' ? 'loading' : status === 'ready' ? 'success' : 'error'}
  icon={<Box size={10} />}
  label={t("chat.sandbox.name")}
  suffix={status === 'starting' && <span>{t("chat.sandbox.initializing")}</span>}
  expandable={hasDetails}
>
  <div className="mt-1 ml-4 pl-3 border-l-2 ...">
    {/* sandbox_id 或 error */}
  </div>
</CollapsiblePill>
```

## 实现要点

1. **展开动画**: 使用 `grid-rows` 实现平滑展开/收起
2. **状态指示器**: 自动根据 status 显示对应图标
3. **颜色方案**: 根据 variant 和 status 组合决定颜色
4. **可访问性**: 按钮需要有正确的 aria 属性

## 不在范围内

- SubagentBlock 的卡片式设计保持不变
- 各组件的内容区域样式保持各自风格
