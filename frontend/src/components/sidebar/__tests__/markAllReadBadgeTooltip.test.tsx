// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, within } from "@testing-library/react";
import { MarkAllReadBadge } from "../MarkAllReadBadge";

const renderBadge = () =>
  render(
    <MarkAllReadBadge
      count={3}
      badgeId="badge"
      markingReadId={null}
      onMarkAllRead={() => {}}
      tooltip="全部已读"
    />,
  );

const getBadge = () => document.querySelector("[role=button]") as HTMLElement;

describe("MarkAllReadBadge tooltip", () => {
  it("shows a tooltip bubble on hover instead of a native title", () => {
    renderBadge();
    const badge = getBadge();
    expect(badge).not.toHaveAttribute("title");
    expect(badge).toHaveAttribute("aria-label", "全部已读");
    fireEvent.mouseEnter(badge);
    expect(within(document.body).getByText("全部已读")).toHaveClass(
      "fixed",
      "pointer-events-none",
    );
  });

  it("shows the tooltip bubble after a long press on touch", () => {
    vi.useFakeTimers();
    try {
      renderBadge();
      const badge = getBadge();
      fireEvent.touchStart(badge);
      expect(
        within(document.body).queryByText("全部已读"),
      ).not.toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(within(document.body).getByText("全部已读")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
