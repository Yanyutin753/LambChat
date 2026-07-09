import { getSSECloseAction, isTerminalSSEEvent } from "../sseConnection.ts";

test("retries an SSE close that arrives before a terminal stream event", () => {
  expect(
    getSSECloseAction({
      receivedTerminalEvent: false,
    }),
  ).toBe("retry");
});

test("treats SSE close as terminal only after done or task error", () => {
  expect(isTerminalSSEEvent("message:chunk")).toBe(false);
  expect(isTerminalSSEEvent("done")).toBe(true);
  expect(isTerminalSSEEvent("complete")).toBe(true);
  expect(isTerminalSSEEvent("user:cancel")).toBe(false);
  expect(isTerminalSSEEvent("error", { type: "ValueError" })).toBe(true);

  expect(
    getSSECloseAction({
      receivedTerminalEvent: true,
    }),
  ).toBe("terminal");
});

test("does not treat transport-level SSE errors as terminal task events", () => {
  expect(
    isTerminalSSEEvent("error", { error: "An internal error occurred" }),
  ).toBe(false);
});
