/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test } from "vitest";
import en from "../../../../../i18n/locales/en.json";
import { StartBackgroundTaskItem } from "../StartBackgroundTaskItem";

const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });
afterEach(cleanup);

function show(props: React.ComponentProps<typeof StartBackgroundTaskItem>) {
  return render(<MemoryRouter><I18nextProvider i18n={i18n}><StartBackgroundTaskItem {...props} /></I18nextProvider></MemoryRouter>);
}

test.each(["queued", "running"])("submitted %s task links to its ordinary conversation without claiming completion", (status) => {
  const view = show({ args: { description: "Research overnight" }, success: true,
    result: { session_id: "child-session", run_id: "run-1", task_id: "task-1", parent_session_id: "parent", status } });
  const link = view.getByRole("link", { name: "Open background conversation" });
  expect(link.getAttribute("href")).toBe("/chat/child-session");
  expect(view.container.textContent).not.toMatch(/completed|finished/i);
});

test.each([{ isPending: true }, { success: false, result: { status: "error", error_code: "background_task_unavailable", session_id: "partial" } }, { cancelled: true, result: { session_id: "partial", status: "queued" } }])("pending, failed and cancelled submissions expose no success link", (state) => {
  const view = show({ args: { description: "Research" }, ...state });
  expect(view.queryByRole("link")).toBeNull();
});

test("session IDs cannot escape the normal chat route", () => {
  const view = show({ args: {}, success: true, result: JSON.stringify({ session_id: "other/../../settings", status: "queued" }) });
  expect(view.getByRole("link").getAttribute("href")).toBe("/chat/other%2F..%2F..%2Fsettings");
});
