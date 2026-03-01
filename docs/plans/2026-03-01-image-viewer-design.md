# ImageViewer 组件设计

## 概述

创建一个全局可复用的全屏图片预览组件，支持放大、缩小、旋转和重置功能。

## 需求

- 点击图片后打开全屏预览
- 支持放大/缩小（滚轮 + 按钮）
- 支持左右旋转（每次90°）
- 支持重置到初始状态
- 放大后支持拖拽移动
- 全局可用（DocumentPreview、ChatMessage 等处）

## 组件结构

```
frontend/src/components/common/ImageViewer/
├── index.ts          # 导出入口
└── ImageViewer.tsx   # 主组件
```

## Props 接口

```typescript
interface ImageViewerProps {
  src: string;           // 图片地址
  alt?: string;          // 图片描述
  isOpen: boolean;       // 是否显示
  onClose: () => void;   // 关闭回调
}
```

## 功能设计

| 功能 | 交互方式 |
|------|----------|
| 放大 | 滚轮向上 / 点击放大按钮 |
| 缩小 | 滚轮向下 / 点击缩小按钮 |
| 旋转 | 点击左旋/右旋按钮 (每次90°) |
| 重置 | 点击重置按钮 |
| 关闭 | ESC键 / 点击背景 / 点击关闭按钮 |
| 拖拽 | 放大后可拖拽移动图片 |

## UI 布局

```
┌──────────────────────────────────────────┐
│  [X 关闭]              [旋转] [缩放] [重置] │  ← 工具栏
├──────────────────────────────────────────┤
│                                          │
│              [图片居中显示]                 │  ← 主区域
│                                          │
├──────────────────────────────────────────┤
│  按 ESC 关闭                              │  ← 底部提示
└──────────────────────────────────────────┘
```

## 技术实现

- 使用 `createPortal` 渲染到 `document.body`
- 使用 CSS `transform` 实现缩放和旋转
- 使用 CSS `cursor: grab/grabbing` 指示拖拽状态
- 使用 `wheel` 事件处理滚轮缩放
- 缩放范围：0.1x - 5x
- 每次缩放步进：0.25x

## 使用示例

```tsx
import { ImageViewer } from "@/components/common/ImageViewer";

function SomeComponent() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <img src="..." onClick={() => setIsOpen(true)} />
      <ImageViewer
        src="..."
        alt="Preview"
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
      />
    </>
  );
}
```

## 集成点

1. **DocumentPreview.tsx** - 图片预览区域点击时打开
2. **ChatMessage.tsx** - 聊天中的图片附件点击时打开
3. **AttachmentPreview.tsx** - 附件预览中的图片点击时打开
