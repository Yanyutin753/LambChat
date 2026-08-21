// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { SessionItem } from "../SessionItem";
import type { BackendSession } from "../../../services/api/session";

const baseSession = {
  id: "sess_1",
  agent_id: "agent_1",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
  is_active: true,
  metadata: {},
} satisfies BackendSession;

describe("SessionItem task running indicator", () => {
  it("shows spinner when task_status is running", () => {
    const view = render(
      <SessionItem
        session={{ ...baseSession, metadata: { task_status: "running" } }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    const indicator = document.querySelector(".animate-spin")?.parentElement;
    expect(indicator).toHaveAttribute("title", "运行中");
    expect(indicator).toHaveAttribute("aria-label", "运行中");
    fireEvent.touchStart(view.container.firstElementChild!, {
      touches: [{ clientX: 10, clientY: 10 }],
    });
    expect(view.getByText("运行中")).toBeInTheDocument();
  });
  it("shows spinner when task_status is pending", () => {
    render(
      <SessionItem
        session={{ ...baseSession, metadata: { task_status: "pending" } }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    const indicator = document.querySelector(".animate-spin")?.parentElement;
    expect(indicator).toHaveAttribute("title", "等待中");
    expect(indicator).toHaveAttribute("aria-label", "等待中");
  });
  it("shows only a running-indicator-sized icon while waiting for a reply", () => {
    render(
      <SessionItem
        session={{ ...baseSession, metadata: { task_status: "waiting_human" } }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    const indicator = document.querySelector("[data-session-status=ask-human]");
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveClass("w-4", "h-4");
    expect(indicator).not.toHaveClass("border", "bg-amber-100/70");
    expect(indicator?.textContent).toBe("");
    expect(indicator?.querySelector("svg")).toHaveAttribute("width", "16");
    expect(indicator?.querySelector("svg")).toHaveAttribute("height", "16");
  });
  it("hides spinner when task_status is completed", () => {
    render(
      <SessionItem
        session={{ ...baseSession, metadata: { task_status: "completed" } }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument();
  });
  it("hides spinner when task_status is absent", () => {
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument();
  });
});
