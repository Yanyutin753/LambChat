import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("loadHistory ignores stale async results instead of overwriting the active chat", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

  expect(source).toMatch(/loadHistoryRequestIdRef/);
  expect(source).toMatch(/isStaleHistoryLoad/);
  expect(source).toMatch(/loadHistoryRequestIdRef\.current \+= 1/);
});

test("clearMessages clears loading flags when a history load is invalidated", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");
  const clearMessagesBody = source.match(
    /const clearMessages = useCallback\(\(\) => \{([\s\S]*?)\n {2}\}, \[\]\);/,
  )?.[1];

  expect(clearMessagesBody).toBeTruthy();
  expect(clearMessagesBody).toMatch(/setIsLoading\(false\)/);
  expect(clearMessagesBody).toMatch(/setIsLoadingHistory\(false\)/);
  expect(clearMessagesBody).toMatch(/isLoadingHistoryRef\.current = false/);
});
