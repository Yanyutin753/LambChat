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
  const effectMatch = source.match(
    /useEffect\(\(\) => \{[\s\S]*?prevRenderItemsRef[\s\S]*?\}, \[messages\]\);/,
  );
  expect(effectMatch).toBeTruthy();
  expect(effectMatch![0]).toMatch(/messages\[0\]\.id === prev\[0\]\.id/);
  expect(effectMatch![0]).toMatch(/findIndex/);
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
