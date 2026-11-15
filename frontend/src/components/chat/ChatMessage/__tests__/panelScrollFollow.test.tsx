/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SidebarMarkdownContent } from "../SidebarMarkdownContent";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));
vi.mock("../MarkdownContent", () => ({
  MarkdownContent: ({ content }: { content: string }) => <div>{content}</div>,
}));
afterEach(cleanup);

function geometry(element: HTMLElement) {
  let top = 0;
  let height = 1000;
  Object.defineProperties(element, {
    clientHeight: { configurable: true, get: () => 200 },
    scrollHeight: { configurable: true, get: () => height },
    scrollTop: {
      configurable: true,
      get: () => top,
      set: (value: number) => {
        top = Math.max(0, Math.min(value, height - 200));
      },
    },
  });
  return (value: number) => {
    height = value;
  };
}

test("thinking follows output, pauses on upward intent and resumes only at the bottom", () => {
  const view = render(<SidebarMarkdownContent content="first" isStreaming />);
  const scroller = view.container.querySelector<HTMLElement>(
    ".sidebar-reasoning-preview__scroll",
  )!;
  const grow = geometry(scroller);
  view.rerender(<SidebarMarkdownContent content="second" isStreaming />);
  expect(scroller.scrollTop).toBe(800);
  fireEvent.wheel(scroller, { deltaY: -10 });
  scroller.scrollTop = 790;
  fireEvent.scroll(scroller);
  grow(1200);
  view.rerender(<SidebarMarkdownContent content="third" isStreaming />);
  expect(scroller.scrollTop).toBe(790);
  scroller.scrollTop = 1000;
  fireEvent.scroll(scroller);
  grow(1400);
  view.rerender(<SidebarMarkdownContent content="fourth" isStreaming />);
  expect(scroller.scrollTop).toBe(1200);
});

test("expanding thinking preserves its scroll surface and paused reading position", () => {
  const view = render(<SidebarMarkdownContent content="first" isStreaming />);
  const scroller = view.container.querySelector<HTMLElement>(
    ".sidebar-reasoning-preview__scroll",
  )!;
  geometry(scroller);
  view.rerender(<SidebarMarkdownContent content="second" isStreaming />);
  fireEvent.touchStart(scroller, { touches: [{ clientY: 100 }] });
  fireEvent.touchMove(scroller, { touches: [{ clientY: 120 }] });
  scroller.scrollTop = 300;
  fireEvent.scroll(scroller);
  fireEvent.click(view.getByRole("button", { name: "Expand" }));
  expect(
    view.container.querySelector(".sidebar-reasoning-preview__scroll"),
  ).toBe(scroller);
  view.rerender(
    <SidebarMarkdownContent content="finished" isStreaming={false} />,
  );
  expect(scroller.scrollTop).toBe(300);
});

test("jump to bottom restores following after accumulated trackpad intent", () => {
  const view = render(<SidebarMarkdownContent content="first" isStreaming />);
  const scroller = view.container.querySelector<HTMLElement>(
    ".sidebar-reasoning-preview__scroll",
  )!;
  const grow = geometry(scroller);
  view.rerender(<SidebarMarkdownContent content="second" isStreaming />);
  for (let i = 0; i < 8; i++) fireEvent.wheel(scroller, { deltaY: -3 });
  grow(1200);
  view.rerender(<SidebarMarkdownContent content="third" isStreaming />);
  expect(scroller.scrollTop).toBe(800);
  fireEvent.click(view.getByRole("button", { name: "common.scrollToBottom" }));
  expect(scroller.scrollTop).toBe(1000);
  grow(1400);
  view.rerender(<SidebarMarkdownContent content="fourth" isStreaming />);
  expect(scroller.scrollTop).toBe(1200);
});

test("completed thinking opens at the start instead of jumping to its end", () => {
  const view = render(<SidebarMarkdownContent content="history" />);
  const scroller = view.container.querySelector<HTMLElement>(
    ".sidebar-reasoning-preview__scroll",
  )!;
  geometry(scroller);
  view.rerender(<SidebarMarkdownContent content="history updated" />);
  expect(scroller.scrollTop).toBe(0);
});

test("long streaming thinking keeps earlier text when updates arrive", () => {
  const content = "START " + "reasoning ".repeat(1500);
  const view = render(<SidebarMarkdownContent content={content} isStreaming />);
  expect(view.getByText(/^START/)).toBeInTheDocument();
  view.rerender(
    <SidebarMarkdownContent content={content + " END"} isStreaming />,
  );
  expect(view.getByText(/^START/)).toHaveTextContent("END");
});
