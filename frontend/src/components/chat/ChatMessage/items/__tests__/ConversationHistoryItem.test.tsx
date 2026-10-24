/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, test } from "vitest";
import zh from "../../../../../i18n/locales/zh.json";
import { ConversationHistoryItem } from "../ConversationHistoryItem";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

const i18n = createInstance();
await i18n.init({
  lng: "zh",
  resources: { zh: { translation: zh } },
  interpolation: { escapeValue: false },
});

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
});

test("conversation detail renders complete formatted messages instead of search excerpts", () => {
  const view = render(
    <I18nextProvider i18n={i18n}>
      <ConversationHistoryItem
        toolName="get_conversation_detail"
        args={{ session_id: "session-1" }}
        result={{
          session: { name: "研究记录" },
          turns: [
            {
              user_message: "请整理研究结论",
              assistant_final: "## 研究结论\n\n- 第一项\n- 最后一项",
            },
          ],
        }}
        success
      />
    </I18nextProvider>,
  );
  fireEvent.click(within(view.container).getByRole("button"));
  const panel = render(
    <I18nextProvider i18n={i18n}>
      {getPersistentToolPanelState()!.children}
    </I18nextProvider>,
  );
  const content = within(panel.container);
  expect(panel.container.querySelector(".tool-panel-content")).toHaveClass(
    "h-full",
    "min-h-0",
    "overflow-y-auto",
  );
  expect(content.getByText("研究记录")).toBeVisible();
  expect(content.getByText("请整理研究结论")).toBeVisible();
  expect(content.getByRole("heading", { name: "研究结论" })).toBeVisible();
  expect(content.getAllByRole("listitem")).toHaveLength(2);
  expect(content.getByText("最后一项")).toBeVisible();
});
