/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { EnvVarItem } from "../EnvVarItem";
import { ScheduledTaskItem } from "../ScheduledTaskItem";
import { openToolLivePanel } from "../ToolLivePanelContent";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../common", async () => ({
  CopyButton: (await import("../../../../common/CopyButton")).CopyButton,
  CollapsiblePill: ({ onPanelOpen }: { onPanelOpen: () => void }) => (
    <button onClick={onPanelOpen}>Open</button>
  ),
}));
vi.mock("../ToolLivePanelContent", () => ({ openToolLivePanel: vi.fn() }));
vi.mock("../useToolStreamingLabel", () => ({
  useToolStreamingLabel: (label: string) => ({ label }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function openDetail(item: ReactNode) {
  render(item);
  fireEvent.click(screen.getByText("Open"));
  const panel = vi.mocked(openToolLivePanel).mock.calls[0][0];
  return render(panel.fallback as ReactNode);
}

test("deleted variables show their result and full key without pretending a masked value remains", () => {
  const key = "SIDEBAR_ACCEPTANCE_DELETE_SINGLE_WITH_A_LONG_KEY";
  const message = `Environment variable '${key}' deleted`;
  openDetail(
    <EnvVarItem
      toolName="env_var_delete"
      args={{ key }}
      success
      result={JSON.stringify({ success: true, message })}
    />,
  );
  expect(screen.getAllByText(message)).toHaveLength(1);
  expect(screen.getByText(key)).toBeTruthy();
  expect(screen.queryByText("••••••••")).toBeNull();
  expect(screen.queryByText("chat.message.envMasked")).toBeNull();
  expect(
    screen.getAllByRole("button", { name: "chat.message.copy" }).length,
  ).toBeGreaterThan(0);
});

test("clear-all results display one readable confirmation with a copy control", () => {
  const message = "Deleted 2 environment variable(s)";
  const result = JSON.stringify({ success: true, message, deleted_count: 2 });
  openDetail(
    <EnvVarItem
      toolName="env_var_delete_all"
      args={{}}
      success
      result={result}
    />,
  );
  expect(screen.getAllByText(message)).toHaveLength(1);
  expect(screen.queryByText(result)).toBeNull();
  expect(
    screen.getByRole("button", { name: "chat.message.copy" }),
  ).toBeTruthy();
});

test("failed variable deletion keeps its error visible without showing a stored masked variable", () => {
  const message = "Environment variable 'MISSING_KEY' not found";
  openDetail(
    <EnvVarItem
      toolName="env_var_delete"
      args={{ key: "MISSING_KEY" }}
      success={false}
      result={JSON.stringify({ error: message })}
    />,
  );
  expect(screen.getByRole("alert").textContent).toContain(message);
  expect(screen.queryByText("••••••••")).toBeNull();
});

test("variable lists still expose only keys and masked values", () => {
  openDetail(
    <EnvVarItem
      toolName="env_var_list"
      args={{}}
      success
      result={JSON.stringify({
        variables: [{ key: "API_ENDPOINT", value: "must-stay-private" }],
        count: 1,
      })}
    />,
  );
  expect(screen.getByText("API_ENDPOINT")).toBeTruthy();
  expect(screen.getByText("••••••••")).toBeTruthy();
  expect(screen.queryByText("must-stay-private")).toBeNull();
});

test("task deletion shows its confirmation once instead of duplicate JSON", () => {
  const message = "Task 'A real acceptance task' deleted.";
  const result = JSON.stringify({
    success: true,
    action: "deleted",
    task_id: "task-1",
    message,
  });
  openDetail(
    <ScheduledTaskItem
      toolName="scheduled_task_delete"
      args={{ task_id: "task-1" }}
      success
      result={result}
    />,
  );
  expect(screen.getAllByText(message)).toHaveLength(1);
  expect(screen.queryByText(result)).toBeNull();
  expect(
    screen.getByRole("button", { name: "chat.message.copy" }),
  ).toBeTruthy();
});

test("task prompts have their own label and remain copyable after an update", () => {
  const prompt = "Keep this isolated task disabled.";
  openDetail(
    <ScheduledTaskItem
      toolName="scheduled_task_update"
      args={{ task_id: "task-1" }}
      success
      result={JSON.stringify({
        success: true,
        task: {
          id: "task-1",
          name: "Updated task",
          enabled: false,
          input_payload: { message: prompt },
        },
        message: "Task updated.",
      })}
    />,
  );
  expect(
    screen.getByRole("button", { name: "chat.message.toolTaskPrompt" }),
  ).toBeTruthy();
  expect(screen.getByText(prompt)).toBeTruthy();
  expect(
    screen.getAllByRole("button", { name: "chat.message.copy" }).length,
  ).toBeGreaterThan(0);
});

test("one-off tasks retain their actual scheduled date instead of a duplicate once label", () => {
  openDetail(
    <ScheduledTaskItem
      toolName="scheduled_task_update"
      args={{}}
      success
      result={JSON.stringify({
        success: true,
        task: {
          id: "task-1",
          name: "Scheduled task",
          trigger_type: "date",
          trigger_config: { run_date: "2040-01-01T00:00:00+00:00" },
          enabled: false,
        },
      })}
    />,
  );
  expect(screen.getByText("2040-01-01T00:00:00+00:00")).toBeTruthy();
});
