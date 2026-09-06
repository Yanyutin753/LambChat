import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("loadHistory ignores stale async results instead of overwriting the active chat", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

  expect(source).toMatch(/loadHistoryRequestIdRef/);
  expect(source).toMatch(/isStaleHistoryLoad/);
  expect(source).toMatch(/loadHistoryRequestIdRef\.current \+= 1/);
  // 状态声明已下沉 loadingStates.ts（useAgent.ts 行数红线）
  const statesSource = readFileSync(
    resolve(__dirname, "../useAgent/loadingStates.ts"),
    "utf8",
  );
  expect(statesSource).toMatch(
    /const \[historyLoadGeneration, setHistoryLoadGeneration\]/,
  );
  expect(source).toMatch(
    /const requestId = loadHistoryRequestIdRef\.current;[\s\S]*setHistoryLoadGeneration\(requestId\)/,
  );
  expect(source).toMatch(/historyAbortControllerRef/);
  expect(source).toMatch(/historyAbortControllerRef\.current\?\.abort\(\)/);
  expect(source).toMatch(/const signal = historyAbortController\.signal/);
  expect(source).toMatch(
    /Promise\.all\(\[\s*sessionApi\.get\(targetSessionId, \{ signal \}\),\s*sessionApi\.getEvents\(targetSessionId, \{[\s\S]*?include_active_user_message: true,[\s\S]*?compact_message_chunks: true,[\s\S]*?signal,[\s\S]*?\}\),\s*\]\)/,
  );
  expect(source).not.toMatch(/await markReadPromise/);
  expect(source).toMatch(/resolveHistoryStreamRunId/);
  expect(source).toMatch(/sseGenerationRef\.current \+= 1/);
  expect(source).toMatch(
    /if \(isStaleHistoryLoad\(\)\) return null;[\s\S]*?sessionData\.name[\s\S]*?dispatchSessionTitleUpdated/,
  );
  expect(source).toMatch(/historyLoadGeneration,/);
});

test("clearMessages clears loading flags when a history load is invalidated", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");
  const clearMessagesBody = source.match(
    /const clearMessages = useCallback\(\(\) => \{([\s\S]*?)\n {2}\}, \[[\s\S]*?\]\);/,
  )?.[1];

  expect(clearMessagesBody).toBeTruthy();
  expect(clearMessagesBody).toMatch(/setIsLoading\(false\)/);
  expect(clearMessagesBody).toMatch(/setIsLoadingHistory\(false\)/);
  expect(clearMessagesBody).toMatch(/isLoadingHistoryRef\.current = false/);
  expect(clearMessagesBody).toMatch(
    /historyAbortControllerRef\.current\?\.abort/,
  );
  expect(clearMessagesBody).toMatch(/sseGenerationRef\.current \+= 1/);
});

test("feedback is deferred outside the essential session and events request pair", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");
  const essentialRequestPair = source.match(
    /const \[sessionData, eventsData\] = await Promise\.all\(\[([\s\S]*?)\]\);/,
  )?.[1];

  expect(essentialRequestPair).toBeTruthy();
  expect(essentialRequestPair).not.toMatch(/feedbackPromise/);
  expect(source).toMatch(/void feedbackPromise\.then/);
});

test("missing sessions surface an unavailable-session error instead of a blank success", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");
  expect(source).toMatch(/chat\.sessionUnavailable/);
  expect(source).toMatch(/会话不存在或已被删除/);
});
