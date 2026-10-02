// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, within } from "@testing-library/react";
import { SessionItem } from "../SessionItem";
import type { BackendSession } from "../../../services/api/session";

// Keep label assertions locale-independent: return the in-code fallback text
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, defaultValue?: string) => defaultValue ?? key,
      i18n: { language: "zh" },
    }),
  };
});

const baseSession = {
  id: "sess_1",
  agent_id: "agent_1",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
  is_active: true,
  metadata: {},
} satisfies BackendSession;

function renderSessionItem(metadata: Record<string, unknown>) {
  const view = render(
    <SessionItem
      session={{ ...baseSession, metadata }}
      isActive={false}
      projects={[]}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      onMoveToProject={vi.fn()}
      onSessionUpdate={vi.fn()}
    />,
  );
  return { ...view, row: view.container.firstElementChild as HTMLElement };
}

const touchRow = (row: HTMLElement) =>
  fireEvent.touchStart(row, { touches: [{ clientX: 10, clientY: 10 }] });

describe("SessionItem task running indicator", () => {
  it("labels the running spinner via aria-label without a native title", () => {
    renderSessionItem({ task_status: "running" });
    const indicator = document.querySelector(".animate-spin")?.parentElement;
    expect(indicator).toHaveAttribute("aria-label", "运行中");
    expect(indicator).not.toHaveAttribute("title");
  });
  it("labels the pending spinner via aria-label", () => {
    renderSessionItem({ task_status: "pending" });
    const indicator = document.querySelector(".animate-spin")?.parentElement;
    expect(indicator).toHaveAttribute("aria-label", "等待中");
  });
  it("does not pop the running label bubble when the row is touched", () => {
    const { row } = renderSessionItem({ task_status: "running" });
    expect(within(row).queryByText("运行中")).not.toBeInTheDocument();
    touchRow(row);
    expect(within(document.body).queryByText("运行中")).not.toBeInTheDocument();
    expect(
      document.querySelector(".animate-spin")?.parentElement?.textContent,
    ).toBe("");
  });
  it("does not pop the waiting-for-reply bubble when the row is touched", () => {
    const { row } = renderSessionItem({ task_status: "waiting_human" });
    expect(within(row).queryByText("等待回复")).not.toBeInTheDocument();
    touchRow(row);
    expect(
      within(document.body).queryByText("等待回复"),
    ).not.toBeInTheDocument();
  });
  it("still shows the running label after a deliberate long press on the spinner", () => {
    const { row } = renderSessionItem({ task_status: "running" });
    const spinner = document.querySelector(".animate-spin")?.parentElement;
    expect(spinner).toBeTruthy();
    vi.useFakeTimers();
    try {
      fireEvent.touchStart(spinner!, { touches: [{ clientX: 0, clientY: 0 }] });
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(within(document.body).queryByText("运行中")).toBeInTheDocument();
      expect(within(row).queryByText("运行中")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
  it("shows only a running-indicator-sized icon while waiting for a reply", () => {
    renderSessionItem({ task_status: "waiting_human" });
    const indicator = document.querySelector("[data-session-status=ask-human]");
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveClass("w-4", "h-4");
    expect(indicator).not.toHaveClass("border", "bg-amber-100/70");
    expect(indicator?.textContent).toBe("");
    expect(indicator?.querySelector("svg")).toHaveAttribute("width", "16");
    expect(indicator?.querySelector("svg")).toHaveAttribute("height", "16");
  });
  it("hides spinner when task_status is completed", () => {
    renderSessionItem({ task_status: "completed" });
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument();
  });
  it("hides spinner when task_status is absent", () => {
    renderSessionItem({});
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument();
  });
});

describe("SessionItem more-options button tooltip", () => {
  it("reveals the more-options button itself on touch, without popping its bubble", () => {
    // The i18n mock returns the key itself when no in-code fallback exists
    const { row } = renderSessionItem({});
    const moreButton = within(row).getByRole("button", {
      name: "sidebar.moreOptions",
    });
    expect(moreButton).not.toHaveAttribute("title");
    expect(moreButton).toHaveAttribute("aria-label", "sidebar.moreOptions");
    touchRow(row);
    // 触摸后按钮亮出（opacity 1），但不再强制弹出气泡
    expect(moreButton).toHaveStyle({ opacity: "1" });
    expect(
      within(document.body).queryByText("sidebar.moreOptions"),
    ).not.toBeInTheDocument();
    expect(
      within(row).queryByText("sidebar.moreOptions"),
    ).not.toBeInTheDocument();
  });
});
