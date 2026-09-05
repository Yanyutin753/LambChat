// @vitest-environment jsdom

import { describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { RunStepsCollapse } from "../RunStepsCollapse";

// Mock i18next with simple {{var}} interpolation
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: unknown) => {
      const templates: Record<string, string> = {
        "chat.message.runStepsSummary": "Worked for {{duration}}",
        "chat.message.runStepsCount": "{{count}} steps",
        "chat.message.runStepsWorking": "Working… {{duration}}",
        "chat.message.runStepsWorkingNoTimer": "Working…",
        "chat.message.runStepsStopped": "Stopped",
      };
      let out = templates[key] ?? key;
      if (opts && typeof opts === "object") {
        for (const [k, v] of Object.entries(opts as Record<string, unknown>)) {
          out = out.split(`{{${k}}}`).join(String(v));
        }
      }
      return out;
    },
    i18n: { language: "en" },
  }),
}));

function SummaryRow() {
  return screen.getByRole("button", { expanded: false });
}

function ExpandedSummaryRow() {
  return screen.getByRole("button", { expanded: true });
}

/** 工作中状态行的文案 span（工作中无按钮，只能按文案定位） */
function WorkingRowText() {
  return screen.getByText(/Working/) as HTMLSpanElement;
}

describe("RunStepsCollapse", () => {
  test("renders the duration in the summary row", () => {
    render(
      <RunStepsCollapse
        steps={3}
        durationMs={90000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(SummaryRow().textContent).toContain("1m 30s");
  });

  test("falls back to the step count when duration is unknown", () => {
    render(
      <RunStepsCollapse
        steps={2}
        durationMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(SummaryRow().textContent).toContain("2");
  });

  test("shows the stopped label instead of the working/summary text when stopped", () => {
    render(
      <RunStepsCollapse
        stopped
        steps={3}
        durationMs={90000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    // 已停止不带时长，也不回落到步骤数/已工作摘要
    expect(SummaryRow().textContent).toBe("Stopped");
    expect(SummaryRow().textContent).not.toContain("1m 30s");
    expect(SummaryRow().textContent).not.toContain("Worked for");
    expect(SummaryRow().textContent).not.toContain("steps");
  });

  test("shows the bare stopped label when duration is unknown", () => {
    render(
      <RunStepsCollapse
        stopped
        steps={3}
        durationMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(SummaryRow().textContent).toBe("Stopped");
  });

  test("shows the live timer and full details while active, with no expand/collapse toggle", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T10:00:45Z"));
    try {
      const renderExpanded = vi.fn(() => <div>step-details</div>);
      render(
        <RunStepsCollapse
          active
          steps={1}
          durationMs={null}
          startedAtMs={Date.now() - 45000}
          renderExpanded={renderExpanded}
        />,
      );
      // 工作中：无展开收起控件（无按钮、无 chevron），直接展示完整详情
      expect(screen.queryByRole("button")).toBeNull();
      const row = WorkingRowText().parentElement as HTMLElement;
      expect(row.querySelector("svg")).toBeNull();
      expect(row.textContent).toContain("45s");
      expect(renderExpanded).toHaveBeenCalled();
      expect(screen.getByText("step-details")).toBeTruthy();

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(WorkingRowText().textContent).toContain("46s");
    } finally {
      vi.useRealTimers();
    }
  });

  test("keeps the live timer ahead of a static elapsed estimate while active", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T10:00:45Z"));
    try {
      render(
        <RunStepsCollapse
          active
          steps={1}
          durationMs={30000}
          startedAtMs={Date.now() - 45000}
          renderExpanded={() => <div>step-details</div>}
        />,
      );
      expect(WorkingRowText().textContent).toContain("45s");
      expect(WorkingRowText().textContent).not.toContain("30s");

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(WorkingRowText().textContent).toContain("46s");
    } finally {
      vi.useRealTimers();
    }
  });

  test("collapses automatically once the run finishes", () => {
    const { rerender } = render(
      <RunStepsCollapse
        active
        steps={1}
        durationMs={null}
        startedAtMs={Date.now() - 1000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(screen.getByText("step-details")).toBeTruthy();

    rerender(
      <RunStepsCollapse
        steps={1}
        durationMs={60000}
        startedAtMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(screen.queryByText("step-details")).toBeNull();
    const row = SummaryRow();
    expect(row.textContent).toContain("Worked for 1m 00s");
    expect(row.querySelector("svg")).not.toBeNull();
    expect((row as HTMLButtonElement).disabled).toBe(false);
  });

  test("summary row text uses the body text color in both states", () => {
    const { unmount } = render(
      <RunStepsCollapse
        steps={2}
        durationMs={45000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    const span = SummaryRow().querySelector("span");
    expect(span?.className).toContain("text-gray-700");
    expect(span?.className).toContain("dark:text-gray-300");
    expect(span?.className).not.toContain("text-theme-text-secondary");
    unmount();

    render(
      <RunStepsCollapse
        active
        steps={2}
        durationMs={45000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    const workingSpan = WorkingRowText();
    expect(workingSpan.className).toContain("text-gray-700");
    expect(workingSpan.className).toContain("dark:text-gray-300");
    expect(workingSpan.className).not.toContain("text-theme-text-secondary");
  });

  test("summary row matches the markdown body font size", () => {
    render(
      <RunStepsCollapse
        steps={2}
        durationMs={45000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    const span = SummaryRow().querySelector("span");
    // 与 .markdown-preview 正文一致：桌面 0.9375rem，≤640px 提升到 1rem
    expect(span?.className).toContain("text-[0.9375rem]");
    expect(span?.className).toContain("max-sm:text-base");
  });

  test("summary row divider uses the full theme border color", () => {
    render(
      <RunStepsCollapse
        steps={2}
        durationMs={45000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(SummaryRow().className).toContain("border-theme-border");
    expect(SummaryRow().style.borderColor).toBe("");
  });

  test("shows details again on resume and auto-collapses when the run finishes", () => {
    const { rerender } = render(
      <RunStepsCollapse
        active
        steps={1}
        durationMs={null}
        startedAtMs={Date.now() - 1000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );

    // 第一次结束：自动收起成一行
    rerender(
      <RunStepsCollapse
        steps={1}
        durationMs={60000}
        startedAtMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(screen.queryByText("step-details")).toBeNull();

    // 用户展开历史行后 run 恢复：直接显示详情（无展开收起控件）
    fireEvent.click(SummaryRow());
    rerender(
      <RunStepsCollapse
        active
        steps={1}
        durationMs={null}
        startedAtMs={Date.now() - 1000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("step-details")).toBeTruthy();

    // 再次结束：仍自动收起
    rerender(
      <RunStepsCollapse
        steps={1}
        durationMs={90000}
        startedAtMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(screen.queryByText("step-details")).toBeNull();
  });

  test("shows the full details directly when toggled open", () => {
    const renderExpanded = vi.fn(() => <div>step-details</div>);
    render(
      <RunStepsCollapse
        steps={2}
        durationMs={45000}
        renderExpanded={renderExpanded}
      />,
    );

    expect(renderExpanded).not.toHaveBeenCalled();
    expect(screen.queryByText("step-details")).toBeNull();

    fireEvent.click(SummaryRow());
    expect(renderExpanded).toHaveBeenCalled();
    expect(screen.getByText("step-details")).toBeTruthy();

    fireEvent.click(ExpandedSummaryRow());
    expect(screen.queryByText("step-details")).toBeNull();
  });
});
