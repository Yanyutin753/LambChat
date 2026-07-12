import {
  dispatchSessionTitleUpdated,
  getCachedSessionTitle,
  listenSessionTitleUpdated,
} from "../sessionTitleEvents.ts";

test("dispatches generated session title updates to listeners", () => {
  const target = new EventTarget();
  const received: Array<{ sessionId: string; title: string }> = [];

  const cleanup = listenSessionTitleUpdated((detail) => {
    received.push(detail);
  }, target);

  dispatchSessionTitleUpdated(
    { sessionId: "session-1", title: "Generated title" },
    target,
  );

  expect(received).toEqual([
    { sessionId: "session-1", title: "Generated title" },
  ]);
  expect(getCachedSessionTitle("session-1")).toBe("Generated title");

  cleanup();
  dispatchSessionTitleUpdated(
    { sessionId: "session-1", title: "Ignored title" },
    target,
  );

  expect(received).toEqual([
    { sessionId: "session-1", title: "Generated title" },
  ]);
});
