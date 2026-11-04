/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ChatInputSteerQueue } from "../ChatInputSteerQueue";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
const items = [
  {
    id: "queued-1",
    content: "多一点中文",
    status: "deferred" as const,
    queued: true,
    timestamp: new Date(),
  },
];

test("a paused queue explains the interruption and resumes without removing its draft", () => {
  const resume = vi.fn(),
    remove = vi.fn();
  render(
    <ChatInputSteerQueue
      items={items}
      paused
      onResume={resume}
      onCancel={remove}
    />,
  );
  expect(screen.getByRole("status").textContent).toContain(
    "chat.queuePausedByStop",
  );
  expect(screen.getByText("多一点中文")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "chat.queueResume" }));
  expect(resume).toHaveBeenCalledTimes(1);
  expect(remove).not.toHaveBeenCalled();
});

test("resume cannot be repeated while its server acknowledgement is pending", () => {
  render(
    <ChatInputSteerQueue items={items} paused resuming onResume={vi.fn()} />,
  );
  expect(
    screen.getByRole("button", { name: "chat.queueResume" }),
  ).toBeDisabled();
});

test("guiding a queued draft passes its identity without deleting it before acknowledgement", () => {
  const guide = vi.fn(),
    remove = vi.fn();
  render(
    <ChatInputSteerQueue items={items} onGuide={guide} onCancel={remove} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.queueGuide" }));
  expect(guide).toHaveBeenCalledWith("多一点中文", undefined, "queued-1");
  expect(remove).not.toHaveBeenCalled();
});
