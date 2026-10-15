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
      <ChatMessage message={{
        id: "empty", role, content: " \n ", timestamp: new Date(),
        parts: [{ type: "sandbox", status: "ready" }],
      }} />,
    );
    expect(screen.queryByRole("button", { name: "chat.message.copy" })).toBeNull();
  },
);

test.each([false, true])("assistant copies saved body with metadata and empty text parts (%s)", async (emptyText) => {
  render(
    <ChatMessage message={{
      id: "saved", role: "assistant", content: "Keep **the saved answer**", timestamp: new Date(),
      parts: [{ type: "sandbox", status: "ready" }, ...(emptyText ? [{ type: "text" as const, content: "" }] : [])],
    }} />,
  );
  const button = screen.getByRole("button", { name: "chat.message.copy" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await screen.findByRole("button", { name: "chat.message.copied" });
  expect(copy).toHaveBeenCalledWith("Keep **the saved answer**");
});

test("assistant copies current text parts ahead of the saved body", async () => {
  render(
    <ChatMessage message={{
      id: "parts", role: "assistant", content: "Old answer", timestamp: new Date(),
      parts: [{ type: "text", content: "First" }, { type: "text", content: "Second" }],
    }} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
  await screen.findByRole("button", { name: "chat.message.copied" });
  expect(copy).toHaveBeenCalledWith("First\nSecond");
});
