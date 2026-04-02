import test from "node:test";
import assert from "node:assert/strict";
import {
  getSessionRouteSyncAction,
  shouldResetExternalNavigateFlag,
} from "./useSessionSync.ts";


test("resets the external navigation flag only when present", () => {
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: true }),
    true,
  );
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: false }),
    false,
  );
  assert.equal(shouldResetExternalNavigateFlag({}), false);
  assert.equal(shouldResetExternalNavigateFlag(null), false);
});

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
