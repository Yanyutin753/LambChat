/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
      .getByRole("dialog", { name: "agentOptions.sandbox.title" })
      .hasAttribute("data-modal-surface"),
  ).toBe(true);
  expect(screen.getByRole("heading", { name: "agentOptions.sandbox.title" })).toBeInTheDocument();
  const location = screen.getByRole("group", { name: "agentOptions.sandbox.section" });
  expect(within(location).getByRole("button", { name: /Cloud/, pressed: true })).toBeInTheDocument();
  expect(within(location).getByRole("button", { name: /Local/, pressed: false })).toBeInTheDocument();
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
