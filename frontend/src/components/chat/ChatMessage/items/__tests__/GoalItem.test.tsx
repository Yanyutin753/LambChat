/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import en from "../../../../../i18n/locales/en.json";
import { GoalItem } from "../GoalItem";

const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });
afterEach(cleanup);

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
