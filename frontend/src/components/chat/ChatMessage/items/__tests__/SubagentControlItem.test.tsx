/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  waitFor,
  within,
} from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import en from "../../../../../i18n/locales/en.json";
import { SubagentControlItem } from "../SubagentControlItem";
import { toolCallPanelStore } from "../../toolCallPanelStore";
import { subagentPanelStore } from "../../subagentPanelStore";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
  toolCallPanelStore.clear();
  subagentPanelStore.clear();
});

function show(props: React.ComponentProps<typeof SubagentControlItem>) {
  return render(
    <I18nextProvider i18n={i18n}>
      <SubagentControlItem {...props} />
    </I18nextProvider>,
  );
}

test.each([
  ["running", "Message queued", "success"],
  ["completed", "Completed", "success"],
  ["waiting_human", "Waiting for human input", "idle"],
  ["failed", "Failed", "error"],
  ["error", "Failed", "error"],
  ["cancelled", "Cancelled", "cancelled"],
])("message results expose subagent state %s", (state, label, pillStatus) => {
  const view = show({
    toolName: "send_subagent_message",
    args: { subagent_id: "agent-1", message: "Continue the review" },
    result: JSON.stringify({ subagent_id: "agent-1", status: state }),
    success: true,
  });
  const button = view.getByRole("button");
  expect(button.textContent).toContain("Message subagent");
  expect(button.textContent).not.toContain("agent-1");
  expect(button.textContent).toContain(label);
  fireEvent.click(button);
  expect(getPersistentToolPanelState()?.status).toBe(pillStatus);
});

test("pending wait opens its live panel and receives the final report", async () => {
  const view = show({
    id: "wait-1",
    toolName: "wait_subagent",
    args: { subagent_id: "agent-1" },
    isPending: true,
  });
  fireEvent.click(view.getByRole("button"));
  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBe("tool:wait-1");
  expect(state?.title).toBe("Wait for subagent");
  expect(state?.status).toBe("loading");
  const panel = render(
    <I18nextProvider i18n={i18n}>{state!.children}</I18nextProvider>,
  );
  act(() =>
    toolCallPanelStore.set({
      toolCallId: "wait-1",
      toolName: "wait_subagent",
      formattedToolName: "Wait for subagent",
      args: { subagent_id: "agent-1" },
      result: JSON.stringify({
        subagent_id: "agent-1",
        status: "completed",
        result: "Final review retained the previous context",
        report_path: "/reports/agent-1.md",
      }),
      success: true,
      isPending: false,
      status: "success",
    }),
  );
  await waitFor(() =>
    expect(within(panel.container).getByText(/Final review/)).toBeTruthy(),
  );
  expect(panel.container.textContent).not.toContain('"status"');
  expect(panel.container.textContent).not.toContain('"subagent_id"');
});

test("a wait awakened by child mail shows the received message instead of running", () => {
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: "agent-1" },
    result: JSON.stringify({
      subagent_id: "agent-1",
      status: "running",
      messages_pending: true,
    }),
    success: true,
  });
  const button = view.getByRole("button");
  expect(button.textContent).toContain("Message from subagent");
  expect(button.textContent).not.toContain("Running");
  fireEvent.click(button);
  expect(getPersistentToolPanelState()?.status).toBe("success");
});

test("malformed historical results remain visible without throwing", () => {
  const view = show({
    toolName: "send_subagent_message",
    args: { subagent_id: "agent-1", message: "Continue" },
    result: "unstructured result",
    success: false,
  });
  fireEvent.click(view.getByRole("button"));
  expect(getPersistentToolPanelState()?.status).toBe("error");
});

test("completed waits show the subagent reply without opening a panel", () => {
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: "subagent-demo-role-a-long-historical-id" },
    result: JSON.stringify({
      subagent_id: "subagent-demo-role-a-long-historical-id",
      status: "completed",
      result: "QC-DEMO-42: Permissions review completed",
    }),
    success: true,
  });
  expect(
    view.getByText("QC-DEMO-42: Permissions review completed"),
  ).toBeTruthy();
  expect(view.getByRole("button").textContent).toContain("Completed");
});

test("a resumed subagent reply is visible and pending calls hide stale replies", () => {
  const props = {
    toolName: "send_subagent_message",
    args: { subagent_id: "agent-1", message: "Continue" },
    result: JSON.stringify({ status: "completed", result: "Context retained" }),
    success: true,
  };
  const view = show(props);
  expect(view.getByText("Context retained")).toBeTruthy();
  view.rerender(
    <I18nextProvider i18n={i18n}>
      <SubagentControlItem {...props} isPending />
    </I18nextProvider>,
  );
  expect(view.queryByText("Context retained")).toBeNull();
  expect(view.getByRole("button").textContent).not.toContain("Completed");
});

test("failed continuations show the error without opening a panel", () => {
  const view = show({
    toolName: "send_subagent_message",
    args: { subagent_id: "agent-1", message: "Continue" },
    result: JSON.stringify({
      status: "error",
      error: "Role access was revoked",
    }),
    success: false,
  });
  expect(view.getByText("Role access was revoked")).toBeTruthy();
});

test("pending waits hide technical IDs even while arguments stream", async () => {
  const subagentId = "subagent-d7ec05ee9b0c8dee667b7c37";
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: subagentId },
    isPending: true,
  });
  await waitFor(() =>
    expect(view.getByRole("button").textContent).toContain("Wait for subagent"),
  );
  expect(view.getByRole("button").textContent).not.toContain(subagentId);
});

test.each(["send_subagent_message", "wait_subagent"])(
  "%s opens the same named subagent conversation",
  (toolName) => {
    subagentPanelStore.set({
      agentId: "agent-1",
      agentName: "API contract reviewer",
      input: "Review permissions",
      result: "A report",
      status: "complete",
      success: true,
    });
    const view = show({
      id: "control-1",
      toolName,
      args: { subagent_id: "agent-1", message: "Continue" },
      result: JSON.stringify({
        subagent_id: "agent-1",
        status: "completed",
        result: "A report",
      }),
      success: true,
    });
    expect(view.getByRole("button").textContent).toContain(
      "API contract reviewer",
    );
    expect(view.getByRole("button").textContent).not.toContain("agent-1");
    expect(view.getByText("A report")).toBeTruthy();
    fireEvent.click(view.getByRole("button"));
    expect(getPersistentToolPanelState()?.panelKey).toBe("subagent-agent-1");
    expect(getPersistentToolPanelState()?.title).toBe("API contract reviewer");
  },
);

test("a role name arriving after the control item updates its label", () => {
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: "agent-1" },
    isPending: true,
  });
  act(() =>
    subagentPanelStore.set({
      agentId: "agent-1",
      agentName: "Reviewer",
      input: "Check",
      status: "running",
    }),
  );
  expect(view.getByRole("button").textContent).toContain("Reviewer");
});

test("cancelled continuations hide stale failure text", () => {
  const view = show({
    toolName: "send_subagent_message",
    args: { subagent_id: "agent-1", message: "Continue" },
    result: JSON.stringify({ status: "error", error: "Previous run failed" }),
    success: false,
    cancelled: true,
  });
  expect(view.getByRole("button").textContent).toContain("Cancelled");
  expect(view.queryByText("Previous run failed")).toBeNull();
});

test.each([
  ["received", "Message from subagent"],
  ["sent", "Message parent agent"],
])(
  "parent communication shows %s with the readable original message",
  (direction, label) => {
    subagentPanelStore.set({
      agentId: "agent-1",
      agentName: "Reviewer",
      input: "Review",
      status: "running",
    });
    const view = show({
      toolName: "send_parent_message",
      args: { subagent_id: "agent-1", message: "Need scope", direction },
      result: JSON.stringify({ subagent_id: "agent-1", status: "queued" }),
      success: true,
    });
    expect(view.getByRole("button").textContent).toContain(label);
    expect(view.getByText("Need scope")).toBeTruthy();
    fireEvent.click(view.getByRole("button"));
    expect(getPersistentToolPanelState()?.panelKey).toBe("subagent-agent-1");
    expect(view.container.textContent).not.toContain('"subagent_id"');
  },
);

test.each([
  ["cancel_subagent", "chat.message.toolCancelSubagent"],
  ["list_subagents", "chat.message.toolListSubagents"],
])("%s exposes its dedicated control action", (toolName, titleKey) => {
  const view = show({
    toolName,
    args: { subagent_id: "agent-1" },
    result: JSON.stringify({ subagent_id: "agent-1", status: "cancelled", subagents: [] }),
    success: true,
  });
  expect(view.getByRole("button").textContent).toContain(i18n.t(titleKey));
});

test("queued wait results stay idle instead of claiming success", () => {
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: "agent-1" },
    result: JSON.stringify({ subagent_id: "agent-1", status: "queued" }),
    success: true,
  });
  fireEvent.click(view.getByRole("button"));
  expect(getPersistentToolPanelState()?.status).toBe("idle");
});


test.each([
  ["complete", "Completed"],
  ["error", "Failed"],
  ["cancelled", "Cancelled"],
  ["timed_out", "Timed out"],
] as const)("expired waits follow the same execution's %s status", (status, label) => {
  const startedAt = Date.parse("2026-10-14T12:25:00Z");
  const child = {
    agentId: "agent-1", agentName: "Reviewer", input: "Review",
    startedAt, status: "running" as const, isPending: true,
  };
  subagentPanelStore.set(child);
  const view = show({
    toolName: "wait_subagent",
    args: { subagent_id: "agent-1" },
    result: JSON.stringify({ subagent_id: "agent-1", status: "running", wait_timed_out: true }),
    success: true,
    completedAt: "2026-10-14T12:32:27Z",
  });
  expect(view.getByRole("button").textContent).toContain("Running");
  act(() => subagentPanelStore.set({ ...child, status, isPending: false, completedAt: startedAt + 480_000 }));
  expect(view.getByRole("button").textContent).toContain(label);
  expect(view.getByRole("button").textContent).not.toContain("Running");
});

test("history replay resolves an old wait from its own run after a later continuation", () => {
  const first = {
    type: "subagent" as const, agent_id: "agent-1", agent_name: "Reviewer",
    input: "First review", depth: 1, status: "complete" as const,
    startedAt: Date.parse("2026-10-14T12:25:00Z"),
    completedAt: Date.parse("2026-10-14T12:32:55Z"),
    result: "First report",
  };
  const later = { ...first, input: "Second review", status: "error" as const,
    startedAt: Date.parse("2026-10-14T13:00:00Z"),
    completedAt: Date.parse("2026-10-14T13:05:00Z"),
  };
  subagentPanelStore.set({ agentId: "agent-1", agentName: "Reviewer", input: later.input,
    status: later.status, startedAt: later.startedAt, history: [first, later],
  });
  const view = show({
    toolName: "wait_subagent", args: { subagent_id: "agent-1" },
    result: JSON.stringify({ subagent_id: "agent-1", status: "running", wait_timed_out: true }),
    success: true, completedAt: "2026-10-14T12:32:27Z",
  });
  expect(view.getByRole("button").textContent).toContain("Completed");
  expect(view.getByRole("button").textContent).not.toContain("Failed");
  expect(view.queryByText("First report")).toBeNull();
});

test("a pending continuation does not inherit the previous execution's terminal state", () => {
  subagentPanelStore.set({ agentId: "agent-1", agentName: "Reviewer", input: "Previous",
    status: "complete", result: "Previous report", completedAt: Date.parse("2026-10-14T12:00:00Z"),
  });
  const view = show({toolName: "wait_subagent", args: {subagent_id: "agent-1"}, isPending: true});
  expect(view.getByRole("button").textContent).not.toContain("Completed");
  expect(view.queryByText("Previous report")).toBeNull();
});
