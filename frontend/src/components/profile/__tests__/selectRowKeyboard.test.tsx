/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SelectRow } from "../SelectRow";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("common selection supports arrows and Escape without dismissing the parent", () => {
  const select = vi.fn();
  render(
    <SelectRow
      label="Theme"
      value="light"
      options={[
        { key: "light", labelKey: "Light" },
        { key: "dark", labelKey: "Dark" },
      ]}
      onSelect={select}
    />,
  );
  const trigger = screen.getByRole("button", { name: "Theme" });
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(
    screen.getByRole("option", { name: "Light" }),
  );
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(document.activeElement).toBe(
    screen.getByRole("option", { name: "Dark" }),
  );
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});
