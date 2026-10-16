/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ThinkingBlock } from "../ThinkingBlock";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count: number }) =>
      key === "chat.message.thinkingSeconds" ? `${values?.count} 秒` : key,
  }),
}));
vi.mock("../useSmoothStreamText", () => ({
  useSmoothStreamText: (value: string) => value,
}));
vi.mock("../../../common", () => ({
  CollapsiblePill: ({ label }: { label: string }) => <button>{label}</button>,
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("updates live seconds then freezes the completed duration", () => {
  vi.useFakeTimers();
  vi.setSystemTime(1700000000000);
  const { rerender } = render(
    <ThinkingBlock content="Reasoning" isStreaming startedAt={1700000000000} />,
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thinking 0 秒",
  );
  act(() => {
    vi.advanceTimersByTime(3000);
  });
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thinking 3 秒",
  );
  rerender(
    <ThinkingBlock
      content="Reasoning"
      startedAt={1700000000000}
      completedAt={1700000012000}
    />,
  );
  act(() => {
    vi.advanceTimersByTime(10000);
  });
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thought 12 秒",
  );
});

test("does not invent timing for old history", () => {
  render(<ThinkingBlock content="Old reasoning" />);
  expect(screen.getByRole("button")).toHaveTextContent(
    /^chat.message.thought$/,
  );
});
