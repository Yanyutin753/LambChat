/** @vitest-environment jsdom */

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";
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
  fireEvent.click(within(cardRoot as HTMLElement).getByRole("button"));

  expect(screen.queryByText("scheduled.pdf")).not.toBeInTheDocument();
  expect(cancelUpload).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: /保存|save/i }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0]?.[0].input_payload).not.toHaveProperty(
    "attachments",
  );
});
