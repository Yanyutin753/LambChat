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
import { CopyButton } from "../CopyButton";
const mocks = vi.hoisted(() => ({
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../../../utils/clipboard", () => ({ copyToClipboard: mocks.copy }));
vi.mock("react-hot-toast", () => ({
  default: { success: mocks.success, error: mocks.error },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => vi.clearAllMocks());

test("failed copying stays retryable and never reports success", async () => {
  mocks.copy
    .mockRejectedValueOnce(new Error("Permission denied"))
    .mockResolvedValueOnce(undefined);
  render(<CopyButton text="Keep this result" label="Copy result" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy result" }));
  await waitFor(() =>
    expect(mocks.error).toHaveBeenCalledWith("chat.message.copyFailed"),
  );
  expect(mocks.success).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Copy result" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Copy result" }));
  await screen.findByRole("button", { name: "chat.message.copied" });
  expect(mocks.copy).toHaveBeenNthCalledWith(2, "Keep this result");
  expect(mocks.success).toHaveBeenCalledOnce();
});

test("pending copying blocks duplicate requests and waits for confirmed success", async () => {
  let complete!: () => void;
  mocks.copy.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  render(<CopyButton text="Report" label="Copy report" />);
  const button = screen.getByRole("button", { name: "Copy report" });
  expect(button).toHaveAttribute("type", "button");
  fireEvent.click(button);
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(mocks.copy).toHaveBeenCalledOnce();
  expect(mocks.success).not.toHaveBeenCalled();
  complete();
  await screen.findByRole("button", { name: "chat.message.copied" });
});

test("replaced text ignores an older pending copy completion", async () => {
  let complete!: () => void;
  mocks.copy.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  const view = render(<CopyButton text="Old report" label="Copy report" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
  view.rerender(<CopyButton text="New report" label="Copy report" />);
  await act(async () => {
    complete();
  });
  expect(mocks.success).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Copy report" })).toBeEnabled();
  mocks.copy.mockResolvedValueOnce(undefined);
  fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
  await screen.findByRole("button", { name: "chat.message.copied" });
  expect(mocks.copy).toHaveBeenLastCalledWith("New report");
});

test("unmounting ignores a late rejected copy", async () => {
  let reject!: (error: Error) => void;
  mocks.copy.mockImplementationOnce(
    () =>
      new Promise<void>((_resolve, fail) => {
        reject = fail;
      }),
  );
  const view = render(<CopyButton text="Report" />);
  fireEvent.click(screen.getByRole("button"));
  view.unmount();
  await act(async () => {
    reject(new Error("Unavailable"));
  });
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.error).not.toHaveBeenCalled();
});

test("confirmed copy expires and unmounting clears its feedback timer", async () => {
  vi.useFakeTimers();
  mocks.copy.mockResolvedValue(undefined);
  const view = render(<CopyButton text="Report" label="Copy report" />);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
  });
  expect(
    screen.getByRole("button", { name: "chat.message.copied" }),
  ).toBeEnabled();
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByRole("button", { name: "Copy report" })).toBeEnabled();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
  });
  expect(vi.getTimerCount()).toBe(1);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
