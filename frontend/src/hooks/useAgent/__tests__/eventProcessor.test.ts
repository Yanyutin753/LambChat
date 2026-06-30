import assert from "node:assert/strict";
import test from "node:test";
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
  assert.equal(subagent.type, "subagent");
  const summaries = subagent.parts?.filter((part) => part.type === "summary");

  assert.equal(summaries?.length, 1);
  assert.equal(summaries?.[0]?.content, "first second");
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

  assert.equal(result.parts.length, 1);
  const subagent = result.parts[0];
  assert.equal(subagent.type, "subagent");
  assert.equal(subagent.agent_name, "Researcher");
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
  assert.equal(subagent.type, "subagent");
  assert.equal(subagent.agent_avatar, "https://cdn.example.com/designer.png");
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

  assert.equal(result.parts.length, 1);
  const recommendations = result.parts[0];
  assert.equal(recommendations.type, "recommend_questions");
  assert.deepEqual(
    recommendations.questions.map((question) => question.content),
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

  assert.equal(result.parts.length, 1);
  const artifact = result.parts[0];
  assert.equal(artifact.type, "artifact");
  if (artifact.type !== "artifact") return;
  assert.equal(artifact.success, true);
  assert.equal(artifact.artifact.kind, "file");
  assert.equal(artifact.artifact.name, "report.pdf");
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
  assert.equal(todo.type, "todo");
  assert.equal(todo.isStreaming, false);
  assert.deepEqual(
    todo.items.map((item) => item.status),
    ["completed", "cancelled", "cancelled"],
  );
  assert.equal(todo.items[1].activeForm, undefined);
});
