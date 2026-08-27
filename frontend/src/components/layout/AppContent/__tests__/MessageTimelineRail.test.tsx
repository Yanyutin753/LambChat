// @vitest-environment jsdom

import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
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

/** 3 user + 3 assistant → 3 turns */
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
    createOutlineItem({
      id: "message:u3",
      anchorId: "chat-outline-message-u3",
      kind: "user-message",
      label: "What about deep learning?",
      messageId: "u3",
      messageIndex: 4,
    }),
    createOutlineItem({
      id: "assistant:a3",
      anchorId: "chat-outline-message-a3",
      kind: "assistant-message",
      label: "Deep learning uses neural networks.",
      messageId: "a3",
      messageIndex: 5,
    }),
  ];
}

function createTwoTurnItems(): MessageOutlineItem[] {
  return createPairedItems().slice(0, 4);
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

  test("hides the timeline when there are only 2 turns", () => {
    const { container } = render(
      <MessageTimelineRail
        items={createTwoTurnItems()}
        onNavigate={onNavigate}
      />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("button title shows turn count", () => {
    const items = createPairedItems();
    render(<MessageTimelineRail items={items} onNavigate={onNavigate} />);

    const btn = screen.getByRole("button", { name: "Timeline" });
    expect(btn).toHaveAttribute("title", "Timeline · 3");
  });

  test("3 turns produce 3 bar elements", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    // Each turn has a clickable span containing a bar span
    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );
    expect(bars).toHaveLength(3);
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

  test("touching a turn doubles that bar's width and leaves neighbors unchanged", () => {
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
    // Only the touched bar expands (2× base width), neighbors stay at base
    expect((bars[1] as HTMLElement).style.width).toBe("32px");
    expect((bars[0] as HTMLElement).style.width).toBe("16px");
    expect((bars[2] as HTMLElement).style.width).toBe("16px");
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

  test("positioned on left edge with a small inset", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain("absolute");
    expect(wrapper.className).toContain("left-2");
    expect(wrapper.className).not.toContain("left-0");
    expect(wrapper.className).not.toContain("right-0");
    expect(wrapper.className).toContain("top-1/2");
    expect(wrapper.className).toContain("-translate-y-1/2");
  });

  test("bars anchor to the left edge of the rail", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const btn = screen.getByRole("button", { name: "Timeline" });
    expect(btn.className).toContain("items-start");

    const row = container.querySelector("button > span.cursor-pointer")!;
    expect(row.className).toContain("justify-start");
  });

  /* ---- Overflow scrolling (rail taller than chat area) ---- */

  test("rail wrapper is height-constrained and scrollable when turns overflow", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain("max-h-full");
    expect(wrapper.className).toContain("overflow-y-auto");
    // Scrollbar is hidden (wheel/trackpad + drag still scroll)
    expect(wrapper.className).toContain("[scrollbar-width:none]");
    expect(wrapper.className).toContain("[&::-webkit-scrollbar]:hidden");
  });

  test("touch drag scrolls the rail vertically when content overflows", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });
    let scrollTop = 0;
    Object.defineProperty(wrapper, "scrollTop", {
      get: () => scrollTop,
      set: (value: number) => {
        scrollTop = value;
      },
      configurable: true,
    });

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 3,
      pointerType: "touch",
      clientY: 300,
    });
    fireEvent.pointerMove(btn, {
      pointerId: 3,
      pointerType: "touch",
      clientY: 250,
    });

    // Finger moved up by 50px → rail scrolls down by 50px
    expect(scrollTop).toBe(50);
  });

  test("touch drag that scrolls the rail does not navigate on release", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 4,
      pointerType: "touch",
      clientY: 300,
    });
    fireEvent.pointerMove(btn, {
      pointerId: 4,
      pointerType: "touch",
      clientY: 250,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 4,
      pointerType: "touch",
      clientY: 250,
    });

    expect(onNavigate).not.toHaveBeenCalled();
  });

  test("swipe release on non-overflowing rail does not navigate", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );
    // jsdom: no overflow mocked → rail does not scroll
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

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 12,
      pointerType: "touch",
      clientY: 48,
    });
    // Swipe well past the tap slop, ending near the top bar
    fireEvent.pointerMove(btn, {
      pointerId: 12,
      pointerType: "touch",
      clientY: 10,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 12,
      pointerType: "touch",
      clientY: 10,
    });

    expect(onNavigate).not.toHaveBeenCalled();
  });

  test("tap without movement on overflowing rail navigates to nearest turn", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });
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

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 5,
      pointerType: "touch",
      clientY: 48,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 5,
      pointerType: "touch",
      clientY: 48,
    });

    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u2", 2);
  });

  test("drag within tap slop on overflowing rail still navigates", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });
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

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 6,
      pointerType: "touch",
      clientY: 48,
    });
    // 3px jitter is below the tap slop threshold
    fireEvent.pointerMove(btn, {
      pointerId: 6,
      pointerType: "touch",
      clientY: 45,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 6,
      pointerType: "touch",
      clientY: 45,
    });

    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u2", 2);
  });

  test("pointercancel on overflowing rail does not navigate", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 7,
      pointerType: "touch",
      clientY: 48,
    });
    fireEvent.pointerCancel(btn, {
      pointerId: 7,
      pointerType: "touch",
      clientY: 48,
    });

    expect(onNavigate).not.toHaveBeenCalled();
  });

  test("pressing overflowing rail enlarges nearest bar to double width", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 8,
      pointerType: "touch",
      clientY: 300,
    });

    const bars = container.querySelectorAll(
      "button > span > span.rounded-full",
    );
    // All jsdom rects are zero → nearest bar is index 0
    expect((bars[0] as HTMLElement).style.width).toBe("32px");

    fireEvent.pointerUp(btn, {
      pointerId: 8,
      pointerType: "touch",
      clientY: 300,
    });
    expect((bars[0] as HTMLElement).style.width).toBe("16px");
  });

  test("touch drag does not re-read bar geometry during moves", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 500,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 11,
      pointerType: "touch",
      clientY: 300,
    });

    // Geometry (bar centers) is captured once at drag start; moves must not
    // force layout by calling getBoundingClientRect again.
    const rectSpy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({
        top: 0,
        bottom: 0,
        left: 0,
        right: 0,
        width: 0,
        height: 0,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect);
    try {
      fireEvent.pointerMove(btn, {
        pointerId: 11,
        pointerType: "touch",
        clientY: 280,
      });
      fireEvent.pointerMove(btn, {
        pointerId: 11,
        pointerType: "touch",
        clientY: 260,
      });
      fireEvent.pointerMove(btn, {
        pointerId: 11,
        pointerType: "touch",
        clientY: 240,
      });
      expect(rectSpy).not.toHaveBeenCalled();
    } finally {
      rectSpy.mockRestore();
    }
  });

  test("clicking the gap between bars (button fallback) navigates to nearest turn", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );
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

    // Click lands on the button itself (gap row), not on any bar span
    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.click(btn, { clientY: 48 });

    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("chat-outline-message-u2", 2);
  });

  test("synthetic click after a touch tap does not navigate twice", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );
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

    const btn = screen.getByRole("button", { name: "Timeline" });
    fireEvent.pointerDown(btn, {
      pointerId: 13,
      pointerType: "touch",
      clientY: 48,
    });
    fireEvent.pointerUp(btn, {
      pointerId: 13,
      pointerType: "touch",
      clientY: 48,
    });
    // Pointer capture retargets the synthetic click to the button
    fireEvent.click(btn, { clientY: 48 });

    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  test("fling continues scrolling with decaying velocity after release", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const wrapper = container.firstElementChild as HTMLElement;
    Object.defineProperty(wrapper, "scrollHeight", {
      value: 2000,
      configurable: true,
    });
    Object.defineProperty(wrapper, "clientHeight", {
      value: 100,
      configurable: true,
    });
    let scrollTop = 0;
    Object.defineProperty(wrapper, "scrollTop", {
      get: () => scrollTop,
      set: (value: number) => {
        scrollTop = value;
      },
      configurable: true,
    });

    const frames: FrameRequestCallback[] = [];
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => {
        frames.push(cb);
        return frames.length;
      });
    try {
      const btn = screen.getByRole("button", { name: "Timeline" });
      fireEvent.pointerDown(btn, {
        pointerId: 9,
        pointerType: "touch",
        clientY: 300,
      });
      // Finger flick: 20px upwards in one move → scrollTop ends at 20
      fireEvent.pointerMove(btn, {
        pointerId: 9,
        pointerType: "touch",
        clientY: 280,
      });
      expect(scrollTop).toBe(20);

      fireEvent.pointerUp(btn, {
        pointerId: 9,
        pointerType: "touch",
        clientY: 280,
      });

      // Fling scheduled: first frame adds full velocity (20)…
      expect(frames.length).toBeGreaterThan(0);
      frames.splice(0).forEach((cb) => cb(0));
      expect(scrollTop).toBe(40);

      // …next frame adds decayed velocity (20 × 0.95 = 19)
      frames.splice(0).forEach((cb) => cb(0));
      expect(scrollTop).toBe(59);
    } finally {
      rafSpy.mockRestore();
    }
  });

  test("active turn bar scrolls into view when visible range changes", () => {
    const scrollIntoView = vi.fn();
    // jsdom does not implement scrollIntoView
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      const items = createPairedItems();
      render(<MessageTimelineRail items={items} onNavigate={onNavigate} />);
      expect(scrollIntoView).not.toHaveBeenCalled();

      act(() => {
        updateTimelineRange({ startIndex: 2, endIndex: 3 });
      });

      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    } finally {
      delete (Element.prototype as Partial<Element>).scrollIntoView;
    }
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

  test("preview card opens to the right of the rail", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    vi.spyOn(clickTarget, "getBoundingClientRect").mockReturnValue({
      top: 100,
      bottom: 116,
      left: 0,
      right: 44,
      width: 44,
      height: 16,
      x: 0,
      y: 100,
      toJSON: () => ({}),
    } as DOMRect);
    fireEvent.mouseEnter(clickTarget);

    const card = document.body.querySelector(
      ".rounded-lg.shadow-lg",
    ) as HTMLElement;
    // Card sits 8px to the right of the bar's right edge (44px)
    expect(card.style.left).toBe("52px");
    expect(card.style.right).toBe("");
  });

  test("preview card has arrow element on its left edge", () => {
    const items = createPairedItems();
    const { container } = render(
      <MessageTimelineRail items={items} onNavigate={onNavigate} />,
    );

    const clickTarget = container.querySelector(
      "button > span.cursor-pointer",
    )!;
    fireEvent.mouseEnter(clickTarget);

    const card = document.body.querySelector(".rounded-lg.shadow-lg")!;
    const arrow = card.querySelector(".rotate-45") as HTMLElement;
    expect(arrow).toBeInTheDocument();
    // Arrow points left toward the rail on the left edge
    expect(arrow.style.left).toBe("-4px");
    expect(arrow.style.right).toBe("");
  });
});
