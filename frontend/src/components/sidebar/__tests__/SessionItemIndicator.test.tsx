// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, within } from "@testing-library/react";
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
  it("shows the running label as a tooltip bubble, not inline text, on touch", () => {
    const { row } = renderSessionItem({ task_status: "running" });
    expect(within(row).queryByText("运行中")).not.toBeInTheDocument();
    touchRow(row);
    const bubble = within(document.body).getByText("运行中");
    expect(bubble).toHaveClass("fixed", "pointer-events-none");
    expect(
      document.querySelector(".animate-spin")?.parentElement?.textContent,
    ).toBe("");
  });
  it("shows the waiting-for-reply label as a tooltip bubble, not inline text, on touch", () => {
    const { row } = renderSessionItem({ task_status: "waiting_human" });
    expect(within(row).queryByText("等待回复")).not.toBeInTheDocument();
    touchRow(row);
    const bubble = within(document.body).getByText("等待回复");
    expect(bubble).toHaveClass("fixed", "pointer-events-none");
    expect(
      document.querySelector("[data-session-status=ask-human]")?.textContent,
    ).toBe("");
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
  it("reveals the more-options label as a tooltip bubble on touch", () => {
    // The i18n mock returns the key itself when no in-code fallback exists
    const { row } = renderSessionItem({});
    const moreButton = row.querySelector("button");
    expect(moreButton).not.toHaveAttribute("title");
    expect(moreButton).toHaveAttribute("aria-label", "sidebar.moreOptions");
    touchRow(row);
    const bubble = within(document.body).getByText("sidebar.moreOptions");
    expect(bubble).toHaveClass("fixed", "pointer-events-none");
    expect(
      within(row).queryByText("sidebar.moreOptions"),
    ).not.toBeInTheDocument();
  });
});
