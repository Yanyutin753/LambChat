# ImageViewer 组件实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建一个全局可复用的全屏图片预览组件，支持放大、缩小、旋转和重置功能。

**Architecture:** 创建独立的 `ImageViewer` 组件，使用 `createPortal` 渲染到 `document.body`。组件管理自身的缩放、旋转、拖拽状态，通过 props 控制显示/隐藏。

**Tech Stack:** React 19, TypeScript, Tailwind CSS, lucide-react, react-i18next

---

## Task 1: 创建 ImageViewer 组件

**Files:**
- Create: `frontend/src/components/common/ImageViewer.tsx`
- Create: `frontend/src/components/common/ImageViewer/index.ts` (re-export)

**Step 1: 创建 ImageViewer 组件**

```tsx
import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  X,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  RotateCw,
  Maximize2,
} from "lucide-react";

interface ImageViewerProps {
  src: string;
  alt?: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ImageViewer({ src, alt, isOpen, onClose }: ImageViewerProps) {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const imageRef = useRef<HTMLImageElement>(null);

  // 缩放范围: 0.1x - 5x
  const MIN_SCALE = 0.1;
  const MAX_SCALE = 5;
  const SCALE_STEP = 0.25;

  // 重置状态
  const resetState = useCallback(() => {
    setScale(1);
    setRotation(0);
    setPosition({ x: 0, y: 0 });
    setIsDragging(false);
  }, []);

  // 关闭时重置
  useEffect(() => {
    if (!isOpen) {
      resetState();
    }
  }, [isOpen, resetState]);

  // ESC 关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // 锁定 body 滚动
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // 滚轮缩放
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -SCALE_STEP : SCALE_STEP;
    setScale((prev) => Math.max(MIN_SCALE, Math.min(MAX_SCALE, prev + delta)));
  }, []);

  // 放大
  const handleZoomIn = useCallback(() => {
    setScale((prev) => Math.min(MAX_SCALE, prev + SCALE_STEP));
  }, []);

  // 缩小
  const handleZoomOut = useCallback(() => {
    setScale((prev) => Math.max(MIN_SCALE, prev - SCALE_STEP));
  }, []);

  // 左旋
  const handleRotateLeft = useCallback(() => {
    setRotation((prev) => prev - 90);
  }, []);

  // 右旋
  const handleRotateRight = useCallback(() => {
    setRotation((prev) => prev + 90);
  }, []);

  // 拖拽开始
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (scale > 1) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    }
  }, [scale, position]);

  // 拖拽移动
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  }, [isDragging, dragStart]);

  // 拖拽结束
  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex flex-col items-center justify-center bg-black/90"
      onClick={onClose}
      onWheel={handleWheel}
    >
      {/* 工具栏 */}
      <div
        className="absolute top-4 left-4 right-4 flex items-center justify-between z-10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 关闭按钮 */}
        <button
          type="button"
          onClick={onClose}
          className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
          title={t("common.close")}
        >
          <X size={20} className="text-white" />
        </button>

        {/* 操作按钮组 */}
        <div className="flex items-center gap-2">
          {/* 左旋 */}
          <button
            type="button"
            onClick={handleRotateLeft}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            title={t("imageViewer.rotateLeft")}
          >
            <RotateCcw size={20} className="text-white" />
          </button>

          {/* 右旋 */}
          <button
            type="button"
            onClick={handleRotateRight}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            title={t("imageViewer.rotateRight")}
          >
            <RotateCw size={20} className="text-white" />
          </button>

          {/* 缩小 */}
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={scale <= MIN_SCALE}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={t("imageViewer.zoomOut")}
          >
            <ZoomOut size={20} className="text-white" />
          </button>

          {/* 缩放比例 */}
          <span className="text-white text-sm font-medium px-2 min-w-[60px] text-center">
            {Math.round(scale * 100)}%
          </span>

          {/* 放大 */}
          <button
            type="button"
            onClick={handleZoomIn}
            disabled={scale >= MAX_SCALE}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={t("imageViewer.zoomIn")}
          >
            <ZoomIn size={20} className="text-white" />
          </button>

          {/* 重置 */}
          <button
            type="button"
            onClick={resetState}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            title={t("imageViewer.reset")}
          >
            <Maximize2 size={20} className="text-white" />
          </button>
        </div>
      </div>

      {/* 图片区域 */}
      <div className="flex-1 flex items-center justify-center w-full overflow-hidden">
        <img
          ref={imageRef}
          src={src}
          alt={alt || ""}
          className="select-none transition-transform duration-100"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
            cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
            maxHeight: "90vh",
            maxWidth: "90vw",
          }}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          draggable={false}
        />
      </div>

      {/* 底部提示 */}
      <div className="absolute bottom-4 left-0 right-0 text-center">
        <span className="text-white/60 text-sm">
          {t("imageViewer.hint")}
        </span>
      </div>
    </div>,
    document.body,
  );
}
```

**Step 2: 创建导出入口**

创建 `frontend/src/components/common/ImageViewer/index.ts`:

```ts
export { ImageViewer } from "./ImageViewer";
export type { ImageViewerProps } from "./ImageViewer";
```

**Step 3: 更新 common/index.ts 导出**

在 `frontend/src/components/common/index.ts` 添加:

```ts
export { ImageViewer } from "./ImageViewer";
export type { ImageViewerProps } from "./ImageViewer";
```

---

## Task 2: 添加国际化翻译

**Files:**
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`

**Step 1: 添加中文翻译**

在 `zh.json` 的 `common` 部分之后添加 `imageViewer` 部分:

```json
{
  ...,
  "imageViewer": {
    "zoomIn": "放大",
    "zoomOut": "缩小",
    "rotateLeft": "向左旋转",
    "rotateRight": "向右旋转",
    "reset": "重置",
    "hint": "滚轮缩放 · 拖拽移动 · ESC 关闭"
  },
  ...
}
```

**Step 2: 添加英文翻译**

在 `en.json` 添加:

```json
{
  ...,
  "imageViewer": {
    "zoomIn": "Zoom In",
    "zoomOut": "Zoom Out",
    "rotateLeft": "Rotate Left",
    "rotateRight": "Rotate Right",
    "reset": "Reset",
    "hint": "Scroll to zoom · Drag to move · ESC to close"
  },
  ...
}
```

**Step 3: 添加日文翻译**

在 `ja.json` 添加:

```json
{
  ...,
  "imageViewer": {
    "zoomIn": "拡大",
    "zoomOut": "縮小",
    "rotateLeft": "左に回転",
    "rotateRight": "右に回転",
    "reset": "リセット",
    "hint": "スクロールでズーム · ドラッグで移動 · ESCで閉じる"
  },
  ...
}
```

**Step 4: 添加韩文翻译**

在 `ko.json` 添加:

```json
{
  ...,
  "imageViewer": {
    "zoomIn": "확대",
    "zoomOut": "축소",
    "rotateLeft": "왼쪽 회전",
    "rotateRight": "오른쪽 회전",
    "reset": "재설정",
    "hint": "스크롤로 확대 · 드래그로 이동 · ESC로 닫기"
  },
  ...
}
```

---

## Task 3: 集成到 DocumentPreview

**Files:**
- Modify: `frontend/src/components/documents/DocumentPreview.tsx`

**Step 1: 导入 ImageViewer**

在文件顶部添加导入:

```tsx
import { ImageViewer } from "../common/ImageViewer";
```

**Step 2: 添加状态**

在组件内部添加状态:

```tsx
const [showImageViewer, setShowImageViewer] = useState(false);
```

**Step 3: 修改图片区域**

替换第 538-550 行的图片渲染代码:

```tsx
) : (imageFile || imageUrl) ? (
  <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 min-h-[200px] overflow-auto">
    <img
      src={imageUrl || `data:image/${ext};base64,${data?.content}`}
      alt={fileName}
      className={`rounded-lg shadow-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${
        isFullscreen
          ? "max-w-full max-h-full"
          : "max-w-full max-h-[50vh] sm:max-h-[60vh]"
      }`}
      onClick={(e) => {
        e.stopPropagation();
        setShowImageViewer(true);
      }}
    />
    <ImageViewer
      src={imageUrl || `data:image/${ext};base64,${data?.content}`}
      alt={fileName}
      isOpen={showImageViewer}
      onClose={() => setShowImageViewer(false)}
    />
  </div>
```

---

## Task 4: 集成到 ChatMessage

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx`

**Step 1: 导入 ImageViewer**

在文件顶部添加导入:

```tsx
import { ImageViewer } from "../common/ImageViewer";
```

**Step 2: 添加图片预览状态**

在组件内部添加状态:

```tsx
const [imagePreview, setImagePreview] = useState<{ src: string; alt: string } | null>(null);
```

**Step 3: 找到图片附件渲染位置，添加点击事件**

需要找到渲染图片附件的代码，添加点击打开 ImageViewer 的逻辑。

---

## Task 5: 提交代码

**Step 1: 验证功能**

运行开发服务器:

```bash
cd frontend && npm run dev
```

验证:
1. 点击 DocumentPreview 中的图片能打开全屏预览
2. 滚轮缩放正常
3. 旋转按钮正常
4. 重置按钮正常
5. ESC 关闭正常
6. 点击背景关闭正常

**Step 2: 提交**

```bash
git add frontend/src/components/common/ImageViewer.tsx frontend/src/components/common/ImageViewer/index.ts frontend/src/components/common/index.ts frontend/src/i18n/locales/*.json frontend/src/components/documents/DocumentPreview.tsx frontend/src/components/chat/ChatMessage.tsx
git commit -m "feat: add ImageViewer component with zoom, rotate, and reset"
```

---

## 集成点总结

| 位置 | 文件 | 触发方式 |
|------|------|----------|
| DocumentPreview | `DocumentPreview.tsx` | 点击图片 |
| ChatMessage | `ChatMessage.tsx` | 点击图片附件 |
| AttachmentPreview | `AttachmentPreview.tsx` | (可选) 点击图片预览 |
