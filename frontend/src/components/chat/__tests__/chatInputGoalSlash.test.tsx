/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState, type ComponentProps } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ChatInput } from "../ChatInput";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({
    uploadFiles: vi.fn(),
    uploadFile: vi.fn(),
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));
vi.mock("../ChatInputSelectors", () => ({
  ChatInputSelectors: () => null,
}));

beforeEach(() => localStorage.setItem("newlineModifier", "enter"));
afterEach(() => localStorage.removeItem("newlineModifier"));

function GoalComposer({
  draft,
  onSend,
  initiallyEnabled = false,
}: {
  draft: string;
  onSend: ComponentProps<typeof ChatInput>["onSend"];
  initiallyEnabled?: boolean;
}) {
  const [goalEnabled, setGoalEnabled] = useState(initiallyEnabled);
  return (
    <ChatInput
      onSend={onSend}
      onStop={() => {}}
      isLoading={false}
      pendingInput={draft}
      goalModeEnabled={goalEnabled}
      onToggleGoalMode={setGoalEnabled}
    />
  );
}

test.each([
  { selection: "Enter", draft: "/goal", initiallyEnabled: false },
  { selection: "Tab", draft: "/go", initiallyEnabled: false },
  { selection: "pointer", draft: "/goal", initiallyEnabled: false },
  { selection: "Enter", draft: "/goal", initiallyEnabled: true },
])(
  "$selection selects $draft and enables Goal (already on: $initiallyEnabled)",
  async ({ selection, draft, initiallyEnabled }) => {
    const onSend = vi.fn();
    const { rerender } = render(
      <GoalComposer
        draft={draft}
        onSend={onSend}
        initiallyEnabled={initiallyEnabled}
      />,
    );
    const editor = await screen.findByRole("textbox");
    expect(
      await screen.findByRole("listbox", { name: "Slash commands" }),
    ).toBeVisible();

    if (selection === "pointer") {
      fireEvent.mouseDown(screen.getByRole("option", { name: /Goal/ }));
    } else {
      fireEvent.keyDown(editor, { key: selection });
    }

    expect(screen.getByRole("button", { name: "Clear Goal" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(editor.textContent).toBe("");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onSend).not.toHaveBeenCalled();

    rerender(<GoalComposer draft="完成发布检查" onSend={onSend} />);
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledWith(
      "完成发布检查",
      {},
      [],
      { runModes: ["goal"] },
      expect.any(Object),
    );
  },
);
