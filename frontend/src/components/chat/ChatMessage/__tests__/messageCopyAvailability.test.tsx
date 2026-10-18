/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ChatMessage } from "..";

const copy = vi.hoisted(() => vi.fn());
vi.mock("../../../../utils/clipboard", () => ({ copyToClipboard: copy }));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ availableModels: [] }),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));
vi.mock("../../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
afterEach(cleanup);
beforeEach(() => copy.mockReset().mockResolvedValue(undefined));

test.each(["user", "assistant"] as const)(
  "%s messages omit copy when there is no readable text",
  (role) => {
    render(
      <ChatMessage
        message={{
          id: "empty",
          role,
          content: " \n ",
          timestamp: new Date(),
          parts: [{ type: "sandbox", status: "ready" }],
        }}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "chat.message.copy" }),
    ).toBeNull();
  },
);

test.each([false, true])(
  "assistant copies saved body with metadata and empty text parts (%s)",
  async (emptyText) => {
    render(
      <ChatMessage
        message={{
          id: "saved",
          role: "assistant",
          content: "Keep **the saved answer**",
          timestamp: new Date(),
          parts: [
            { type: "sandbox", status: "ready" },
            ...(emptyText ? [{ type: "text" as const, content: "" }] : []),
          ],
        }}
      />,
    );
    const button = screen.getByRole("button", { name: "chat.message.copy" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await screen.findByRole("button", { name: "chat.message.copied" });
    expect(copy).toHaveBeenCalledWith("Keep **the saved answer**");
  },
);

test("assistant copies current text parts ahead of the saved body", async () => {
  render(
    <ChatMessage
      message={{
        id: "parts",
        role: "assistant",
        content: "Old answer",
        timestamp: new Date(),
        parts: [
          { type: "text", content: "First" },
          { type: "text", content: "Second" },
        ],
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
  await screen.findByRole("button", { name: "chat.message.copied" });
  expect(copy).toHaveBeenCalledWith("First\nSecond");
});

test.each([false, true])(
  "scheduled trigger renders as a user bubble before its assistant (%s)",
  (isStreaming) => {
    const timestamp = new Date("2026-10-17T19:33:41Z");
    const { container } = render(
      <ChatMessage
        message={{
          id: "scheduled-result:run",
          role: "assistant",
          content: isStreaming ? "" : "692",
          timestamp,
          isStreaming,
          metadata: { scheduledTaskName: "每分钟随机数字" },
        }}
      />,
    );
    const bubble = container.querySelector(".user-message-bubble");
    expect(bubble).toHaveTextContent("scheduledTask.title · 每分钟随机数字");
    expect(bubble).toHaveTextContent(timestamp.toLocaleString());
    const heading = container.querySelector(".chat-assistant-heading")!;
    expect(
      bubble!.compareDocumentPosition(heading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(heading.parentElement?.textContent).not.toContain("每分钟随机数字");
  },
);

test.each([false, true])(
  "ordinary and scheduled confirmations share a visible status row (%s)",
  (scheduled) => {
    render(
      <ChatMessage
        message={{
          id: "waiting",
          role: "assistant",
          content: "",
          timestamp: new Date(),
          isStreaming: false,
          metadata: scheduled
            ? {
                scheduledTaskName: "Numbers",
                scheduledProgressStatus: "waiting_human",
              }
            : undefined,
          parts: [
            {
              type: "tool",
              id: "exec",
              name: "execute",
              args: { command: "echo 123" },
              isPending: true,
              awaitingConfirmation: true,
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("status", { name: "chat.message.waitingConfirm" }),
    ).toBeVisible();
    expect(screen.queryByText("chat.message.runInterrupted")).toBeNull();
    expect(
      screen.queryByRole("status", {
        name: "chat.message.runStepsWorkingNoTimer",
      }),
    ).toBeNull();
  },
);
