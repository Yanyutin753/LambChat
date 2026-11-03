/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import type { ScheduledTask } from "../../../../types/scheduledTask";

const { cancelUpload } = vi.hoisted(() => ({ cancelUpload: vi.fn() }));

vi.mock("../../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({ cancelUpload }),
}));

vi.mock("../../../chat/FileUploadButton", () => ({
  FileUploadButton: () => null,
}));

vi.mock("../../../../services/api/personaPreset", () => ({
  personaPresetApi: {
    list: vi.fn().mockResolvedValue({ presets: [] }),
  },
}));

vi.mock("../../../../services/api/team", () => ({
  teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
}));

vi.mock("../../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <div>
      {children}
      {footer}
    </div>
  ),
}));

import { TaskFormModal } from "../TaskFormModal";
afterEach(cleanup);

const task: ScheduledTask = {
  id: "task-1",
  name: "Attachment task",
  description: null,
  agent_id: "default",
  trigger_type: "interval",
  trigger_config: { seconds: 300 },
  timezone: "Asia/Shanghai",
  input_payload: {
    attachments: [
      {
        id: "scheduled-attachment",
        key: "uploads/scheduled.pdf",
        name: "scheduled.pdf",
        type: "document",
        mimeType: "application/pdf",
        size: 1024,
      },
    ],
  },
  status: "active",
  enabled: true,
  run_on_start: false,
  max_retries: 0,
  timeout_seconds: 600,
  owner_id: "owner-1",
  source_session_id: null,
  source_run_id: null,
  created_by: "user",
  last_run_at: null,
  last_run_status: null,
  last_run_id: null,
  total_runs: 0,
  unread_count: 0,
  created_at: null,
  updated_at: null,
};

test("plain instructions edit legacy prompts without losing custom payload or schedule fields", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={{
        ...task,
        trigger_type: "cron",
        trigger_config: { hour: "9", minute: "0", year: "2027" },
        input_payload: { prompt: "Old instructions", custom: { keep: true } },
      }}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.change(
    screen.getByLabelText(i18n.t("chat.message.toolTaskPrompt")),
    { target: { value: "Check the release and report only changes" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].input_payload).toEqual({
    prompt: "Check the release and report only changes",
    custom: { keep: true },
  });
  expect(onSave.mock.calls[0][0].trigger_config.year).toBe("2027");
});

test("advanced payload rejects arrays instead of silently turning them into objects", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.change(
    screen.getByLabelText(i18n.t("scheduledTask.inputPayload")),
    { target: { value: "[]" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(onSave).not.toHaveBeenCalled();
});

test("scheduled-task uploaded attachment removal is local and omitted on save", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[
        {
          id: "default",
          name: "Default",
          description: "Default agent",
          version: "1",
        },
      ]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );

  const card = await screen.findByText("scheduled.pdf");
  const cardRoot = card.closest(".attachment-card-enter");
  expect(cardRoot).not.toBeNull();
  fireEvent.click(
    within(cardRoot as HTMLElement).getByRole("button", {
      name: i18n.t("common.remove"),
    }),
  );

  expect(screen.queryByText("scheduled.pdf")).not.toBeInTheDocument();
  expect(cancelUpload).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0]?.[0].input_payload).not.toHaveProperty(
    "attachments",
  );
});

test("task configuration fields and trigger choices have accessible names and states", async () => {
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  await screen.findByText("scheduled.pdf");
  for (const key of [
    "name",
    "description",
    "interval",
    "inputPayload",
    "maxRetries",
  ]) {
    expect(screen.getByLabelText(i18n.t(`scheduledTask.${key}`))).toBeTruthy();
  }
  for (const key of ["agent", "persona", "model"]) {
    expect(
      screen.getByRole("button", { name: i18n.t(`scheduledTask.${key}`) }),
    ).toBeTruthy();
  }
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("scheduledTask.triggerType") }),
  );
  fireEvent.click(
    screen.getByRole("option", {
      name: i18n.t("scheduledTask.cron"),
      exact: true,
    }),
  );
  expect(
    screen.getByRole("button", { name: i18n.t("scheduledTask.triggerType") }),
  ).toHaveTextContent(i18n.t("scheduledTask.cron"));
  for (const key of [
    "cronHour",
    "cronMinute",
    "cronSecond",
    "cronDay",
    "cronMonth",
    "cronDayOfWeek",
  ]) {
    expect(screen.getByLabelText(i18n.t(`scheduledTask.${key}`))).toBeTruthy();
  }
});

test("a chat-created schedule defaults to continuing the current conversation", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={null}
      defaultSessionId="chat-1"
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText(i18n.t("scheduledTask.name")), {
    target: { value: "Follow up" },
  });
  expect(
    screen.getByText(i18n.t("scheduledTask.inheritContext")),
  ).toBeInTheDocument();
  expect(
    screen.queryByLabelText(i18n.t("scheduledTask.agent")),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0]).toMatchObject({
    execution_mode: "conversation",
    target_session_id: "chat-1",
    notification_policy: "meaningful_changes",
  });
});

test("legacy task editing shows no execution deadline and saves unlimited duration", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  await screen.findByText("scheduled.pdf");
  expect(
    screen.queryByRole("spinbutton", {
      name: i18n.t("scheduledTask.timeoutSeconds"),
    }),
  ).toBeNull();
  expect(screen.getByText(i18n.t("scheduledTask.noTimeLimit"))).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].timeout_seconds).toBe(0);
});

test("calendar presets save weekdays at the chosen local time", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("scheduledTask.triggerType") }),
  );
  fireEvent.click(
    screen.getByRole("option", {
      name: i18n.t("scheduledTask.weekdays"),
      exact: true,
    }),
  );
  fireEvent.change(screen.getByLabelText(i18n.t("scheduledTask.timeOfDay")), {
    target: { value: "14:35" },
  });
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0]).toMatchObject({
    trigger_type: "cron",
    trigger_config: {
      hour: "14",
      minute: "35",
      second: "0",
      day_of_week: "mon-fri",
    },
    timezone: "Asia/Shanghai",
  });
});

test("interval editing presents minutes and saves seconds", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByLabelText(i18n.t("scheduledTask.interval"))).toHaveValue(
    5,
  );
  fireEvent.change(screen.getByLabelText(i18n.t("scheduledTask.interval")), {
    target: { value: "10" },
  });
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].trigger_config).toEqual({ seconds: 600 });
});

test("invalid intervals do not silently become a default interval", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  await screen.findByText("scheduled.pdf");
  fireEvent.change(screen.getByLabelText(i18n.t("scheduledTask.interval")), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  expect(onSave).not.toHaveBeenCalled();
});

test("clearing instructions cannot revive a legacy prompt alias", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={{
        ...task,
        input_payload: {
          message: "Current instructions",
          prompt: "Obsolete instructions",
          custom: true,
        },
      }}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.change(
    screen.getByLabelText(i18n.t("chat.message.toolTaskPrompt")),
    { target: { value: "" } },
  );
  expect(
    screen.getByLabelText(i18n.t("chat.message.toolTaskPrompt")),
  ).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].input_payload).toEqual({
    message: "",
    custom: true,
  });
});

test("editing a legacy sub-minute interval preserves its configured cadence", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={{ ...task, trigger_config: { seconds: 30 } }}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].trigger_config).toEqual({ seconds: 30 });
});

test("name validation remains visible and focuses the missing field", async () => {
  const onSave = vi.fn();
  render(
    <TaskFormModal
      task={null}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("scheduledTask.nameRequired"),
  );
  expect(screen.getByLabelText(i18n.t("scheduledTask.name"))).toHaveFocus();
  expect(onSave).not.toHaveBeenCalled();
});

test("keyboard save locks editing and cancellation until the request settles", async () => {
  let finish!: () => void;
  const onSave = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const onClose = vi.fn();
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={onClose}
    />,
  );
  const name = screen.getByLabelText(i18n.t("scheduledTask.name"));
  fireEvent.keyDown(name, { key: "Enter", ctrlKey: true, isComposing: true });
  expect(onSave).not.toHaveBeenCalled();
  fireEvent.keyDown(name, { key: "Enter", ctrlKey: true });
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(name).toBeDisabled();
  const cancel = screen.getByRole("button", { name: i18n.t("common.cancel") });
  expect(cancel).toBeDisabled();
  fireEvent.click(cancel);
  expect(onClose).not.toHaveBeenCalled();
  fireEvent.keyDown(name, { key: "Enter", metaKey: true });
  expect(onSave).toHaveBeenCalledOnce();
  await act(async () => finish());
  expect(name).not.toBeDisabled();
});

test("save failures stay visible and allow retry with the same draft", async () => {
  const onSave = vi
    .fn()
    .mockRejectedValueOnce(new Error("Network unavailable"))
    .mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={task}
      agents={[]}
      availableModels={null}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Network unavailable",
  );
  expect(screen.getByLabelText(i18n.t("scheduledTask.name"))).toHaveValue(
    task.name,
  );
  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
});

test("calendar time and weekday survive temporary changes to another schedule type", async () => {
  render(
    <TaskFormModal
      task={{
        ...task,
        trigger_type: "cron",
        trigger_config: { hour: "14", minute: "35", day_of_week: "fri" },
      }}
      agents={[]}
      availableModels={null}
      onSave={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  for (const preset of ["interval", "daily", "weekly"]) {
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("scheduledTask.triggerType") }),
    );
    fireEvent.click(
      screen.getByRole("option", {
        name: i18n.t(`scheduledTask.${preset}`),
        exact: true,
      }),
    );
  }
  expect(screen.getByLabelText(i18n.t("scheduledTask.timeOfDay"))).toHaveValue(
    "14:35",
  );
  expect(
    screen.getByRole("button", { name: i18n.t("scheduledTask.cronDayOfWeek") }),
  ).toHaveTextContent(i18n.t("scheduledTask.weekday.fri"));
});
