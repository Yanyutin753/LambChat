/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { PersonaPreviewSidebar } from "../PersonaPreviewSidebar";
import type { PersonaPreset } from "../../../types";

const preset: PersonaPreset = {
  id: "research",
  scope: "global",
  name: "Research",
  description: "Research assistant",
  tags: ["research"],
  system_prompt:
    "# Notes\n\nKeep every source: https://example.com/long-original-reference\n",
  skill_names: [],
  mcp_server_names: [],
  visibility: "public",
  status: "published",
  version: 1,
  usage_count: 120,
  created_at: "2026-10-01",
  updated_at: "2026-10-01",
};
const props = {
  isSelected: false,
  isMutating: false,
  isUsingPreset: false,
  onClose: vi.fn(),
  onUsePreset: vi.fn(),
  onCopyPreset: vi.fn(),
};
beforeEach(() => resetRightPanelCoordinator());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test.each(["global", "user"] as const)(
  "%s persona preview displays scope and usage in its content",
  (scope) => {
    render(<PersonaPreviewSidebar preset={{ ...preset, scope }} {...props} />);
    const content = within(screen.getByRole("tabpanel", { name: preset.name }));
    expect(
      content.getByText(
        i18n.t(
          scope === "global"
            ? "personaPresets.official"
            : "personaPresets.mine",
        ),
      ),
    ).toBeInTheDocument();
    expect(
      content.getByText(`120 ${i18n.t("personaPresets.usageCount")}`),
    ).toBeInTheDocument();
  },
);

test("source mode announces its selection and copies the unchanged original prompt", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  render(<PersonaPreviewSidebar preset={preset} {...props} />);
  const toggle = screen.getByRole("button", {
    name: i18n.t("personaPresets.viewSource"),
  });
  expect(toggle).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(toggle);
  expect(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.previewMarkdown"),
    }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(document.querySelector("pre")?.textContent).toBe(preset.system_prompt);
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("chat.message.copy"),
      exact: true,
    }),
  );
  await waitFor(() =>
    expect(writeText).toHaveBeenCalledWith(preset.system_prompt),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.previewMarkdown"),
    }),
  );
  expect(screen.getByRole("heading", { name: "Notes" })).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.viewSource") }),
  ).toHaveAttribute("aria-pressed", "false");
});
