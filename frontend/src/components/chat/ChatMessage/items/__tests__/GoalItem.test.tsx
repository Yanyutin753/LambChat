/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import en from "../../../../../i18n/locales/en.json";
import { GoalItem } from "../GoalItem";
import {
  getPersistentToolPanelState,
  closePersistentToolPanel,
} from "../persistentToolPanelState";

const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });
afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test.each(["get_goal", "update_goal"] as const)(
  "%s has an accessible dedicated Goal item",
  (toolName) => {
    const view = render(
      <I18nextProvider i18n={i18n}>
        <GoalItem toolName={toolName} args={{}} isPending />
      </I18nextProvider>,
    );
    expect(view.getByRole("button").textContent).toContain(
      toolName === "get_goal" ? "Read goal" : "Submit goal audit",
    );
  },
);

test("submitting completion does not claim the Goal is already completed", () => {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <GoalItem
        toolName="update_goal"
        args={{ status: "complete" }}
        success
        result="Self-audit recorded for turn-end validation."
      />
    </I18nextProvider>,
  );
  expect(view.container.textContent).toContain("Submit goal audit");
  expect(view.container.textContent).not.toMatch(/Goal completed/i);
});

test("goal details show the objective and criteria instead of protocol JSON", () => {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <GoalItem
        toolName="get_goal"
        args={{}}
        success
        result={{
          status: "active",
          objective: "Ship the report",
          rubric: "Verify totals",
          turn: 2,
          tokens_used: 1234,
          requirements: [{ id: "r0", text: "Ship the report" }],
        }}
      />
    </I18nextProvider>,
  );
  fireEvent.click(view.getByRole("button"));
  const panel = getPersistentToolPanelState();
  const detail = render(
    <I18nextProvider i18n={i18n}>{panel?.children}</I18nextProvider>,
  );
  expect(within(detail.container).getByText("Ship the report")).toBeTruthy();
  expect(within(detail.container).getByText("Verify totals")).toBeTruthy();
  expect(within(detail.container).getByText("Active")).toBeTruthy();
  expect(detail.container.textContent).not.toContain("tokens_used");
  expect(detail.container.textContent).not.toMatch(/1234|r0|Working on turn/);
});

test.each([
  {
    success: true,
    result: "Self-audit recorded for turn-end validation.",
    expected: "Awaiting validation",
  },
  {
    success: false,
    result: { status: "error", error: "Evidence changed" },
    expected: "Evidence changed",
  },
  { cancelled: true, expected: "Cancelled" },
])("audit details preserve pending or failed outcomes: $expected", (state) => {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <GoalItem
        toolName="update_goal"
        args={{ status: "complete", explanation: "Checked the final report" }}
        {...state}
      />
    </I18nextProvider>,
  );
  fireEvent.click(view.getByRole("button"));
  const detail = render(
    <I18nextProvider i18n={i18n}>
      {getPersistentToolPanelState()?.children}
    </I18nextProvider>,
  );
  expect(within(detail.container).getByText(state.expected)).toBeTruthy();
  expect(
    within(detail.container).getByText("Checked the final report"),
  ).toBeTruthy();
  expect(within(detail.container).queryByText("Completed")).toBeNull();
});
