/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ChatInputSteerQueue } from "../ChatInputSteerQueue";
import type { SteerItem } from "../../../utils/mergeSteers";

const item: SteerItem = {
  id: "q1",
  content: "看看",
  queued: true,
  status: "deferred",
  timestamp: new Date(1),
};

test("attachment-only messages display the queued filenames", () => {
  render(
    <ChatInputSteerQueue
      items={[
        {
          ...item,
          content: "",
          attachments: [
            {
              id: "f1",
              key: "f1",
              name: "report.pdf",
              type: "document",
              mimeType: "application/pdf",
              size: 10,
            },
          ],
        },
      ]}
    />,
  );
  expect(screen.getByText("report.pdf")).toBeInTheDocument();
});

test("more menu supports keyboard dismissal and restores trigger focus", () => {
  render(<ChatInputSteerQueue items={[item]} onEdit={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: "chat.queueMore" });
  fireEvent.click(trigger);
  expect(screen.getByRole("menuitem")).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("menuitem"), { key: "Escape" });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("messages already being delivered cannot be guided again", () => {
  render(
    <ChatInputSteerQueue
      items={[{ ...item, status: "pending" }]}
      onGuide={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "chat.queueGuide" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("chat.steerQueued");
});

test("deleting one of two identical messages uses its unique ID", () => {
  const onCancel = vi.fn();
  render(
    <ChatInputSteerQueue
      items={[item, { ...item, id: "q2" }]}
      onCancel={onCancel}
    />,
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "chat.queueDelete" })[1],
  );
  expect(onCancel).toHaveBeenCalledExactlyOnceWith(item.content, "q2");
});

test("failed messages remain visible and editable", () => {
  render(
    <ChatInputSteerQueue
      items={[{ ...item, status: "failed" }]}
      onEdit={vi.fn()}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("chat.steerFailedRetry");
  fireEvent.click(screen.getByRole("button", { name: "chat.queueMore" }));
  expect(screen.getByRole("menuitem")).toBeEnabled();
});
