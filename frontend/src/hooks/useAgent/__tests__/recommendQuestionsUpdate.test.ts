import type { Message } from "../../../types";
import { applyRecommendQuestionsToMessages } from "../recommendQuestionsUpdate";

function assistant(runId: string, content: string): Message {
  return {
    id: `message-${runId}`,
    role: "assistant",
    content,
    timestamp: new Date("2026-08-09T00:00:00Z"),
    runId,
    parts: [],
    isStreaming: false,
  };
}

test("applies WebSocket recommendations only to the matching assistant run", () => {
  const messages = [assistant("run-1", "first"), assistant("run-2", "second")];

  const updated = applyRecommendQuestionsToMessages(messages, "run-2", [
    "问题一？",
    "问题二？",
  ]);

  expect(updated[0]).toBe(messages[0]);
  expect(updated[1].content).toBe("second");
  expect(updated[1].parts?.[0]).toMatchObject({
    type: "recommend_questions",
    questions: [{ content: "问题一？" }, { content: "问题二？" }],
  });
});

test("replaces recommendations when the same run notification is delivered again", () => {
  const first = applyRecommendQuestionsToMessages(
    [assistant("run-1", "answer")],
    "run-1",
    ["旧问题？"],
  );

  const updated = applyRecommendQuestionsToMessages(first, "run-1", [
    "新问题？",
  ]);

  const recommendationParts = updated[0].parts?.filter(
    (part) => part.type === "recommend_questions",
  );
  expect(recommendationParts).toHaveLength(1);
  expect(recommendationParts?.[0]).toMatchObject({
    questions: [{ content: "新问题？" }],
  });
});

test("ignores empty or malformed recommendation values", () => {
  const messages = [assistant("run-1", "answer")];

  const updated = applyRecommendQuestionsToMessages(messages, "run-1", [
    "",
    "   ",
  ]);

  expect(updated).toBe(messages);
});
