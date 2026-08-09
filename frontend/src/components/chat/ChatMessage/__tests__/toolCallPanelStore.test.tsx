/** @vitest-environment jsdom */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import type { Message } from "../../../../types";
import { ToolCallItem } from "../ToolCallItem";
import * as toolPanelModule from "../toolCallPanelStore";

const { toolCallPanelStore } = toolPanelModule;

type SyncToolPanels = (messages: readonly Message[]) => void;

function assistantMessage(parts: Message["parts"]): Message {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "",
    timestamp: new Date("2026-08-09T10:00:00.000Z"),
    parts,
  };
}

afterEach(() => {
  cleanup();
  ["tool-offscreen", "tool-stream", "tool-nested"].forEach((toolCallId) =>
    toolCallPanelStore.delete(toolCallId),
  );
});

test("keeps tool panel data when a virtualized message row unmounts", async () => {
  const view = render(
    <ToolCallItem
      id="tool-offscreen"
      name="shell"
      args={{ command: "printf done" }}
      isPending
      startedAt="2026-08-09T10:00:00.000Z"
    />,
  );

  await waitFor(() => {
    expect(toolCallPanelStore.get("tool-offscreen")).toMatchObject({
      toolCallId: "tool-offscreen",
      toolName: "shell",
      isPending: true,
      status: "loading",
    });
  });

  view.unmount();

  expect(toolCallPanelStore.get("tool-offscreen")).toMatchObject({
    toolCallId: "tool-offscreen",
    toolName: "shell",
    isPending: true,
    status: "loading",
  });
});

test("updates an off-screen pending tool with its streamed result", () => {
  const syncToolCallPanelStore = (
    toolPanelModule as typeof toolPanelModule & {
      syncToolCallPanelStore?: SyncToolPanels;
    }
  ).syncToolCallPanelStore;

  expect(syncToolCallPanelStore).toBeTypeOf("function");
  if (!syncToolCallPanelStore) return;

  syncToolCallPanelStore([
    assistantMessage([
      {
        type: "tool",
        id: "tool-stream",
        name: "shell",
        args: { command: "printf done" },
        isPending: true,
        startedAt: "2026-08-09T10:00:00.000Z",
      },
    ]),
  ]);
  const notifications: string[] = [];
  const unsubscribe = toolCallPanelStore.subscribe("tool-stream", () =>
    notifications.push("changed"),
  );

  syncToolCallPanelStore([
    assistantMessage([
      {
        type: "tool",
        id: "tool-stream",
        name: "shell",
        args: { command: "printf done" },
        result: "final output",
        success: true,
        isPending: false,
        startedAt: "2026-08-09T10:00:00.000Z",
        completedAt: "2026-08-09T10:00:01.000Z",
      },
    ]),
  ]);

  expect(toolCallPanelStore.get("tool-stream")).toEqual({
    toolCallId: "tool-stream",
    toolName: "shell",
    formattedToolName: "Shell",
    args: { command: "printf done" },
    result: "final output",
    success: true,
    isPending: false,
    cancelled: undefined,
    startedAt: "2026-08-09T10:00:00.000Z",
    completedAt: "2026-08-09T10:00:01.000Z",
    status: "success",
  });
  expect(notifications).toEqual(["changed"]);
  unsubscribe();
});

test("synchronizes tool results nested inside subagent history", () => {
  const syncToolCallPanelStore = (
    toolPanelModule as typeof toolPanelModule & {
      syncToolCallPanelStore?: SyncToolPanels;
    }
  ).syncToolCallPanelStore;

  expect(syncToolCallPanelStore).toBeTypeOf("function");
  if (!syncToolCallPanelStore) return;

  syncToolCallPanelStore([
    assistantMessage([
      {
        type: "subagent",
        agent_id: "researcher",
        agent_name: "Researcher",
        input: "find it",
        depth: 1,
        parts: [
          {
            type: "tool",
            id: "tool-nested",
            name: "docs:search_files",
            args: { partial: '{"query":"sidebar"}' },
            result: { matches: 3 },
            success: true,
            isPending: false,
          },
        ],
      },
    ]),
  ]);

  expect(toolCallPanelStore.get("tool-nested")).toMatchObject({
    toolCallId: "tool-nested",
    toolName: "search_files",
    formattedToolName: "Search Files",
    args: { query: "sidebar" },
    result: { matches: 3 },
    status: "success",
  });
});

test("clears cached tool data at the conversation lifecycle boundary", () => {
  const clear = (
    toolCallPanelStore as typeof toolCallPanelStore & {
      clear?: () => void;
    }
  ).clear;
  toolCallPanelStore.set({
    toolCallId: "tool-stream",
    toolName: "shell",
    formattedToolName: "Shell",
    args: {},
    status: "loading",
  });
  const notifications: string[] = [];
  const unsubscribe = toolCallPanelStore.subscribe("tool-stream", () =>
    notifications.push("changed"),
  );

  expect(clear).toBeTypeOf("function");
  if (!clear) return;
  clear();

  expect(toolCallPanelStore.get("tool-stream")).toBeUndefined();
  expect(notifications).toEqual(["changed"]);
  unsubscribe();
});
