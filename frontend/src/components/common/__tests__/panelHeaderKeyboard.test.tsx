/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../PanelHeader";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("mobile actions have a translated label and Escape returns focus to the trigger", () => {
  render(<PanelHeader title="Tools" actions={<button>New tool</button>} />);
  const trigger = screen.getByRole("button", {
    name: "common.filtersAndActions",
  });
  fireEvent.click(trigger);
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(trigger);
});
