import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import {
  getTargetRunIdFromSearch,
  getInitialUrlSyncCompletionAction,
  getSessionRouteSyncAction,
  shouldLoadSessionFromUrlChange,
} from "../useSessionSync.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("does not restore a chat route after the user already navigated away", () => {
  expect(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/skills",
      sessionId: "session-123",
      urlSessionId: undefined,
      externalNavigate: false,
    }),
  ).toBe(null);
});

test("does not restore chat when render state is stale but browser path already left chat", () => {
  expect(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/chat/session-123",
      browserPathname: "/users",
      sessionId: "session-456",
      urlSessionId: "session-123",
      externalNavigate: false,
    }),
  ).toBe(null);
});

test("updates the chat url when a new session is created from /chat", () => {
  expect(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/chat",
      sessionId: "session-123",
      urlSessionId: undefined,
      externalNavigate: false,
    }),
  ).toEqual({
    type: "replace-url",
    path: "/chat/session-123",
  });
});

test("reads the target run id from chat url search params", () => {
  expect(getTargetRunIdFromSearch("?run_id=run_20260531_abc&panel=chat")).toBe(
    "run_20260531_abc",
  );
  expect(getTargetRunIdFromSearch("?run_id=")).toBe(undefined);
});

test("loads the target session when external navigation lands on chat from an empty state", () => {
  expect(
    shouldLoadSessionFromUrlChange({
      activeTab: "chat",
      sessionId: null,
      urlSessionId: "session-123",
      isLoading: false,
      isNewSession: false,
      isInternalNavigation: false,
    }),
  ).toBe(true);
});

test("does not trigger a second url-change load while the initial url sync is still pending", () => {
  expect(
    shouldLoadSessionFromUrlChange({
      activeTab: "chat",
      sessionId: null,
      urlSessionId: "session-123",
      isLoading: false,
      isNewSession: false,
      isInternalNavigation: false,
      initialUrlSyncPending: true,
    }),
  ).toBe(false);
});

test("clears external navigation state after the initial url sync finishes on chat", () => {
  expect(
    getInitialUrlSyncCompletionAction({
      activeTab: "chat",
      pathname: "/chat/session-123",
      externalNavigate: true,
    }),
  ).toEqual({
    type: "clear-external-state",
    path: "/chat/session-123",
  });
});

test("session selection does not issue page-level scroll resets", () => {
  const source = readFileSync(
    resolve(__dirname, "../useSessionSync.ts"),
    "utf8",
  );

  expect(source).not.toMatch(/window\.scrollTo/);
});
