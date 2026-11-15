/** @vitest-environment jsdom */
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import i18n from "../../../i18n";
import { ChatHeaderFrame } from "../../layout/AppContent/ChatHeaderFrame";
import { RightPanelTabs } from "../RightPanelTabs";
import {
  collapseRightPanel,
  registerRightPanel,
  resetRightPanelCoordinator,
} from "../rightPanelCoordinator";

afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});
test("collapsed panel controls occupy the header instead of covering its actions", () => {
  registerRightPanel({
    id: Symbol(),
    kind: "content",
    automatic: false,
    close: () => {},
    opener: null,
    title: "report.txt",
  });
  render(
    <>
      <ChatHeaderFrame>
        <button>Files</button>
        <button>Account</button>
      </ChatHeaderFrame>
      <RightPanelTabs />
    </>,
  );
  act(() => collapseRightPanel());
  const header = screen.getByRole("banner");
  const restore = within(header).getByRole("button", {
    name: i18n.t("common.expandPanel"),
  });
  expect(restore).toBeVisible();
  expect(restore).toHaveFocus();
  expect(within(header).getByRole("button", { name: "Files" })).toBeVisible();
});
