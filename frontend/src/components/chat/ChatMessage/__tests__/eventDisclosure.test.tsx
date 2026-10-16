/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Box } from "lucide-react";
import { CollapsiblePill } from "../../../common/CollapsiblePill";
import { MemoryStatusItem } from "../MemoryStatusItem";
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "chat.memory.initializing": "Retrieving memory",
        "chat.memory.ready": "Memory ready",
        "chat.memory.cancelled": "Memory retrieval cancelled",
      })[key] ?? key,
  }),
}));
afterEach(cleanup);

test("inline event details have a linked disclosure and retain expansion across status updates", () => {
  const { rerender } = render(
    <CollapsiblePill status="loading" icon={<Box />} label="Event">
      Details
    </CollapsiblePill>,
  );
  const toggle = screen.getByRole("button", { name: "Event" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(
    document.getElementById(toggle.getAttribute("aria-controls")!),
  ).toHaveTextContent("Details");
  rerender(
    <CollapsiblePill status="error" icon={<Box />} label="Event">
      Updated details
    </CollapsiblePill>,
  );
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Updated details")).toBeVisible();
});

test("an empty non-expandable event has no misleading disclosure arrow", () => {
  render(
    <CollapsiblePill icon={<Box />} label="Status" expandable={false}>
      {false}
    </CollapsiblePill>,
  );
  const button = screen.getByRole("button", { name: "Status" });
  expect(button).toHaveAttribute("aria-disabled", "true");
  expect(button.querySelector("svg.lucide-chevron-right")).toBeNull();
});

test("memory cancellation remains cancellation instead of appearing successful", () => {
  const { rerender } = render(<MemoryStatusItem status="starting" />);
  rerender(<MemoryStatusItem status="cancelled" />);
  const button = screen.getByRole("button", {
    name: "Memory retrieval cancelled",
  });
  expect(button).toHaveAttribute("data-status", "cancelled");
  expect(button).toHaveAttribute("aria-disabled", "true");
  expect(screen.queryByText("Memory ready")).not.toBeInTheDocument();
});

test.each(["error", "cancelled"] as const)(
  "tool %s includes an explicit status and keeps its original label",
  (status) => {
    render(
      <CollapsiblePill
        variant="tool"
        status={status}
        icon={<Box />}
        label="Read file"
      />,
    );
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Read file");
    expect(button).toHaveTextContent(`chat.eventStatus.${status}`);
    if (status === "error") {
      expect(screen.getByText("chat.eventStatus.error")).toHaveClass("sr-only");
      expect(button).toHaveAccessibleName(
        /Read file\s*chat\.eventStatus\.error/,
      );
    }
    expect(button.querySelector(".pill-btn__status")).toBeNull();
  },
);

test("an existing terminal label is not duplicated by the shared status suffix", () => {
  render(
    <CollapsiblePill
      variant="tool"
      status="cancelled"
      icon={<Box />}
      label="Wait · chat.eventStatus.cancelled"
    />,
  );
  expect(
    screen
      .getByRole("button")
      .textContent?.match(/chat.eventStatus.cancelled/g),
  ).toHaveLength(1);
});
