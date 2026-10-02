/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PersonaPresetSelector } from "../PersonaPresetSelector";
import type { PersonaPreset } from "../../../types";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../PersonaPreviewSidebar", () => ({
  PersonaPreviewSidebar: () => (
    <div role="dialog" aria-label="Persona preview" />
  ),
}));
afterEach(cleanup);

const preset: PersonaPreset = {
  id: "analyst",
  name: "Analyst",
  description: "Analysis",
  system_prompt: "Prompt",
  tags: ["Research"],
  scope: "global",
  visibility: "public",
  status: "published",
  skill_names: [],
  mcp_server_names: [],
  version: 1,
  usage_count: 0,
  created_at: "",
  updated_at: "",
};
const props = {
  presets: [preset],
  isOpen: true,
  onOpenChange: vi.fn(),
  onUsePreset: async () => null,
  onCopyPreset: vi.fn(async () => undefined),
  onClearPreset: vi.fn(),
};

test("persona preview has a native keyboard entry separate from copy and preference actions", () => {
  const toggle = vi.fn(async () => undefined);
  render(<PersonaPresetSelector {...props} onTogglePreference={toggle} />);
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.copy" }));
  expect(screen.queryByRole("dialog", { name: "Persona preview" })).toBeNull();
  expect(props.onCopyPreset).toHaveBeenCalledWith(preset);
  const pin = screen.getByRole("button", { name: "personaPresets.pin" });
  expect(pin.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(pin);
  expect(toggle).toHaveBeenCalledWith(preset, { is_pinned: true });
  fireEvent.click(screen.getByRole("button", { name: "Analyst", exact: true }));
  expect(screen.getByRole("dialog", { name: "Persona preview" })).toBeTruthy();
});

test("persona selector names close and exposes selected filters with a distinct no-match state", () => {
  render(<PersonaPresetSelector {...props} />);
  expect(screen.getByRole("button", { name: "common.close" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Research" }));
  expect(
    screen
      .getByRole("button", { name: "Research" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "No match" },
  });
  expect(screen.getByText("personaPresets.noMatch")).toBeTruthy();
});

test("persona load errors remain visible and retry the current list", () => {
  const retry = vi.fn();
  render(
    <PersonaPresetSelector {...props} error="Unable to load" onRetry={retry} />,
  );
  expect(screen.getByRole("alert").textContent).toContain("Unable to load");
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(retry).toHaveBeenCalledOnce();
});

test("a persona list shrinking to one page corrects a previously selected later page", () => {
  const change = vi.fn();
  render(
    <PersonaPresetSelector
      {...props}
      page={4}
      total={1}
      onPageChange={change}
    />,
  );
  expect(
    screen.getByRole("navigation", { name: "common.pagination" }),
  ).toBeTruthy();
  expect(change).toHaveBeenCalledWith(1);
});
