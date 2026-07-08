import type { MessagePart } from "../../../types";
import { processMessageEvent } from "../eventProcessor.ts";

test("merges streamed summary chunks inside a subagent by summary id", () => {
  let parts: MessagePart[] = [
    {
      type: "subagent",
      agent_id: "agent-1",
      agent_name: "Research",
      input: "look this up",
      depth: 1,
      isPending: true,
      status: "running",
      parts: [],
    },
  ];

  const first = processMessageEvent(
    "summary",
    { content: "first ", summary_id: "summary-1", agent_id: "agent-1" },
    parts,
    "",
    [],
    1,
    [{ agent_id: "agent-1", depth: 1, message_id: "message-1" }],
    true,
    "message-1",
  );
  parts = first.parts;

  const second = processMessageEvent(
    "summary",
    { content: "second", summary_id: "summary-1", agent_id: "agent-1" },
    parts,
    "",
    [],
    1,
    [{ agent_id: "agent-1", depth: 1, message_id: "message-1" }],
    true,
    "message-1",
  );

  const subagent = second.parts[0];
  expect(subagent.type).toBe("subagent");
  const summaries = subagent.parts?.filter((part) => part.type === "summary");

  expect(summaries?.length).toBe(1);
  expect(summaries?.[0]?.content).toBe("first second");
});

test("agent call uses provided team role display name", () => {
  const result = processMessageEvent(
    "agent:call",
    {
      agent_id: "team-m-1-researcher_abc",
      agent_name: "Researcher",
      input: "Find the facts",
    },
    [],
    "",
    [],
    1,
    [],
    true,
    "message-1",
  );

  expect(result.parts.length).toBe(1);
  const subagent = result.parts[0];
  expect(subagent.type).toBe("subagent");
  expect(subagent.agent_name).toBe("Researcher");
});

test("agent call preserves team role avatar url", () => {
  const result = processMessageEvent(
    "agent:call",
    {
      agent_id: "team-m-1-designer_abc",
      agent_name: "Designer",
      agent_avatar: "https://cdn.example.com/designer.png",
      input: "Sketch the flow",
    },
    [],
    "",
    [],
    1,
    [],
    true,
    "message-1",
  );

  const subagent = result.parts[0];
  expect(subagent.type).toBe("subagent");
  expect(subagent.agent_avatar).toBe("https://cdn.example.com/designer.png");
});

test("adds recommended questions from recommendation events", () => {
  const result = processMessageEvent(
    "recommend:questions",
    {
      questions: [
        "如何预防胫骨内侧压力综合征？",
        { content: "赛前减量期具体怎么做？" },
        { text: "能量胶补给策略有哪些细节？" },
      ],
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "message-1",
  );

  expect(result.parts.length).toBe(1);
  const recommendations = result.parts[0];
  expect(recommendations.type).toBe("recommend_questions");
  expect(recommendations.questions.map((question) => question.content)).toEqual(
    [
      "如何预防胫骨内侧压力综合征？",
      "赛前减量期具体怎么做？",
      "能量胶补给策略有哪些细节？",
    ],
  );
});

test("adds artifact result events as artifact parts without tool chrome", () => {
  const result = processMessageEvent(
    "artifact:result",
    {
      artifact: {
        kind: "file",
        id: "file:revealed/report.pdf",
        name: "report.pdf",
        path: "/workspace/report.pdf",
        fileSize: 2048,
        preview: {
          kind: "file",
          previewKey: "revealed/report.pdf",
          filePath: "/workspace/report.pdf",
          signedUrl: "/api/upload/file/revealed/report.pdf",
          fileSize: 2048,
        },
      },
      success: true,
    },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(result.parts.length).toBe(1);
  const artifact = result.parts[0];
  expect(artifact.type).toBe("artifact");
  if (artifact.type !== "artifact") return;
  expect(artifact.success).toBe(true);
  expect(artifact.artifact.kind).toBe("file");
  expect(artifact.artifact.name).toBe("report.pdf");
});

test("adds generic plugin message events as plugin message parts", () => {
  const result = processMessageEvent(
    "plugin:message",
    {
      plugin_id: "automation_runner",
      renderer: "automation_runner.RunCard",
      id: "run-1",
      title: "Run completed",
      status: "completed",
      payload: { run_id: "run-1", output: { answer: "done" } },
      timestamp: "2026-07-08T12:00:00Z",
    },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  assert.equal(result.parts.length, 1);
  const pluginMessage = result.parts[0];
  assert.equal(pluginMessage.type, "plugin_message");
  if (pluginMessage.type !== "plugin_message") return;
  assert.equal(pluginMessage.plugin_id, "automation_runner");
  assert.equal(pluginMessage.renderer, "automation_runner.RunCard");
  assert.equal(pluginMessage.id, "run-1");
  assert.equal(pluginMessage.status, "completed");
  assert.deepEqual(pluginMessage.payload, {
    run_id: "run-1",
    output: { answer: "done" },
  });
});

test("ignores plugin message events without a plugin id or renderer", () => {
  const result = processMessageEvent(
    "plugin:message",
    { plugin_id: "automation_runner", payload: { run_id: "run-1" } },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  assert.equal(result.parts.length, 0);
});

test("complete event cancels unfinished todo items", () => {
  const result = processMessageEvent(
    "complete",
    {},
    [
      {
        type: "todo",
        isStreaming: true,
        items: [
          { content: "done", status: "completed" },
          { content: "started", status: "in_progress", activeForm: "starting" },
          { content: "not started", status: "pending" },
        ],
      },
    ],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  const todo = result.parts[0];
  expect(todo.type).toBe("todo");
  expect(todo.isStreaming).toBe(false);
  expect(todo.items.map((item) => item.status)).toEqual([
    "completed",
    "cancelled",
    "cancelled",
  ]);
  expect(todo.items[1].activeForm).toBe(undefined);
});
