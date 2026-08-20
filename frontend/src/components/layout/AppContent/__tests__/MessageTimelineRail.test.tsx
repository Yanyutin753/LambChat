// @vitest-environment jsdom

import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { MessageOutlineItem } from "../messageOutline";
import {
  MessageTimelineRail,
  updateTimelineRange,
} from "../MessageTimelineRail";

// Mock i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

function createOutlineItem(
  overrides: Partial<MessageOutlineItem>,
): MessageOutlineItem {
  return {
    id: overrides.id ?? "message:u1",
    anchorId: overrides.anchorId ?? "chat-outline-message-u1",
    kind: overrides.kind ?? "user-message",
    label: overrides.label ?? "Hello",
    level: 1,
    messageId: overrides.messageId ?? "u1",
    messageIndex: overrides.messageIndex ?? 0,
  } as MessageOutlineItem;
}

/** 2 user + 2 assistant → 2 turns */
function createPairedItems(): MessageOutlineItem[] {
  return [
    createOutlineItem({
      id: "message:u1",
      anchorId: "chat-outline-message-u1",
      kind: "user-message",
      label: "What is AI?",
      messageId: "u1",
      messageIndex: 0,
    }),
    createOutlineItem({
      id: "assistant:a1",
      anchorId: "chat-outline-message-a1",
      kind: "assistant-message",
      label: "AI stands for Artificial Intelligence",
      messageId: "a1",
      messageIndex: 1,
    }),
    createOutlineItem({
      id: "message:u2",
      anchorId: "chat-outline-message-u2",
      kind: "user-message",
      label: "Tell me more",
      messageId: "u2",
      messageIndex: 2,
    }),
    createOutlineItem({
      id: "assistant:a2",
      anchorId: "chat-outline-message-a2",
      kind: "assistant-message",
      label: "Machine learning is a subset of AI",
      messageId: "a2",
      messageIndex: 3,
    }),
  ];
}

describe("MessageTimelineRail", () => {
  const onNavigate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    updateTimelineRange(null);
  });

  test("renders nothing when items are empty", () => {
    const { container } = render(
      <MessageTimelineRail items={[]} onNavigate={onNavigate} />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("renders nothing when items only contain headings", () => {
    const headingItem = createOutlineItem({
      id: "heading:a1:0:Introduction",
      anchorId: "chat-outline-heading-a1-0-introduction",
      kind: "assistant-heading",
      label: "Introduction",
      messageId: "a1",
      messageIndex: 0,
    });
    const { container } = render(
      <MessageTimelineRail items={[headingItem]} onNavigate={onNavigate} />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("renders a button with flex layout and correct aria-label", () => {
    const items = createPairedItems();
    render(<MessageTimelineRail items={items} onNavigate={onNavigate} />);

    const btn = screen.getByRole("button", { name: "Timeline" });
    expect(btn).toBeInTheDocument();
    expect(btn.className).toContain("flex");
    expect(btn.className).toContain("group/timeline");
  });

  test("button title shows turn count", () => {
    const items = createPairedItems();
    render(<MessageTimelineRail items={items} onNavigate={onNavigate} />);

    const btn = screen.getByRole("button", { name: "Timeline" });
    expect(btn).toHaveAttribute("title", "Timeline · 2");
  });

  test("2 turns produce 2 bar elements", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // Each turn has a clickable span containing a bar span
    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );
    expect(bars).toHaveLength(2);
  });

  test("bar height is 3px and width is 16px", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const bar = container.querySelector("button > span > span.rounded-full");
    expect(bar?.className).toContain("h-[3px]");
    expect((bar as HTMLElement)?.style.width).toBe("16px");
  });

  test("bars have compact 8px gap", () => {
    const items = createPairedItems();
    render(<MessageTimelineRail items={items} onNavigate={onNavigate} />);

    const btn = screen.getByRole("button", { name: "Timeline" });
    expect(btn.style.gap).toBe("8px");
  });

  test("touch dragging navigates to the turn on release", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );
    const btn = screen.getByRole("button", { name: "Timeline" });
    const targets = container.querySelectorAll("button > span.cursor-pointer");
    vi.spyOn(targets[1]!, "getBoundingClientRect").mockReturnValue({
      top: 40,
      bottom: 56,
      left: 0,
      right: 40,
      width: 40,
      height: 16,
      x: 0,
      y: 40,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(btn, {
      pointerId: 1,
      pointerType: "touch",
      clientY: 48,
    });
    fireEvent.pointerMove(btn, {
      pointerId: 1,
      pointerType: "touch",
      clientY: 48,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 1,
      pointerType: "touch",
      clientY: 48,
    });

    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u2", 2);
  });

  test("touching a turn creates a length-based wave across nearby bars", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );
    const btn = screen.getByRole("button", { name: "Timeline" });
    const targets = container.querySelectorAll("button > span.cursor-pointer");
    vi.spyOn(targets[1]!, "getBoundingClientRect").mockReturnValue({
      top: 40,
      bottom: 56,
      left: 0,
      right: 40,
      width: 40,
      height: 16,
      x: 0,
      y: 40,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(btn, {
      pointerId: 2,
      pointerType: "touch",
      clientY: 48,
    });

    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );
    expect((bars[1] as HTMLElement).style.width).toBe("24px");
    expect((bars[0] as HTMLElement).style.width).toBe("23px");
  });

  test("inactive bars use color-mix transparent background", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // No visible range → all bars inactive
    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );
    for (const bar of bars) {
      expect(bar.className).toContain(
        "bg-[color-mix(in_srgb,var(--theme-text-secondary)_22%,transparent)]",
      );
    }
  });

  test("active bars use primary color when in visible range", () => {
    const items = createPairedItems();
    updateTimelineRange({ startIndex: 2, endIndex: 3 });

    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );

    // Second bar (turn 2, messages index 2-3) should be active
    expect(bars[1]!.className).toContain("bg-[var(--theme-primary)]");

    // First bar (turn 1, messages index 0-1) should be inactive
    expect(bars[0]!.className).toContain(
      "bg-[color-mix(in_srgb,var(--theme-text-secondary)_22%,transparent)]",
    );
  });

  test("clicking a bar navigates to the turn's user message", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // Click the second turn's bar
    const clickTargets = container.querySelectorAll(
      "button > span.cursor-pointer",
    );
    fireEvent.click(clickTargets[1]!);
    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u2", 2);
  });

  test("clicking the first bar navigates to first user message", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTargets = container.querySelectorAll(
      "button > span.cursor-pointer",
    );
    fireEvent.click(clickTargets[0]!);
    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u1", 0);
  });

  test("clicking a bar stops propagation", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    const event = new MouseEvent("click", { bubbles: true });
    const spy = vi.spyOn(event, "stopPropagation");

    clickTarget.dispatchEvent(event);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  test("positioned centered on right edge", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain("absolute");
    expect(wrapper.className).toContain("right-0");
    expect(wrapper.className).toContain("top-1/2");
    expect(wrapper.className).toContain("-translate-y-1/2");
  });

  /* ---- Hover preview card ---- */

  test("hovering a bar shows preview card in portal", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // No card initially
    expect(document.body.querySelector(".rounded-lg.shadow-lg")).toBeNull();

    // Hover the first turn bar
    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);

    // Card should appear in portal
    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    expect(card).toBeInTheDocument();
  });

  test("preview card shows user message text", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);

    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    // First turn's user message is "What is AI?"
    expect(card.textContent).toContain("What is AI?");
  });

  test("preview card shows assistant response text", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);

    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    // First turn's assistant response is "AI stands for Artificial Intelligence"
    expect(card.textContent).toContain("AI stands for Artificial Intelligence");
  });

  test("mouse leave on rail removes preview card", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const btn = screen.getByRole("button", { name: "Timeline" });
    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;

    // Hover to show card
    fireEvent.mouseEnter(clickTarget);
    expect(
      document.body.querySelector(".rounded-lg.shadow-lg"),
    ).toBeInTheDocument();

    // Mouse leave on button hides card
    fireEvent.mouseLeave(btn);
    expect(document.body.querySelector(".rounded-lg.shadow-lg")).toBeNull();
  });

  test("hovering a bar widens it from 16px to 24px", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const bar = container.querySelector(
      "button > span > span.rounded-full",
    ) as HTMLElement;
    expect(bar.style.width).toBe("16px");

    // Hover the parent span
    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);
    expect(bar.style.width).toBe("24px");
  });

  test("hovering second turn shows second turn's content", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // Hover the second turn
    const clickTargets = container.querySelectorAll(
      "button > span.cursor-pointer",
    );
    fireEvent.mouseEnter(clickTargets[1]!);

    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    expect(card.textContent).toContain("Tell me more");
    expect(card.textContent).toContain("Machine learning is a subset of AI");
  });

  test("preview card has arrow element", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);

    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    const arrow = card.querySelector(".rotate-45");
    expect(arrow).toBeInTheDocument();
  });
});
