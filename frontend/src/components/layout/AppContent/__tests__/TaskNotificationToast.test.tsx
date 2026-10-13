/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskNotificationToast } from "../TaskNotificationToast";
import { buildTaskNotificationRoute } from "../taskNotificationContent";

describe("task notification navigation", () => {
  it("escapes session and run identifiers and targets the completed run", () => {
    expect(buildTaskNotificationRoute("session/1", "run &2")).toBe("/chat/session%2F1?run_id=run%20%262");
    expect(buildTaskNotificationRoute("session/1")).toBe("/chat/session%2F1");
  });
  it("offers separate keyboard-focusable open and dismiss actions", () => {
    const open = vi.fn(); const dismiss = vi.fn();
    render(<TaskNotificationToast visible title="Task completed" body="Result" openLabel="Open conversation" dismissLabel="Dismiss" onOpen={open} onDismiss={dismiss} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveTextContent("Result");
    const openButton = screen.getByRole("button", { name: "Open conversation: Task completed" });
    openButton.focus(); expect(openButton).toHaveFocus();
    fireEvent.click(openButton); expect(open).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(dismiss).toHaveBeenCalledOnce(); expect(open).toHaveBeenCalledOnce();
  });
});
