/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test, vi } from "vitest";
import type { Message } from "../../../../types";
import en from "../../../../i18n/locales/en.json";
import { SubagentPanelContent } from "../SubagentPanelContent";
import { buildSubagentConversation } from "../subagentPanelState";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "../subagentPanelStore";

Element.prototype.scrollIntoView = vi.fn();

vi.mock("../MessagePartRenderer", () => ({
  MessagePartRenderer: ({ part }: { part: { content?: string } }) => (
    <div>{part.content}</div>
  ),
}));
vi.mock("../index", () => ({
  ChatMessage: ({
    message,
    personaName,
    showFeedbackAndShareActions,
  }: {
    message: Message;
    personaName: string;
    showFeedbackAndShareActions: boolean;
  }) => (
    <section
      data-testid="chat-message"
      data-role={message.role}
      data-message-id={message.id}
      data-streaming={message.isStreaming}
      data-cancelled={message.cancelled}
      data-failed={message.metadata?.steerStatus === "failed"}
      data-feedback={showFeedbackAndShareActions}
      data-persona={personaName}
    >
      {message.content}
      {message.parts?.map((part, index) => (
        <div key={index}>
          {part.type === "text" || part.type === "thinking"
            ? part.content
            : part.type}
        </div>
      ))}
    </section>
  ),
}));
const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });
afterEach(() => {
  cleanup();
  subagentPanelStore.clear();
});

test("the conversation shows initial work, follow-up and resumed replies in order", () => {
  const first = {
    type: "subagent",
    agent_id: "reviewer",
    agent_name: "Reviewer",
    input: "Review API permissions",
    result: "First report",
    status: "complete",
    success: true,
    parts: [],
  };
  const followup = {
    type: "tool",
    id: "send-1",
    name: "send_subagent_message",
    args: { subagent_id: "reviewer", message: "Only permissions now" },
    success: true,
  };
  const resumed = {
    ...first,
    input: "Only permissions now",
    result: "History retained",
  };
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: resumed.input,
    result: resumed.result,
    status: "complete",
    success: true,
    history: [first, followup, resumed],
  } as SubagentPanelData);
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  const text = view.container.textContent!;
  expect(text.indexOf("Review API permissions")).toBeLessThan(
    text.indexOf("First report"),
  );
  expect(text.indexOf("First report")).toBeLessThan(
    text.indexOf("Only permissions now"),
  );
  expect(text.indexOf("Only permissions now")).toBeLessThan(
    text.indexOf("History retained"),
  );
  expect(view.getAllByText("Only permissions now")).toHaveLength(1);
  expect(text).not.toContain("send_subagent_message");
  expect(text).not.toContain("Args");
  expect(
    view.getAllByTestId("chat-message").map((node) => node.dataset.role),
  ).toEqual(["user", "assistant", "user", "assistant"]);
  for (const node of view.getAllByTestId("chat-message")) {
    expect(node.dataset.feedback).toBe("false");
    expect(node.dataset.persona).toBe("Reviewer");
  }
});

test("single historical runs render readable task and reply without raw parameters", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review permissions",
    result: "Completed report",
    status: "complete",
    success: true,
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.getByText("Review permissions")).toBeTruthy();
  expect(view.getByText("Completed report")).toBeTruthy();
  expect(view.queryByText("Args")).toBeNull();
});

test("instructions sent during a run appear before that run's final reply", () => {
  const run = {
    type: "subagent",
    agent_id: "reviewer",
    agent_name: "Reviewer",
    input: "Review",
    result: "Scope narrowed",
    parts: [
      { type: "text", content: "Follow-up received" },
      {
        type: "tool",
        name: "send_parent_message",
        args: { message: "Follow-up acknowledged" },
        startedAt: new Date(1_750_000_007_000).toISOString(),
        success: true,
      },
      { type: "thinking", content: "Preparing the updated report" },
      { type: "text", content: "Scope narrowed" },
    ],
    status: "complete",
    success: true,
    startedAt: 1_750_000_000_000,
    completedAt: 1_750_000_010_000,
  };
  const queued = {
    type: "tool",
    name: "send_subagent_message",
    args: { subagent_id: "reviewer", message: "Permissions only" },
    startedAt: new Date(1_750_000_005_000).toISOString(),
    success: true,
  };
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: run.input,
    result: run.result,
    status: "complete",
    success: true,
    history: [run, queued],
  } as SubagentPanelData);
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  const text = view.container.textContent!;
  expect(text.indexOf("Permissions only")).toBeLessThan(
    text.indexOf("Scope narrowed"),
  );
  expect(text.indexOf("Permissions only")).toBeLessThan(
    text.indexOf("Follow-up received"),
  );
  expect(view.getAllByText("Permissions only")).toHaveLength(1);
});

test("resuming with the original task metadata does not repeat the initial task", () => {
  const first = {
    type: "subagent",
    agent_id: "reviewer",
    agent_name: "Reviewer",
    input: "Original task",
    result: "First reply",
    status: "complete",
    success: true,
  };
  const followup = {
    type: "tool",
    name: "send_subagent_message",
    args: {
      subagent_id: "reviewer",
      message: "Continue with the same history",
    },
    success: true,
  };
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: first.input,
    status: "complete",
    success: true,
    history: [first, followup, { ...first, result: "Second reply" }],
  } as SubagentPanelData);
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.getAllByText("Original task")).toHaveLength(1);
  expect(view.getByText("Second reply")).toBeTruthy();
  const ids = view
    .getAllByTestId("chat-message")
    .map((node) => node.dataset.messageId);
  expect(new Set(ids).size).toBe(ids.length);
});

test("native process parts and the final report render once in the shared chat component", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    result: "Final report",
    status: "complete",
    success: true,
    parts: [
      { type: "thinking", content: "Checking permissions" },
      { type: "text", content: "Final report" },
    ],
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.getAllByText("Final report")).toHaveLength(1);
  expect(view.getByText("Checking permissions")).toBeTruthy();
  expect(view.getAllByTestId("chat-message")[1].dataset.role).toBe("assistant");
});

test("a rejected follow-up remains visible with its error and previous completed reply", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    status: "complete",
    success: true,
    history: [
      {
        type: "subagent",
        agent_id: "reviewer",
        agent_name: "Reviewer",
        depth: 1,
        input: "Review",
        result: "Previous report",
        status: "complete",
        success: true,
      },
      {
        type: "tool",
        name: "send_subagent_message",
        args: { message: "Continue", subagent_id: "reviewer" },
        success: false,
        result: JSON.stringify({
          status: "failed",
          error: "Role access revoked",
        }),
      },
    ],
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.getByText("Previous report")).toBeTruthy();
  expect(view.getByText("Role access revoked")).toBeTruthy();
  expect(view.getByText("Continue").dataset.failed).toBe("true");
});

test("an intermediate text is retained when the final report arrives only on the subagent result", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    result: "Final report",
    status: "complete",
    success: true,
    parts: [{ type: "text", content: "Started checking permissions" }],
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.getByText("Started checking permissions")).toBeTruthy();
  expect(view.getAllByText("Final report")).toHaveLength(1);
});

test("a running turn uses chat streaming state and hides its stale completed report", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    status: "running",
    isPending: true,
    result: "Stale report",
    parts: [{ type: "text", content: "Checking" }],
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.queryByText("Stale report")).toBeNull();
  expect(view.getByText("Checking").parentElement?.dataset.streaming).toBe(
    "true",
  );
});

test("a cancelled turn uses the same cancelled message state as the main chat", () => {
  subagentPanelStore.set({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    status: "cancelled",
    isPending: false,
    result: "Stale report",
    parts: [{ type: "text", content: "Partial reply" }],
  });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <SubagentPanelContent agentId="reviewer" />
    </I18nextProvider>,
  );
  expect(view.queryByText("Stale report")).toBeNull();
  expect(view.getAllByTestId("chat-message")[1].dataset.cancelled).toBe("true");
});

test("splitting a live follow-up preserves the latest turn's file navigation anchors", () => {
  const run = {
    type: "subagent" as const,
    agent_id: "reviewer",
    agent_name: "Reviewer",
    depth: 1,
    input: "Review",
    status: "complete" as const,
    success: true,
    startedAt: 1_750_000_000_000,
    completedAt: 1_750_000_010_000,
    parts: [
      {
        type: "tool" as const,
        name: "reveal_file",
        args: { path: "report.md" },
      },
      { type: "text" as const, content: "Report ready" },
    ],
    result: "Report ready",
  };
  const messages = buildSubagentConversation({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    history: [
      run,
      {
        type: "tool",
        name: "send_subagent_message",
        success: true,
        args: { subagent_id: "reviewer", message: "Continue" },
        startedAt: new Date(1_750_000_005_000).toISOString(),
      },
    ],
  });
  const replies = messages.filter((message) => message.role === "assistant");
  expect(replies[0].metadata).toMatchObject({
    partAnchorOwnerId: "subagent:reviewer",
  });
  expect(replies[1].metadata).toMatchObject({
    partAnchorOwnerId: "subagent:reviewer",
    partIndexOffset: 1,
  });
  expect(replies.map((reply) => reply.duration)).toEqual([5000, 5000]);
  expect(replies[1].timestamp.getTime()).toBe(run.startedAt + 5000);
});

test("successive live instructions stay interleaved with their acknowledgments and tools", () => {
  const startedAt = 1_750_000_000_000;
  const parts = [
    {
      type: "tool" as const,
      name: "reveal_file",
      args: { path: "initial.md" },
      startedAt: new Date(startedAt + 2000).toISOString(),
    },
    { type: "text" as const, content: "Acknowledged A" },
    {
      type: "tool" as const,
      name: "send_parent_message",
      args: { message: "A received" },
      startedAt: new Date(startedAt + 7000).toISOString(),
    },
    { type: "text" as const, content: "Acknowledged B" },
    {
      type: "tool" as const,
      name: "send_parent_message",
      args: { message: "B received" },
      startedAt: new Date(startedAt + 11000).toISOString(),
    },
    { type: "text" as const, content: "Final report" },
  ];
  const messages = buildSubagentConversation({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    history: [
      {
        type: "subagent",
        agent_id: "reviewer",
        agent_name: "Reviewer",
        depth: 1,
        input: "Review",
        status: "complete",
        success: true,
        startedAt,
        completedAt: startedAt + 15000,
        parts,
        result: "Final report",
      },
      ...[5000, 9000].map((offset, index) => ({
        type: "tool" as const,
        id: `send-${index}`,
        name: "send_subagent_message",
        args: {
          subagent_id: "reviewer",
          message: `Instruction ${index ? "B" : "A"}`,
        },
        startedAt: new Date(startedAt + offset).toISOString(),
        success: true,
      })),
    ],
  });
  expect(
    messages.map((message) =>
      message.role === "user"
        ? message.content
        : message.parts?.map((part) =>
            part.type === "text"
              ? part.content
              : part.type === "tool"
                ? part.args
                : part.type,
          ),
    ),
  ).toEqual([
    "Review",
    [{ path: "initial.md" }],
    "Instruction A",
    ["Acknowledged A", { message: "A received" }],
    "Instruction B",
    ["Acknowledged B", { message: "B received" }, "Final report"],
  ]);
  const replies = messages.filter((message) => message.role === "assistant");
  expect(replies.flatMap((message) => message.parts!)).toEqual(parts);
  expect(
    replies.map((message) => message.metadata?.partIndexOffset ?? 0),
  ).toEqual([0, 1, 3]);
  expect(replies.map((message) => message.duration)).toEqual([
    5000, 4000, 6000,
  ]);
  expect(new Set(messages.map((message) => message.id)).size).toBe(
    messages.length,
  );
});

test("a text-only late follow-up separates the streamed revision without duplicating it", () => {
  const startedAt = 1_750_000_000_000;
  const messages = buildSubagentConversation({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    history: [
      {
        type: "subagent",
        agent_id: "reviewer",
        agent_name: "Reviewer",
        depth: 1,
        input: "Review",
        status: "complete",
        success: true,
        startedAt,
        completedAt: startedAt + 10000,
        parts: [{ type: "text", content: "Initial reportRevised report" }],
        result: "Revised report",
      },
      {
        type: "tool",
        name: "send_subagent_message",
        args: { subagent_id: "reviewer", message: "Revise the report" },
        startedAt: new Date(startedAt + 5000).toISOString(),
        success: true,
      },
    ],
  });
  expect(
    messages.map((message) =>
      message.role === "user"
        ? message.content
        : message.parts?.map((part) =>
            part.type === "text" ? part.content : part.type,
          ),
    ),
  ).toEqual([
    "Review",
    ["Initial report"],
    "Revise the report",
    ["Revised report"],
  ]);
});

test("separating a streamed revision retains trailing file tools' original anchors", () => {
  const startedAt = 1_750_000_000_000;
  const file = {
    type: "tool" as const,
    name: "reveal_file",
    args: { path: "revised.md" },
    startedAt: new Date(startedAt + 7000).toISOString(),
  };
  const messages = buildSubagentConversation({
    agentId: "reviewer",
    agentName: "Reviewer",
    input: "Review",
    history: [
      {
        type: "subagent",
        agent_id: "reviewer",
        agent_name: "Reviewer",
        depth: 1,
        input: "Review",
        status: "complete",
        success: true,
        startedAt,
        completedAt: startedAt + 10000,
        parts: [{ type: "text", content: "Initial reportRevised report" }, file],
        result: "Revised report",
      },
      {
        type: "tool",
        name: "send_subagent_message",
        args: { subagent_id: "reviewer", message: "Revise the report" },
        startedAt: new Date(startedAt + 5000).toISOString(),
        success: true,
      },
    ],
  });
  const replies = messages.filter((message) => message.role === "assistant");
  const fileReply = replies.find((message) => message.parts?.includes(file))!;
  expect(
    fileReply.parts!.indexOf(file) +
      Number(fileReply.metadata?.partIndexOffset ?? 0),
  ).toBe(1);
  expect(replies[0].parts).toEqual([
    { type: "text", content: "Initial report" },
  ]);
  expect(messages[2].content).toBe("Revise the report");
  expect(fileReply.parts).toEqual([
    file,
    { type: "text", content: "Revised report" },
  ]);
});


test("timed-out runs display preserved partial report and error without streaming", () => {
  const messages = buildSubagentConversation({
    agentId: "reviewer", agentName: "Reviewer", input: "Review",
    result: "Partial result: verified file contents; task unfinished",
    error: "Execution deadline exceeded", status: "timed_out", isPending: false,
    parts: [{ type: "tool", name: "read_file", args: {}, result: "verified file contents", isPending: false }],
  });
  const reply = messages.find(message => message.role === "assistant");
  expect(reply?.parts).toContainEqual({ type: "text", content: "Partial result: verified file contents; task unfinished" });
  expect(reply?.parts).toContainEqual({ type: "text", content: "Execution deadline exceeded" });
  expect(reply).toMatchObject({ isStreaming: false, cancelled: false });
});
