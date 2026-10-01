/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PersonaPresetCard } from "../PersonaPresetCard";
import type { PersonaPreset } from "../../../types";
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("restored card keeps use, edit and pin actions available", () => {
  const preset = {
    id: "role-1",
    name: "Research",
    scope: "user",
    tags: [],
    skill_names: [],
    description: "Research assistant",
    usage_count: 0,
  } as unknown as PersonaPreset;
  const onUse = vi.fn();
  const onEdit = vi.fn();
  const onTogglePreference = vi.fn();
  render(
    <PersonaPresetCard
      preset={preset}
      selected={false}
      activeTag={null}
      canWrite
      canAdmin={false}
      onUse={onUse}
      onClear={vi.fn()}
      onCopy={vi.fn()}
      onEdit={onEdit}
      onDelete={vi.fn()}
      onToggleTag={vi.fn()}
      onTogglePreference={onTogglePreference}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.use" }));
  expect(onUse).toHaveBeenCalledWith(preset);
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.edit" }));
  expect(onEdit).toHaveBeenCalledWith(preset);
  fireEvent.click(screen.getByRole("button", { name: "personaPresets.pin" }));
  expect(onTogglePreference).toHaveBeenCalledWith(preset, { is_pinned: true });
});
