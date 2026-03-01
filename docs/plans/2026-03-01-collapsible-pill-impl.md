# CollapsiblePill 公共组件实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提取公共的 "pill + 展开" 模式为可复用的 CollapsiblePill 组件，并重构 ThinkingBlock、ToolCallItem、SubagentToolItem、Sandbox 四个组件使用它。

**Architecture:** 创建 CollapsiblePill 基础组件，封装状态指示器、pill 按钮、展开动画逻辑。各业务组件传入 status、icon、label 等属性，并通过 children 自定义展开内容样式。

**Tech Stack:** React, TypeScript, Tailwind CSS, clsx, lucide-react

---

## Task 1: 创建 CollapsiblePill 组件

**Files:**
- Create: `frontend/src/components/common/CollapsiblePill.tsx`
- Modify: `frontend/src/components/common/index.ts`

**Step 1: 创建 CollapsiblePill 组件**

```tsx
import { clsx } from "clsx";
import { useState } from "react";
import { CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";

export type CollapsibleStatus = "idle" | "loading" | "success" | "error";
export type CollapsibleVariant = "default" | "tool" | "thinking";

export interface CollapsiblePillProps {
  status?: CollapsibleStatus;
  icon: React.ReactNode;
  label: string;
  suffix?: React.ReactNode;
  defaultExpanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;
  variant?: CollapsibleVariant;
  children?: React.ReactNode;
  expandable?: boolean;
}

// 状态指示器组件
function StatusIndicator({
  status,
  variant,
}: {
  status: CollapsibleStatus;
  variant: CollapsibleVariant;
}) {
  if (status === "loading") {
    return <LoadingSpinner size="sm" className="shrink-0" />;
  }
  if (status === "success") {
    return <CheckCircle size={12} className="shrink-0" />;
  }
  if (status === "error") {
    return <XCircle size={12} className="shrink-0" />;
  }
  // idle 状态不显示状态指示器
  return null;
}

// 获取按钮样式
function getButtonStyles(
  status: CollapsibleStatus,
  variant: CollapsibleVariant
): string {
  if (variant === "thinking") {
    return clsx(
      "bg-stone-200 dark:bg-stone-700",
      "text-stone-600 dark:text-stone-300",
      "hover:bg-stone-300 dark:hover:bg-stone-600"
    );
  }

  if (variant === "tool") {
    if (status === "loading") {
      return clsx(
        "bg-amber-100/80 dark:bg-amber-900/30",
        "text-amber-700 dark:text-amber-300"
      );
    }
    if (status === "success") {
      return clsx(
        "bg-emerald-100/80 dark:bg-emerald-900/30",
        "text-emerald-700 dark:text-emerald-300"
      );
    }
    if (status === "error") {
      return clsx(
        "bg-red-100/80 dark:bg-red-900/30",
        "text-red-700 dark:text-red-300"
      );
    }
    return clsx(
      "bg-stone-100 dark:bg-stone-800",
      "text-stone-600 dark:text-stone-400"
    );
  }

  // default variant (for Sandbox)
  if (status === "error") {
    return clsx(
      "bg-red-100/80 dark:bg-red-900/30",
      "text-red-700 dark:text-red-300"
    );
  }
  return clsx(
    "bg-emerald-100/80 dark:bg-emerald-900/30",
    "text-emerald-700 dark:text-emerald-300"
  );
}

export function CollapsiblePill({
  status = "idle",
  icon,
  label,
  suffix,
  defaultExpanded = false,
  onExpandChange,
  variant = "default",
  children,
  expandable = true,
}: CollapsiblePillProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const hasChildren = children !== undefined;

  const handleToggle = () => {
    if (!expandable && !hasChildren) return;
    const newState = !isExpanded;
    setIsExpanded(newState);
    onExpandChange?.(newState);
  };

  const canExpand = expandable || hasChildren;

  return (
    <div className="my-1">
      <button
        onClick={handleToggle}
        className={clsx(
          "inline-flex items-center gap-1.5 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-all",
          getButtonStyles(status, variant),
          canExpand && "cursor-pointer",
          !canExpand && "cursor-default"
        )}
      >
        <StatusIndicator status={status} variant={variant} />
        {icon}
        <span className="font-mono">{label}</span>
        {suffix}
        {canExpand && (
          <ChevronRight
            size={12}
            className={clsx(
              "shrink-0 transition-transform duration-200",
              "text-stone-500 dark:text-stone-400",
              isExpanded && "rotate-90"
            )}
          />
        )}
      </button>

      <div
        className={clsx(
          "grid transition-all duration-200 ease-out",
          isExpanded && hasChildren
            ? "grid-rows-[1fr] opacity-100 mt-1"
            : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
```

**Step 2: 更新 index.ts 导出**

在 `frontend/src/components/common/index.ts` 中添加导出：

```ts
export { CollapsiblePill } from "./CollapsiblePill";
export type { CollapsiblePillProps, CollapsibleStatus, CollapsibleVariant } from "./CollapsiblePill";
```

**Step 3: 验证组件编译通过**

Run: `cd frontend && npm run build`
Expected: 无编译错误

**Step 4: Commit**

```bash
git add frontend/src/components/common/CollapsiblePill.tsx frontend/src/components/common/index.ts
git commit -m "feat(ui): add CollapsiblePill reusable component"
```

---

## Task 2: 重构 ThinkingBlock 使用 CollapsiblePill

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx:1102-1179`

**Step 1: 添加 StreamingDots 组件**

在 ThinkingBlock 之前添加一个流式动画组件：

```tsx
// 流式动画点
function StreamingDots() {
  return (
    <span className="flex items-center gap-[2px] ml-1">
      <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite]" />
      <span className="w-0.5 h-1.5 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.1s]" />
      <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.2s]" />
    </span>
  );
}
```

**Step 2: 重构 ThinkingBlock 函数**

将现有的 ThinkingBlock 函数（约 1102-1179 行）替换为：

```tsx
function ThinkingBlock({
  content,
  isStreaming,
  isPending,
  success,
  hasResult,
}: {
  content: string;
  isStreaming?: boolean;
  isPending?: boolean;
  success?: boolean;
  hasResult?: boolean;
}) {
  const { t } = useTranslation();

  const status: CollapsibleStatus = isPending
    ? "loading"
    : success
      ? "success"
      : hasResult
        ? "error"
        : "idle";

  return (
    <CollapsiblePill
      status={status}
      icon={<Brain size={12} className="shrink-0 text-stone-500 dark:text-stone-400" />}
      label={t("chat.message.thinking")}
      variant="thinking"
      suffix={isStreaming && <StreamingDots />}
    >
      <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
        <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap font-mono leading-relaxed pl-1 pt-2">
          {content}
        </pre>
      </div>
    </CollapsiblePill>
  );
}
```

**Step 3: 添加 import**

在文件顶部的 import 区域添加：

```tsx
import { CollapsiblePill, type CollapsibleStatus } from "../common/CollapsiblePill";
```

**Step 4: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 无编译错误

**Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "refactor(ui): refactor ThinkingBlock to use CollapsiblePill"
```

---

## Task 3: 重构 ToolCallItem 使用 CollapsiblePill

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx:768-860`

**Step 1: 重构 ToolCallItem 函数**

将现有的 ToolCallItem 函数（约 768-860 行）替换为：

```tsx
function ToolCallItem({
  name,
  args,
  result,
  success,
  isPending,
}: {
  name: string;
  args: Record<string, unknown>;
  result?: string;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const hasResult = result !== undefined;
  const hasArgs = Object.keys(args).length > 0;
  const canExpand = hasArgs || hasResult;

  const status: CollapsibleStatus = isPending
    ? "loading"
    : success
      ? "success"
      : hasResult
        ? "error"
        : "idle";

  return (
    <CollapsiblePill
      status={status}
      icon={
        <>
          <Wrench size={10} className="shrink-0 opacity-50" />
        </>
      }
      label={name}
      variant="tool"
      expandable={canExpand}
      onExpandChange={setIsExpanded}
    >
      {isExpanded && canExpand && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2">
          {/* Arguments */}
          {hasArgs && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.args")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 overflow-x-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {hasResult && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.result")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
                {result}
              </pre>
            </div>
          )}

          {/* Pending state */}
          {isPending && (
            <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
              <LoadingSpinner size="xs" />
              <span>{t("chat.message.running")}</span>
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
```

**Step 2: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 无编译错误

**Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "refactor(ui): refactor ToolCallItem to use CollapsiblePill"
```

---

## Task 4: 重构 SubagentToolItem 使用 CollapsiblePill

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx:1335-1400`

**Step 1: 重构 SubagentToolItem 函数**

将现有的 SubagentToolItem 函数（约 1335-1400 行）替换为：

```tsx
function SubagentToolItem({
  part,
}: {
  part: Extract<MessagePart, { type: "tool" }>;
}) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const hasDetails =
    (part.args && Object.keys(part.args).length > 0) || part.result;

  const status: CollapsibleStatus = part.isPending
    ? "loading"
    : part.success
      ? "success"
      : "error";

  return (
    <CollapsiblePill
      status={status}
      icon={<Wrench size={10} className="text-stone-400 shrink-0" />}
      label={part.name}
      variant="tool"
      expandable={hasDetails}
      onExpandChange={setShowDetails}
    >
      {showDetails && hasDetails && (
        <div className="px-3 pb-2 space-y-2 border-t border-stone-200/50 dark:border-stone-600/50">
          {part.args && Object.keys(part.args).length > 0 && (
            <div>
              <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                {t("chat.message.parameters")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 overflow-auto">
                {JSON.stringify(part.args, null, 2)}
              </pre>
            </div>
          )}
          {part.result && (
            <div>
              <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                {t("chat.message.result")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 max-h-24 overflow-auto">
                {truncateText(part.result, 500)}
              </pre>
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
```

**Step 2: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 无编译错误

**Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "refactor(ui): refactor SubagentToolItem to use CollapsiblePill"
```

---

## Task 5: 提取并重构 Sandbox 为独立组件

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx:1457-1525` (SubagentContentRenderer 中的 sandbox 处理)
- Modify: `frontend/src/components/chat/ChatMessage.tsx:1779-1835` (MessagePartRenderer 中的 sandbox 处理)

**Step 1: 创建 SandboxItem 组件**

在 ChatMessage.tsx 中，SubagentToolItem 之后添加新组件：

```tsx
// Sandbox 状态块组件
function SandboxItem({
  status,
  sandboxId,
  error,
}: {
  status: "starting" | "ready" | "error";
  sandboxId?: string;
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails =
    (status === "ready" && sandboxId) || (status === "error" && error);

  const pillStatus: CollapsibleStatus =
    status === "starting" ? "loading" : status === "ready" ? "success" : "error";

  return (
    <CollapsiblePill
      status={pillStatus}
      icon={<Box size={10} className="shrink-0 opacity-50" />}
      label={t("chat.sandbox.name")}
      suffix={
        status === "starting" && (
          <span className="ml-0.5 font-mono">{t("chat.sandbox.initializing")}</span>
        )
      }
      expandable={hasDetails}
      onExpandChange={setIsExpanded}
    >
      {isExpanded && hasDetails && (
        <div className="mt-1 ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
          {status === "ready" && sandboxId && (
            <div className="text-xs text-stone-600 dark:text-stone-300 pl-1 py-1 font-mono">
              ID: {sandboxId}
            </div>
          )}
          {status === "error" && error && (
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-1">
              {error}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
```

**Step 2: 替换 SubagentContentRenderer 中的 sandbox 处理**

将约 1457-1525 行的 sandbox 处理代码替换为：

```tsx
  // Sandbox 状态块
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
      />
    );
  }
```

**Step 3: 替换 MessagePartRenderer 中的 sandbox 处理**

将约 1779-1835 行的 sandbox 处理代码替换为相同的调用：

```tsx
  // Sandbox 状态块
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
      />
    );
  }
```

**Step 4: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 无编译错误

**Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "refactor(ui): extract SandboxItem component using CollapsiblePill"
```

---

## Task 6: 清理和验证

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage.tsx`

**Step 1: 移除未使用的 import**

检查并移除因重构而不再使用的 import（如果有）。特别注意 ChevronDown、ChevronRight 可能不再需要（ChevronRight 已在 CollapsiblePill 内部使用）。

**Step 2: 运行完整构建**

Run: `cd frontend && npm run build`
Expected: 无编译错误，无警告

**Step 3: 运行 lint 检查**

Run: `cd frontend && npm run lint`
Expected: 无错误

**Step 4: 手动测试**

启动开发服务器，测试以下场景：
1. Thinking 块的展开/收起、加载状态
2. Tool 调用的成功/失败/加载状态
3. Sandbox 的初始化/就绪/错误状态

**Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "chore(ui): cleanup unused imports after CollapsiblePill refactor"
```

---

## 验收标准

- [ ] CollapsiblePill 组件创建完成，支持 status、variant、icon、label、children 等属性
- [ ] ThinkingBlock 使用 CollapsiblePill 重构完成
- [ ] ToolCallItem 使用 CollapsiblePill 重构完成
- [ ] SubagentToolItem 使用 CollapsiblePill 重构完成
- [ ] SandboxItem 组件提取完成，使用 CollapsiblePill
- [ ] 所有组件视觉效果与重构前一致
- [ ] 无编译错误和 lint 错误
