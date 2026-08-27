import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("ChatView wires reverse infinite scroll for older history pages", () => {
  const source = readSource("../ChatView.tsx");

  // Virtuoso 反向无限滚动：firstItemIndex 前移保持滚动位置
  expect(source).toMatch(/firstItemIndex=\{firstItemIndex\}/);
  expect(source).toMatch(/startReached=\{handleVirtuosoStartReached\}/);

  // 头部提供手动“加载更早消息”入口与加载态
  expect(source).toMatch(/Header: virtuosoHeaderComponent/);
  expect(source).toMatch(/chat\.historyLoadOlder/);
  expect(source).toMatch(/chat\.historyLoadingOlder/);

  // 追加旧消息时按前插条数递减 firstItemIndex
  expect(source).toMatch(/setFirstItemIndex/);
  expect(source).toMatch(/onLoadOlderHistory/);
});

test("ChatView prepend detection anchors on the previous first message id", () => {
  const source = readSource("../ChatView.tsx");
  const blockMatch = source.match(
    /const prependCount =[\s\S]{0,900}?prevRenderItemsRef\.current = messages;/,
  );
  expect(blockMatch).toBeTruthy();
  expect(blockMatch![0]).toMatch(
    /messages\[0\]\.id !== previousFirstMessageId/,
  );
  expect(blockMatch![0]).toMatch(/findIndex/);
});

test("ChatView moves firstItemIndex in the same render as the prepended data", () => {
  const source = readSource("../ChatView.tsx");
  // firstItemIndex 必须与前插数据同一次 commit 生效：若放到事后 effect
  // 修正，中间帧会被 Virtuoso 当成顶部插入，滚动位置被重置（跳回顶部）
  expect(source).not.toMatch(
    /useEffect\(\(\) => \{[\s\S]*?findIndex[\s\S]*?setFirstItemIndex[\s\S]*?\}, \[messages\]\);/,
  );
  expect(source).toMatch(
    /if \(prependCount > 0\) \{[\s\S]{0,500}?setFirstItemIndex/,
  );
});

test("ChatView syncs firstItemIndexRef in the same render as the prepend", () => {
  const source = readSource("../ChatView.tsx");
  // rangeChanged 的绝对索引换算读 firstItemIndexRef。父组件的 useEffect
  // 晚于子组件（Virtuoso）的事件发射，若只靠 effect 同步，前插后第一帧
  // 的换算会用旧基准，dataRange 整体偏移一个分页量——时间轴点击后
  // 点亮落在目标轮之后且不再自愈。ref 必须在前插的同一渲染帧同步。
  const block = source.match(
    /if \(prependCount > 0\) \{[\s\S]*?prevRenderItemsRef\.current = messages;/,
  );
  expect(block).toBeTruthy();
  expect(block![0]).toMatch(/firstItemIndexRef\.current = nextFirstItemIndex/);
});

test("ChatAppContent passes the older-history pagination props to ChatView", () => {
  const source = readSource("../ChatAppContent.tsx");

  expect(source).toMatch(/hasMoreHistoryTraces=\{hasMoreHistoryTraces\}/);
  expect(source).toMatch(/isLoadingOlderHistory=\{isLoadingOlderHistory\}/);
  expect(source).toMatch(/onLoadOlderHistory=\{loadOlderHistory\}/);
});

test("useAgent loads the first history page bounded and pages older runs by cursor", () => {
  const source = readSource("../../../../hooks/useAgent.ts");
  const paginationSource = readSource(
    "../../../../hooks/useAgent/historyTracePagination.ts",
  );

  // 首屏只取最近一页（按 trace 窗口）
  expect(source).toMatch(/trace_limit: HISTORY_TRACE_PAGE_SIZE/);
  expect(source).toMatch(/useHistoryTracePagination/);

  // 翻页走游标，并在完成后全量重建消息
  expect(paginationSource).toMatch(
    /before_trace_started_at: traceWindow\.oldest_trace_started_at/,
  );
  expect(paginationSource).toMatch(
    /before_trace_id: traceWindow\.oldest_trace_id/,
  );
  expect(paginationSource).toMatch(/mergeOlderHistoryEvents/);
  expect(paginationSource).toMatch(
    /reconstructMessagesFromEvents\(\s*mergedEvents/,
  );
});
