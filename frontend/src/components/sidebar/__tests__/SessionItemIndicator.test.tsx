// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
    render(
      <SessionItem
        session={{ ...baseSession, task_status: "running" }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });
  it("shows spinner when task_status is pending", () => {
    render(
      <SessionItem
        session={{ ...baseSession, task_status: "pending" }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });
  it("hides spinner when task_status is completed", () => {
    render(
      <SessionItem
        session={{ ...baseSession, task_status: "completed" }}
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
  it("hides spinner when task_status is null", () => {
    render(
      <SessionItem
        session={{ ...baseSession, task_status: null }}
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
