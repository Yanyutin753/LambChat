import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("loadHistory ignores stale async results instead of overwriting the active chat", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

  assert.match(source, /loadHistoryRequestIdRef/);
  assert.match(source, /isStaleHistoryLoad/);
  assert.match(source, /loadHistoryRequestIdRef\.current \+= 1/);
});

test("clearMessages clears loading flags when a history load is invalidated", () => {
  const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");
  const clearMessagesBody = source.match(
    /const clearMessages = useCallback\(\(\) => \{([\s\S]*?)\n {2}\}, \[\]\);/,
  )?.[1];

  assert.ok(clearMessagesBody, "clearMessages callback should exist");
  assert.match(clearMessagesBody, /setIsLoading\(false\)/);
  assert.match(clearMessagesBody, /setIsLoadingHistory\(false\)/);
  assert.match(clearMessagesBody, /isLoadingHistoryRef\.current = false/);
});
