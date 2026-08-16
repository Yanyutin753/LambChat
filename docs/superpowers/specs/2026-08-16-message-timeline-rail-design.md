# Message Timeline Rail — Design Spec

**Date**: 2026-08-16
**Status**: Approved

## Summary

在聊天消息区域右侧边缘添加一个极窄竖条导航（Message Timeline Rail），每个消息用线段标记表示，鼠标悬浮弹出预览卡片，点击跳转到对应消息。仅桌面端显示。

## Motivation

长对话中快速定位消息的轻量方案。现有大纲面板（ReactFlow）功能完整但较重，需要一个更轻、更直觉的快速导航方式。

## Component Architecture

```
ChatView.tsx
  └── MessageTimelineRail (新组件)
        ├── TimelineMark × N (每条消息一个标记)
        └── TimelinePreviewCard (悬浮预览卡片，createPortal 到 body)
```

## Detailed Design

### MessageTimelineRail

- **位置**: 聊天区域 `<main>` 右边缘，`position: absolute; right: 0`
- **可见性**: `hidden lg:block`（仅 ≥1024px 显示）
- **宽度**: `w-[8px]`，可视竖条 `w-[4px]` 居中
- **竖条背景**: `bg-theme-border/30 rounded-full`

**线段标记 (TimelineMark)**:
- 每条消息均匀分布在竖条高度上
- **用户消息**: 1 根线，`h-[3px] w-[7px]`，`rounded-full`，`bg-[var(--theme-primary)]`
- **助手消息**: 3 根细线，各 `h-[1px] w-[5px]`，间距 `gap-[2px]`，`bg-theme-text-tertiary`
- 非可见区域标记 `opacity-30`，可见区域标记 `opacity-70`
- hover 状态: `opacity-100` + 轻微 `scale-x` 放大
- hover 时在左侧弹出预览卡片

**跳转行为**:
- 点击标记 → `virtuosoRef.current?.scrollToIndex({ index: messageIndex, behavior: "smooth" })`
- 跳转后对目标消息设置 `data-external-navigation-highlighted=true`（1600ms 高亮动画）
- 复用 `useMessageScroll.externalNavigation.ts` 中的 `highlightElementForExternalNavigation`

### TimelinePreviewCard

- 使用 `createPortal` 渲染到 `document.body`
- 定位: 标记左侧，`right: (chatArea.right - mark.left)px`
- 使用 `useStickyDropdownPosition` 或固定偏移

**内容**:
- **用户消息**: 1 行摘要，`text-sm font-medium`，`truncate`
- **助手消息**: 最多 3 行摘要，`text-xs text-theme-text-secondary`，`line-clamp-3`
- 底部: 消息序号标签（`#3`），`text-[10px] text-theme-text-tertiary`

**样式**:
- 复用现有卡片样式: `bg-theme-bg-card border border-theme-border shadow-lg rounded-lg`
- 宽度: `w-[240px]`，`p-3`

### Data Flow

```
messages[]
  → extractMessageOutline() (已有)
  → MessageTimelineRail
      → outlineItems.map → TimelineMark
      → visibleRange (Virtuoso rangeChanged) → 更新高亮
      → hover → TimelinePreviewCard
      → click → scrollToIndex + highlight
```

### 复用已有基础设施

| 已有模块 | 用途 |
|----------|------|
| `extractMessageOutline()` | 提取消息摘要和锚点 ID |
| `createMessageAnchorId()` | 消息 DOM 锚点 |
| Virtuoso `rangeChanged` | 可见范围追踪 |
| `virtuosoRef.scrollToIndex()` | 跳转到消息 |
| `highlightElementForExternalNavigation` | 跳转后高亮动画 |
| `createPortal` + click-outside pattern | 预览卡片渲染 |

## File Changes

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `AppContent/ChatView.tsx` | 修改 | 在 `<main>` 内添加 `<MessageTimelineRail />` |
| `AppContent/MessageTimelineRail.tsx` | **新建** | 竖条主组件 |
| `AppContent/TimelinePreviewCard.tsx` | **新建** | 预览卡片组件 |
| `messageOutline.ts` | 无变更 | 复用 |
| `useChatOutline.tsx` | 无变更 | 复用 |
| i18n (en.json, zh.json) | 修改 | 添加 `chat.timelineRail` 相关键（如需要） |

## Non-Goals

- 不替代现有大纲面板（ReactFlow），两者并存
- 不在移动端/平板端显示
- 不引入新依赖
- 不做 minimap 式等比例映射（虚拟列表下高度不可预测）
- 不在竖条上显示 heading 级别的标记（仅 user-message 和 assistant-message）

## Testing

- 组件渲染测试: 正确数量和类型的标记
- 交互测试: hover 显示预览卡片，点击触发跳转
- 可见性测试: 可见区域标记高亮，非可见区域标记半透明
- 响应式测试: lg 以下不显示
