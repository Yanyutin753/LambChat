import test from "node:test";
import assert from "node:assert/strict";
import {
  getInitialUrlSyncCompletionAction,
  getSessionRouteSyncAction,
  shouldLoadSessionFromUrlChange,
} from "./useSessionSync.ts";

test("does not restore a chat route after the user already navigated away", () => {
  assert.equal(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/skills",
      sessionId: "session-123",
      urlSessionId: undefined,
      externalNavigate: false,
    }),
    null,
  );
});

test("does not restore chat when render state is stale but browser path already left chat", () => {
  assert.equal(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/chat/session-123",
      browserPathname: "/users",
      sessionId: "session-456",
      urlSessionId: "session-123",
      externalNavigate: false,
    }),
    null,
  );
});

test("updates the chat url when a new session is created from /chat", () => {
  assert.deepEqual(
    getSessionRouteSyncAction({
      activeTab: "chat",
      pathname: "/chat",
      sessionId: "session-123",
      urlSessionId: undefined,
      externalNavigate: false,
    }),
    {
      type: "replace-url",
      path: "/chat/session-123",
    },
  );
});

test("loads the target session when external navigation lands on chat from an empty state", () => {
  assert.equal(
    shouldLoadSessionFromUrlChange({
      activeTab: "chat",
      sessionId: null,
      urlSessionId: "session-123",
      isLoading: false,
      isNewSession: false,
      isInternalNavigation: false,
    }),
    true,
  );
});

test("does not trigger a second url-change load while the initial url sync is still pending", () => {
  assert.equal(
    shouldLoadSessionFromUrlChange({
      activeTab: "chat",
      sessionId: null,
      urlSessionId: "session-123",
      isLoading: false,
      isNewSession: false,
      isInternalNavigation: false,
      initialUrlSyncPending: true,
    }),
    false,
  );
});

test("clears external navigation state after the initial url sync finishes on chat", () => {
  assert.deepEqual(
    getInitialUrlSyncCompletionAction({
      activeTab: "chat",
      pathname: "/chat/session-123",
      externalNavigate: true,
    }),
    {
      type: "clear-external-state",
      path: "/chat/session-123",
    },
  );
});
