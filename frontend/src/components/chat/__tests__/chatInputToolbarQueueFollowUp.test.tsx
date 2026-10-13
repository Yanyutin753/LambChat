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

test("continuing in background invokes navigation without stopping the run", () => {
  const onContinueInBackground = vi.fn();
  const onStopClick = vi.fn();
  const view = render(<ChatInputToolbar {...baseProps} hasDraft={false} onContinueInBackground={onContinueInBackground} onStopClick={onStopClick} />);
  fireEvent.click(view.getByTestId("continue-in-background"));
  expect(onContinueInBackground).toHaveBeenCalledTimes(1);
  expect(onStopClick).not.toHaveBeenCalled();
  fireEvent.click(view.getByRole("button", { name: /Stop|chat.stop/i }));
  expect(onStopClick).toHaveBeenCalledTimes(1);
});

test("background continuation has no entry when idle or unavailable", () => {
  const view = render(<ChatInputToolbar {...baseProps} isLoading={false} onContinueInBackground={vi.fn()} />);
  expect(view.queryByTestId("continue-in-background")).toBeNull();
});

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


test("active run modes sit beside the desktop model selector and stay hidden on phones", () => {
  const onToggleAutoMode = vi.fn();
  const onToggleGoalMode = vi.fn();
  const { container } = render(
    <ChatInputToolbar
      {...baseProps}
      autoModeEnabled
      goalModeEnabled
      onToggleAutoMode={onToggleAutoMode}
      onToggleGoalMode={onToggleGoalMode}
    />,
  );
  const modes = container.querySelector("[data-composer-run-modes]");
  expect(modes).not.toBeNull();
  const buttons = modes!.querySelectorAll("button");
  expect(buttons).toHaveLength(2);
  expect(modes!.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(2);
  expect(buttons[0].textContent).toContain("Auto");
  expect(buttons[1].textContent).toContain("Goal");
  expect(modes!.closest(".chat-input-toolbar")).not.toBeNull();
  expect(modes!.className).toContain("hidden");
  expect(modes!.className).toContain("sm:flex");
  expect(container.querySelector("[data-run-mode-trigger] [data-run-mode-status-dot]")).not.toBeNull();
  fireEvent.click(buttons[0]);
  fireEvent.click(buttons[1]);
  expect(onToggleAutoMode).toHaveBeenCalledWith(false);
  expect(onToggleGoalMode).toHaveBeenCalledWith(false);
});

test("inactive run modes do not reserve an empty row", () => {
  const { container } = render(<ChatInputToolbar {...baseProps} />);
  expect(container.querySelector("[data-composer-run-modes]")).toBeNull();
  expect(container.querySelector("[data-run-mode-status-dot]")).toBeNull();
});


test("one active desktop mode only shows the separator after the model", () => {
  const { container } = render(
    <ChatInputToolbar {...baseProps} goalModeEnabled />,
  );
  const modes = container.querySelector("[data-composer-run-modes]");
  expect(modes!.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(1);
});
