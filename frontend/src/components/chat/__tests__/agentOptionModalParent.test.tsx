/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AgentOptionButton } from "../AgentOptionButton";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("sandbox choices share the dismissible modal parent and scroll boundary", () => {
  const close = vi.fn();
  render(
    <AgentOptionButton
      optionKey="sandbox"
      option={{
        type: "select",
        label: "Sandbox",
        description: "Choose runtime",
        default: "cloud",
        options: [
          { value: "cloud", label: "Cloud" },
          { value: "local", label: "Local" },
        ],
      }}
      value="cloud"
      onChange={vi.fn()}
      isOpen
      onOpenChange={close}
    />,
  );
  expect(
    screen
      .getByRole("dialog", { name: "Choose runtime" })
      .hasAttribute("data-modal-surface"),
  ).toBe(true);
  expect(document.querySelector("[data-modal-handle]")).not.toBeNull();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledWith(false);
});
