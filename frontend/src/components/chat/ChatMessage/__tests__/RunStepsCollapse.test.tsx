// @vitest-environment jsdom

import { describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { RunStepsCollapse } from "../RunStepsCollapse";

// Mock i18next with simple {{var}} interpolation
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: unknown) => {
      const templates: Record<string, string> = {
        "chat.message.runStepsSummary":
          "Worked for {{duration}} · {{count}} steps",
        "chat.message.runStepsCount": "{{count}} steps",
        "chat.message.runStepsWorking": "Working… {{duration}}",
      };
      let out = templates[key] ?? key;
      if (opts && typeof opts === "object") {
        for (const [k, v] of Object.entries(opts as Record<string, unknown>)) {
          out = out.split(`{{${k}}}`).join(String(v));
        }
      }
      return out;
    },
  }),
}));

function ToggleButton() {
  return screen.getByRole("button");
}

describe("RunStepsCollapse", () => {
  test("renders step count and compact duration in the summary row", () => {
    render(
      <RunStepsCollapse
        steps={3}
        durationMs={90000}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(ToggleButton().textContent).toContain("1m 30s");
    expect(ToggleButton().textContent).toContain("3");
  });

  test("renders step count alone when duration is unknown", () => {
    render(
      <RunStepsCollapse
        steps={5}
        durationMs={null}
        renderExpanded={() => <div>step-details</div>}
      />,
    );
    expect(ToggleButton().textContent).toContain("5");
  });

  test("shows a live working timer while the run is active", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T10:00:45Z"));
    try {
      render(
        <RunStepsCollapse
          active
          steps={0}
          durationMs={null}
          startedAtMs={Date.now() - 45000}
          renderExpanded={() => <div>step-details</div>}
        />,
      );
      expect(ToggleButton().textContent).toContain("Working");
      expect(ToggleButton().textContent).toContain("45s");

      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(ToggleButton().textContent).toContain("46s");
    } finally {
      vi.useRealTimers();
    }
  });

  test("hides expanded content until toggled and does not render it while collapsed", () => {
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
    expect(ToggleButton().getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(ToggleButton());
    expect(renderExpanded).toHaveBeenCalledTimes(1);
    expect(screen.getByText("step-details")).toBeTruthy();
    expect(ToggleButton().getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(ToggleButton());
    expect(screen.queryByText("step-details")).toBeNull();
    expect(ToggleButton().getAttribute("aria-expanded")).toBe("false");
  });
});
