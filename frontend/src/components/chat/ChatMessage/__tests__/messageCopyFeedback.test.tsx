/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ChatMessage } from "..";
import { MarkdownContent } from "../MarkdownContent";

const mocks = vi.hoisted(() => ({
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../../../../utils/clipboard", () => ({ copyToClipboard: mocks.copy }));
vi.mock("react-hot-toast", () => ({
  default: { success: mocks.success, error: mocks.error },
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
beforeEach(() => vi.clearAllMocks());

test.each(["user", "assistant"] as const)(
  "%s message copying waits for the clipboard and preserves retry after failure",
  async (role) => {
    let complete!: () => void;
    mocks.copy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          complete = resolve;
        }),
    );
    render(
      <ChatMessage
        message={{
          id: "copy-message",
          role,
          content: "Keep **the original** Markdown",
          timestamp: new Date(),
        }}
      />,
    );
    const copy = screen.getByRole("button", { name: "chat.message.copy" });
    fireEvent.click(copy);
    expect(copy).toBeDisabled();
    expect(copy).toHaveAttribute("aria-busy", "true");
    expect(mocks.success).not.toHaveBeenCalled();
    await act(async () => complete());
    const copied = await screen.findByRole("button", {
      name: "chat.message.copied",
    });
    expect(mocks.copy).toHaveBeenLastCalledWith(
      "Keep **the original** Markdown",
    );
    mocks.copy.mockRejectedValueOnce(new Error("Permission denied"));
    fireEvent.click(copied);
    await waitFor(() =>
      expect(mocks.error).toHaveBeenCalledWith("chat.message.copyFailed", {
        id: expect.any(String),
      }),
    );
    expect(
      screen.getByRole("button", { name: "chat.message.copy" }),
    ).toBeEnabled();
    expect(mocks.success).toHaveBeenCalledOnce();
  },
);

test.each([
  {
    kind: "code block",
    content: "```js\nconst result = 42;\n```",
    label: "chat.message.copyCode",
    expected: "const result = 42;",
  },
  {
    kind: "table",
    content: "| Name | Value |\n| --- | --- |\n| Draft | two |",
    label: "chat.message.copy",
    expected: "| Name  | Value |\n| ----- | ----- |\n| Draft | two   |",
  },
])(
  "$kind copying waits for confirmation and retains its serialized content",
  async ({ content, label, expected }) => {
    let complete!: () => void;
    mocks.copy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          complete = resolve;
        }),
    );
    render(<MarkdownContent content={content} />);
    const copy = await screen.findByRole("button", { name: label });
    fireEvent.click(copy);
    expect(copy).toBeDisabled();
    expect(mocks.success).not.toHaveBeenCalled();
    expect(mocks.copy).toHaveBeenCalledWith(expected);
    await act(async () => complete());
    const copied = await screen.findByRole("button", {
      name: "chat.message.copied",
    });
    mocks.copy.mockRejectedValueOnce(new Error("Permission denied"));
    fireEvent.click(copied);
    await waitFor(() =>
      expect(mocks.error).toHaveBeenCalledWith("chat.message.copyFailed", {
        id: expect.any(String),
      }),
    );
    expect(screen.getByRole("button", { name: label })).toBeEnabled();
    expect(mocks.success).toHaveBeenCalledOnce();
  },
);

test("inline code is a keyboard accessible copy action that waits for confirmation", async () => {
  let complete!: () => void;
  mocks.copy.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  render(<MarkdownContent content="Use `delivery_count` here." />);
  const button = screen.getByRole("button", { name: "chat.message.copyCode" });
  expect(button).toHaveAttribute("type", "button");
  expect(button.querySelector("code")).toHaveTextContent("delivery_count");
  expect(button).toHaveAccessibleDescription("delivery_count");
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(mocks.success).not.toHaveBeenCalled();
  await act(async () => complete());
  expect(mocks.copy).toHaveBeenCalledWith("delivery_count");
  mocks.copy.mockRejectedValueOnce(new Error("Unavailable"));
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copied" }));
  await waitFor(() => expect(mocks.error).toHaveBeenCalledOnce());
  expect(
    screen.getByRole("button", { name: "chat.message.copyCode" }),
  ).toHaveAccessibleDescription("delivery_count chat.message.copyFailed");
  mocks.copy.mockResolvedValueOnce(undefined);
  fireEvent.click(
    screen.getByRole("button", { name: "chat.message.copyCode" }),
  );
  expect(
    await screen.findByRole("button", { name: "chat.message.copied" }),
  ).toBeEnabled();
});
