import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/useWebSocketNotifications.tsx",
  ),
  "utf8",
);

test("task completion for the open session triggers a stream reconcile", () => {
  // 当前会话跑完（可能在另一端推进）也要触发本地对账：落定气泡/接续新 run
  expect(source).toMatch(/onCurrentSessionTaskComplete\?:/);
  expect(source).toMatch(/onCurrentSessionTaskCompleteRef/);
  expect(source).toMatch(/if \(session_id === sessionId\)/);
});

const appContentSource = readFileSync(
  join(
    process.cwd(),
    "src/components/layout/AppContent/ChatAppContent.tsx",
  ),
  "utf8",
);

test("ChatAppContent wires the reconcile callback into websocket notifications", () => {
  expect(appContentSource).toMatch(/onCurrentSessionTaskComplete:/);
  expect(appContentSource).toMatch(/reconcileActiveRun/);
});
