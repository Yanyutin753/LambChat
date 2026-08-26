# 长会话打开卡死止血 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除「打开超长项目会话时页面卡死」的三个前端热点：历史重建 O(n²)、项目预览文件无上限并发全量拉取、派生计算全量重扫。

**Architecture:** 三个独立止血修复，不改 API 契约：(A) `reconstructMessagesFromEvents` 内两处二次方扫描改为线性预扫描/计数；(B) `loadProjectRevealFiles` 加并发上限、结果缓存加 LRU 淘汰；(C) 会话图片库与工具面板派生计算按消息/工具 part 引用做 WeakMap 记忆化。结构性优化（事件分页）另开 issue，不在本计划内。

**Tech Stack:** React 19 + TypeScript + Vitest（纯函数测试，无需 DOM）。

**Spec:** 用户反馈：打开很长、且带文件产物的会话时等待极久甚至卡死。诊断结论见会话记录：`useAgent.ts:309-316` 全量拉事件 + `historyLoader.ts` O(n²) + `revealPreviewData.ts:207-226` 无上限 Promise.all 全量拉项目文件（缓存无淘汰）。

## Global Constraints

- 前端测试位于源码同目录 `__tests__/*.test.ts`，纯函数测试不加 jsdom 注释。
- 每个任务严格红-绿-重构：先写失败测试并运行确认失败。
- 不改无关代码；不动后端。
- 验证：`cd frontend && pnpm test` + `pnpm run lint` + `pnpm run build`。

---

### Task A: historyLoader 两处 O(n²) → O(n)

**Files:**
- Modify: `frontend/src/hooks/useAgent/historyLoader.ts:337-348`（run_id 归一化）与 `:504-520`（循环内 filter）
- Test: `frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts`（已存在，追加用例）

**Interfaces:**
- Produces: `export function normalizeEventRunIds(events: HistoryEvent[]): HistoryEvent[]`（historyLoader.ts 导出，供测试直接调用）；`reconstructMessagesFromEvents` 行为不变。

- [ ] **A1 RED：为 normalizeEventRunIds 写失败测试**（新导出函数尚不存在）：

```ts
test("normalizeEventRunIds backfills missing run_id from nearest neighbors", () => {
  const events = [
    { event_id: "1", event_type: "message", timestamp: "2026-01-01T00:00:01Z", run_id: "run-a" },
    { event_id: "2", event_type: "thinking", timestamp: "2026-01-01T00:00:02Z" },
    { event_id: "3", event_type: "thinking", timestamp: "2026-01-01T00:00:03Z" },
    { event_id: "4", event_type: "message", timestamp: "2026-01-01T00:00:04Z", run_id: "run-b" },
  ] as unknown as HistoryEvent[];
  const normalized = normalizeEventRunIds(events);
  expect(normalized[1].run_id).toBe("run-a"); // 前向就近
  expect(normalized[2].run_id).toBe("run-a"); // 前向优先于后向
});
```

- [ ] **A2 RED：run_id 交替排列断言线性复杂度**（大数组 20k 事件在 1s 内完成，防止回归）：

```ts
test("normalizeEventRunIds stays linear on large inputs", () => {
  const events = Array.from({ length: 20000 }, (_, i) => ({
    event_id: `e${i}`,
    event_type: "thinking",
    timestamp: new Date(i * 1000).toISOString(),
  })) as unknown as HistoryEvent[];
  const start = performance.now();
  const normalized = normalizeEventRunIds(events);
  expect(performance.now() - start).toBeLessThan(1000);
  expect(normalized.every((e) => e.run_id === undefined)).toBe(true);
});
```

- [ ] 运行确认失败：`cd frontend && pnpm vitest run src/hooks/useAgent/__tests__/historyLoader.test.ts`

- [ ] **A3 GREEN：实现 normalizeEventRunIds**，替换 `:337-348` 内联逻辑（排序仍在 reconstructMessagesFromEvents 内完成后传入）：

```ts
export function normalizeEventRunIds(events: HistoryEvent[]): HistoryEvent[] {
  const prevRunIdByIndex: Array<string | undefined> = new Array(events.length);
  let lastSeen: string | undefined;
  for (let i = 0; i < events.length; i++) {
    prevRunIdByIndex[i] = lastSeen;
    if (events[i].run_id) lastSeen = events[i].run_id;
  }
  const nextRunIdByIndex: Array<string | undefined> = new Array(events.length);
  let nextSeen: string | undefined;
  for (let i = events.length - 1; i >= 0; i--) {
    nextRunIdByIndex[i] = nextSeen;
    if (events[i].run_id) nextSeen = events[i].run_id;
  }
  return events.map((event, index) => {
    if (event.run_id) return event;
    const runId = prevRunIdByIndex[index] || nextRunIdByIndex[index];
    return runId ? { ...event, run_id: runId } : event;
  });
}
```

- [ ] **A4 GREEN：修 `:504-520` 循环内 filter** — 维护 `assistantTurnCountsByRunId: Map<string, number>`，引入局部 `pushMessage` helper 包裹全部 `reconstructedMessages.push` 助手消息点（365/386/426/433/468/470/523 行），assistant+runId 时计数；三元内改为读 Map：

```ts
const priorAssistantTurns = event.run_id
  ? assistantTurnCountsByRunId.get(event.run_id) || 0
  : 0;
```

- [ ] 运行全部 historyLoader 测试通过（含既有用例防行为回归）。
- [ ] **Commit**: `perf: make history reconstruction linear (O(n²) → O(n))`

### Task B: 项目预览文件拉取并发上限 + 缓存 LRU 淘汰

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/revealPreviewData.ts:189-247`（loadProjectRevealFiles）、`:261-314`（缓存）
- Test: `frontend/src/components/chat/ChatMessage/items/__tests__/revealPreviewData.test.ts`（追加）

**Interfaces:**
- Produces: `loadProjectRevealFiles(project, options?: { concurrency?: number })`（默认 6）；缓存 LRU 上限 `PROJECT_REVEAL_FILES_CACHE_MAX_ENTRIES = 4`，`loadProjectRevealFilesCached` / `getCachedProjectRevealFiles` / `clearProjectRevealFilesCache` 签名不变。

- [ ] **B1 RED：并发上限测试**（stub 全局 fetch，记录同时在飞的请求数）：

```ts
test("loadProjectRevealFiles caps concurrent text file fetches", async () => {
  const files: Record<string, FileManifestEntry> = {};
  for (let i = 0; i < 20; i++) {
    files[`/f${i}.txt`] = { url: `/api/upload/file/f${i}`, is_binary: false, size: 1 };
  }
  let inFlight = 0;
  let maxInFlight = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((r) => setTimeout(r, 5));
    inFlight--;
    return new Response(`content`, { status: 200 });
  }) as typeof fetch;
  try {
    const result = await loadProjectRevealFiles(makeV2Project(files));
    expect(Object.keys(result.files)).toHaveLength(20);
    expect(result.failed).toHaveLength(0);
    expect(maxInFlight).toBeLessThanOrEqual(6);
    expect(maxInFlight).toBeGreaterThan(1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
```

- [ ] **B2 RED：LRU 淘汰测试**（加载 5 个项目后最早项被淘汰、最近使用项保留；`getCachedProjectRevealFiles` 命中刷新新鲜度）。
- [ ] 运行确认失败。
- [ ] **B3 GREEN**：实现 `mapWithConcurrency` 局部工具 + `loadProjectRevealFiles` 改用之；缓存 Map set 时超限删除最旧 key，get 命中时 delete+set 刷新。
- [ ] 全部 revealPreviewData 测试通过。
- [ ] **Commit**: `perf: cap project reveal file fetch concurrency and evict stale file caches`

### Task C: 派生计算 WeakMap 记忆化（图片库 + 工具面板）

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/sessionImageGallery.tsx:196-230`、`frontend/src/components/chat/ChatMessage/toolCallPanelStore.ts:99-150`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/sessionImageGallery.test.ts`（追加）、`__tests__/toolCallPanelStore.test.tsx`（追加）

**Interfaces:**
- Consumes: Message/ToolPart 为不可变替换对象（未变消息保持引用），WeakMap 以对象引用为键。
- Produces: `collectSessionImageGalleryItems`、`syncToolCallPanelStore` 签名不变，行为不变，仅重复调用时跳过已计算消息的重解析。

- [ ] **C1 RED：图片库记忆化测试**（用 getter 计数 content 读取次数）：

```ts
test("collectSessionImageGalleryItems skips reparsing unchanged messages", () => {
  let reads = 0;
  const stable = {
    id: "m1", role: "assistant", runId: "r1",
    get content() { reads++; return "![a](/img/a.png)"; },
  } as unknown as Message;
  collectSessionImageGalleryItems([stable]);
  const streaming = { id: "m2", role: "assistant", runId: "r1", content: "![b](/img/b.png)" } as Message;
  collectSessionImageGalleryItems([stable, streaming]);
  expect(reads).toBe(1); // 第二次调用未重读 stable.content
});
```

- [ ] **C2 RED：工具面板 args.partial JSON.parse 记忆化测试**（同理用 getter 计数）。
- [ ] 运行确认失败。
- [ ] **C3 GREEN**：两处各加模块级 `WeakMap`，按消息/工具 part 引用缓存计算结果；dedupe 与 store.set 的 shallowEqual 短路逻辑保持不变。
- [ ] 全部相关测试通过。
- [ ] **Commit**: `perf: memoize per-message gallery and tool panel derivations by reference`

### Task D: 验证与收尾

- [ ] `cd frontend && pnpm test`（全量）
- [ ] `cd frontend && pnpm run lint && pnpm run build`（build 需 ~6G 堆，见 memory）
- [ ] 建分支 `perf/long-session-open-freeze`，提 PR 到 main；结构性优化（事件分页、Worker 解析、outline 记忆化、TimelineRail 虚拟化）列为 PR 描述中的 follow-up。
