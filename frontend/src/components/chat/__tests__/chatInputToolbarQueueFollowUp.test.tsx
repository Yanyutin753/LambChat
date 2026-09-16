/** @vitest-environment jsdom */

import { fireEvent, render } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("../selectors/FeatureMenu", () => ({
  FeatureMenu: () => null,
}));

vi.mock("../ComposerUsageChip", () => ({
  ComposerUsageChip: () => null,
}));

vi.mock("../RunModePopover", () => ({
  RunModePopover: () => null,
}));

vi.mock("../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({ online: false, machines: [] }),
}));

vi.mock("../../services/api/team", () => ({
  teamApi: {
    list: vi.fn(async () => ({ total: 0, teams: [] })),
  },
}));

import { ChatInputToolbar } from "../ChatInputToolbar";

const baseProps = {
  activePanel: null,
  onActivePanelChange: vi.fn(),
  canSend: true,
  sendBlocked: false,
  isLoading: true,
  hasDraft: true,
  canSubmit: false,
  hasUploadingAttachment: false,
  hasFailedAttachment: false,
  hasInvalidAttachment: false,
  enabledToolsCount: 0,
  totalToolsCount: 0,
  enabledSkillsCount: 0,
  totalSkillsCount: 0,
  hasPersonaSelector: false,
  hasAgentSelector: false,
  hasThinkingOption: false,
  uploadCategories: [],
  uploadFiles: vi.fn(),
  selectedPersonaName: null,
  personaAvatar: null,
  onStopClick: vi.fn(),
  onNoPermissionClick: vi.fn(),
};

test("shows the queue follow-up trigger while running with a draft and fires it", () => {
  const onQueueFollowUp = vi.fn();
  const { getByTestId } = render(
    <ChatInputToolbar {...baseProps} onQueueFollowUp={onQueueFollowUp} />,
  );

  fireEvent.click(getByTestId("queue-followup-trigger"));

  expect(onQueueFollowUp).toHaveBeenCalledTimes(1);
});

test("hides the queue follow-up trigger while idle", () => {
  const { queryByTestId } = render(
    <ChatInputToolbar
      {...baseProps}
      isLoading={false}
      onQueueFollowUp={vi.fn()}
    />,
  );

  expect(queryByTestId("queue-followup-trigger")).toBeNull();
});

test("hides the queue follow-up trigger without a callback", () => {
  const { queryByTestId } = render(
    <ChatInputToolbar {...baseProps} onQueueFollowUp={undefined} />,
  );

  expect(queryByTestId("queue-followup-trigger")).toBeNull();
});

test("the main send button queues while running", () => {
  const onQueueFollowUp = vi.fn();
  const { getByTestId } = render(
    <ChatInputToolbar {...baseProps} onQueueFollowUp={onQueueFollowUp} />,
  );

  fireEvent.click(getByTestId("queue-followup-trigger"));

  expect(onQueueFollowUp).toHaveBeenCalledTimes(1);
});

test("hides the running send button while idle", () => {
  const { queryByTestId } = render(
    <ChatInputToolbar
      {...baseProps}
      isLoading={false}
      onQueueFollowUp={vi.fn()}
    />,
  );

  expect(queryByTestId("queue-followup-trigger")).toBeNull();
});
