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

test("sandbox runtime selection keeps the modal open for policy selection", () => {
  const change = vi.fn();
  const close = vi.fn();
  render(<AgentOptionButton optionKey="sandbox" option={{ type: "select", label: "Sandbox", default: "cloud", options: [{ value: "local", label: "Local" }] }} value="cloud" onChange={change} isOpen onOpenChange={close} />);
  fireEvent.click(screen.getByRole("button", { name: /Local/ }));
  expect(change).toHaveBeenCalledWith("local");
  expect(close).not.toHaveBeenCalled();
});

test("thinking selection still closes the modal", () => {
  const close = vi.fn();
  render(<AgentOptionButton optionKey="enable_thinking" option={{ type: "select", label: "Thinking", default: "low", options: [{ value: "high", label: "High" }] }} value="low" onChange={vi.fn()} isOpen onOpenChange={close} />);
  fireEvent.click(screen.getByRole("button", { name: "High" }));
  expect(close).toHaveBeenCalledWith(false);
});
