/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ThinkingBlock } from "../ThinkingBlock";

const locale = vi.hoisted(() => ({ language: "zh" }));

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    i18n: locale,
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
  locale.language = "zh";
});

test("updates live seconds then freezes the completed duration", () => {
  vi.useFakeTimers();
  vi.setSystemTime(1700000000000);
  const { rerender } = render(
    <ThinkingBlock content="Reasoning" isStreaming startedAt={1700000000000} />,
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    /^chat.message.thinking$/,
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

test.each([0, 999, -1000])(
  "hides completed duration below one second (%i ms)",
  (elapsed) => {
    render(
      <ThinkingBlock
        content="Quick reasoning"
        startedAt={1700000000000}
        completedAt={1700000000000 + elapsed}
      />,
    );
    expect(screen.getByRole("button")).toHaveTextContent(
      /^chat.message.thought$/,
    );
  },
);

test("shows completed duration starting at one second", () => {
  render(
    <ThinkingBlock
      content="Reasoning"
      startedAt={1700000000000}
      completedAt={1700000001000}
    />,
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thought 1 秒",
  );
});

test.each([
  [59000, "59 秒"],
  [60000, "1 分"],
  [365000, "6 分 5 秒"],
  [3600000, "1 小时"],
  [3723000, "1 小时 2 分 3 秒"],
])("formats completed thinking duration (%i ms)", (elapsed, expected) => {
  render(
    <ThinkingBlock
      content="Reasoning"
      startedAt={1700000000000}
      completedAt={1700000000000 + elapsed}
    />,
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    `chat.message.thought ${expected}`,
  );
});

test("switches live thinking from seconds to minutes", () => {
  vi.useFakeTimers();
  vi.setSystemTime(1700000059000);
  render(
    <ThinkingBlock content="Reasoning" isStreaming startedAt={1700000000000} />,
  );
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thinking 59 秒",
  );
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByRole("button")).toHaveTextContent(
    "chat.message.thinking 1 分",
  );
});

test.each(["en", "ja", "ko", "ru"])(
  "formats long thinking duration in %s",
  (language) => {
    locale.language = language;
    render(
      <ThinkingBlock
        content="Reasoning"
        startedAt={1700000000000}
        completedAt={1700000365000}
      />,
    );
    expect(screen.getByRole("button")).toHaveTextContent(
      "chat.message.thought 6m 05s",
    );
  },
);
