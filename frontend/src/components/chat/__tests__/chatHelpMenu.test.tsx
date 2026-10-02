/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ChatInputHelpMenu } from "../ChatInputHelpMenu";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

test("help keeps native documentation links and supports menu navigation and dismissal", () => {
  render(<ChatInputHelpMenu />);
  const trigger = screen.getByRole("button", { name: "common.help" });
  fireEvent.click(trigger);
  const menu = screen.getByRole("menu", { name: "common.help" });
  expect(trigger).toHaveAttribute("aria-controls", menu.id);
  const docs = screen.getByRole("menuitem", { name: "chat.helpDocs" });
  expect(docs.tagName).toBe("A");
  expect(docs).toHaveAttribute(
    "href",
    "https://yanyutin753.github.io/LambChat/",
  );
  expect(docs).toHaveFocus();
  fireEvent.keyDown(docs, { key: "ArrowDown" });
  expect(
    screen.getByRole("menuitem", { name: "chat.keyboardShortcuts" }),
  ).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, {
    key: "Escape",
    isComposing: true,
  });
  expect(menu).toBeInTheDocument();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
});

test("opening keyboard shortcuts hands focus back to help when the dialog closes", () => {
  render(<ChatInputHelpMenu />);
  const trigger = screen.getByRole("button", { name: "common.help" });
  fireEvent.click(trigger);
  fireEvent.click(
    screen.getByRole("menuitem", { name: "chat.keyboardShortcuts" }),
  );
  expect(screen.queryByRole("menu")).toBeNull();
  const dialog = screen.getByRole("dialog", { name: "chat.keyboardShortcuts" });
  expect(dialog).toHaveFocus();
  for (const category of [
    "shortcut.categoryChat",
    "shortcut.categoryGeneral",
    "shortcut.categoryDialog",
  ]) {
    expect(screen.getByText(category)).not.toHaveStyle({ opacity: "0.5" });
  }
  fireEvent.click(screen.getByRole("button", { name: "common.close" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(trigger).toHaveFocus();
});
