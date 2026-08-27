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

  test("starts expanded with a live timer while the run is active, without chevron or toggle", () => {
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
      const row = ExpandedSummaryRow();
      expect(row.textContent).toContain("Working");
      expect(row.textContent).toContain("45s");
      expect(row.querySelector("svg")).toBeNull();
      expect((row as HTMLButtonElement).disabled).toBe(true);
      expect(renderExpanded).toHaveBeenCalled();
      expect(screen.getByText("step-details")).toBeTruthy();

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(ExpandedSummaryRow().textContent).toContain("46s");
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
      const row = ExpandedSummaryRow();
      expect(row.textContent).toContain("45s");
      expect(row.textContent).not.toContain("30s");

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(ExpandedSummaryRow().textContent).toContain("46s");
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
    let span = SummaryRow().querySelector("span");
    expect(span?.className).toContain("text-theme-text-secondary");
    expect(span?.className).not.toContain("text-theme-text-tertiary");
    unmount();

    render(
      <RunStepsCollapse
        active
        steps={2}
        durationMs={45000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    span = ExpandedSummaryRow().querySelector("span");
    expect(span?.className).toContain("text-theme-text-secondary");
    expect(span?.className).not.toContain("text-theme-text-tertiary");
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
