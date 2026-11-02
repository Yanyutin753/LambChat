/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";

vi.mock("../../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({ cancelUpload: vi.fn() }),
}));

vi.mock("../../../chat/FileUploadButton", () => ({
  FileUploadButton: () => null,
}));

vi.mock("../../../../services/api/personaPreset", () => ({
  personaPresetApi: { list: vi.fn().mockResolvedValue({ presets: [] }) },
}));

vi.mock("../../../../services/api/team", () => ({
  teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
}));

vi.mock("../../../../services/api/session", () => ({
  sessionApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: "quick-chat",
        agent_id: "quick",
        name: "Quick chat",
        created_at: "2026-10-16T00:00:00Z",
        updated_at: "2026-10-16T00:00:00Z",
        is_active: true,
        unread_count: 0,
      },
    ]),
  },
}));

import { TaskFormModal } from "../TaskFormModal";
afterEach(cleanup);

test("conversation mode refuses to save when the target session runs the quick agent", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskFormModal
      task={null}
      agents={[
        { id: "quick", name: "Everyday", description: "quick", version: "1" },
      ]}
      availableModels={null}
      defaultSessionId="quick-chat"
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );

  const nameInput = await screen.findByLabelText(
    i18n.t("scheduledTask.name") as string,
  );
  fireEvent.change(nameInput, { target: { value: "AO3 watch" } });
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.save") as string }),
  );

  // 守卫命中：不允许提交（后端同样会以 scheduled_task_agent_unsupported 拒绝）
  expect(onSave).not.toHaveBeenCalled();
});
