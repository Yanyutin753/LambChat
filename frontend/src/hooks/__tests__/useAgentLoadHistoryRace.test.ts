import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("loadHistory ignores stale async results instead of overwriting the active chat", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

  expect(source).toMatch(/loadHistoryRequestIdRef/);
  expect(source).toMatch(/isStaleHistoryLoad/);
  expect(source).toMatch(/loadHistoryRequestIdRef\.current \+= 1/);
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
