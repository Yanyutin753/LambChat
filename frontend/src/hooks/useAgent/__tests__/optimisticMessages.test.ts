import { createOptimisticMessagesForSend } from "../optimisticMessages";

test("attaches run modes to the optimistic user message only", () => {
  const { messages } = createOptimisticMessagesForSend({
    previousMessages: [],
    content: "ok",
    runModes: ["auto", "goal"],
  });

  expect(messages).toHaveLength(2);
  expect(messages[0]).toMatchObject({ role: "user", content: "ok" });
  expect(messages[0]?.runModes).toEqual(["auto", "goal"]);
  expect(messages[1]?.runModes).toBeUndefined();
});

test("omits run modes when none were active at send time", () => {
  const { messages } = createOptimisticMessagesForSend({
    previousMessages: [],
    content: "ok",
  });

  expect(messages[0]?.runModes).toBeUndefined();
});
