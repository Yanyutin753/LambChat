import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const readSource = (relativePath: string) =>
  readFileSync(resolve(process.cwd(), "src", relativePath), "utf8");

const chatViewSource = readSource("components/layout/AppContent/ChatView.tsx");
const outlineSource = readSource(
  "components/layout/AppContent/useChatOutline.tsx",
);
const chatMessageSource = readSource("components/chat/ChatMessage/index.tsx");

test("keeps Virtuoso range changes out of ChatView render state", () => {
  expect(chatViewSource).not.toMatch(/useState<ListRange/);
  expect(chatViewSource).not.toMatch(/setVisibleRange/);
  expect(chatViewSource).toMatch(/rangeChanged=\{handleVisibleRangeChange\}/);
  expect(outlineSource).toMatch(/handleVisibleRangeChange\s*=\s*useCallback/);
});

test("does not replay assistant entrance animation for remounted history messages", () => {
  expect(chatMessageSource).not.toMatch(
    /"group w-full animate-\[fade-in_0\.3s_ease-out\]/,
  );
  expect(chatMessageSource).toMatch(
    /isLastMessage\s*&&\s*message\.isStreaming\s*&&\s*"animate-\[fade-in_0\.3s_ease-out\]"/,
  );
});

test("derives last-message state from the rendered list including steer items", () => {
  expect(chatViewSource).toMatch(
    /isLastMessage=\{index === renderItems\.length - 1\}/,
  );
  expect(chatViewSource.indexOf("const renderItems = useMemo")).toBeLessThan(
    chatViewSource.indexOf("const virtuosoItemContent = useCallback"),
  );
});
