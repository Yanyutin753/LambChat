/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SkillEditor } from "../SkillEditor";

vi.mock("../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("Tab leaves skill code unchanged and remains available for keyboard navigation", () => {
  const change = vi.fn();
  render(
    <SkillEditor filePath="SKILL.md" value="Instructions" onChange={change} />,
  );
  const editor = screen.getByRole("textbox", { name: "SKILL.md" });
  editor.focus();
  expect(
    fireEvent.keyDown(editor, { key: "Tab", code: "Tab", keyCode: 9 }),
  ).toBe(true);
  expect(change).not.toHaveBeenCalled();
  expect(editor.textContent).toBe("Instructions");
});
