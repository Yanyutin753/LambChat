/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { FeatureMenu } from "../FeatureMenu";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("collapsed feature groups are hidden from assistive technology and Escape restores the trigger", async () => {
  const open = vi.fn();
  const user = userEvent.setup();
  render(
    <FeatureMenu
      activePanel={null}
      onOpen={open}
      enabledToolsCount={1}
      totalToolsCount={1}
      enabledSkillsCount={2}
      totalSkillsCount={2}
      hasPersonaSelector
      uploadCategories={[]}
      onUploadFiles={() => {}}
    />,
  );
  const trigger = screen.getByRole("button", { name: "chat.features" });
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  const enhance = screen.getByRole("button", { name: "featureMenu.enhance" });
  expect(enhance).toHaveFocus();
  expect(enhance).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("button", { name: "featureMenu.persona" }),
  ).toBeNull();
  const body = document.getElementById(enhance.getAttribute("aria-controls")!);
  expect(body).toHaveAttribute("inert");
  await user.keyboard("{Enter}");
  expect(enhance).toHaveAttribute("aria-expanded", "true");
  await user.tab();
  expect(
    screen.getByRole("button", { name: "featureMenu.persona" }),
  ).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(trigger).toHaveFocus();
  expect(open).not.toHaveBeenCalled();
});

test("Tab after the last feature returns to the next composer action and closes the portal", async () => {
  const user = userEvent.setup();
  render(
    <>
      <FeatureMenu
        activePanel={null}
        onOpen={() => {}}
        enabledToolsCount={0}
        totalToolsCount={0}
        enabledSkillsCount={0}
        totalSkillsCount={0}
        uploadCategories={["image"]}
        onUploadFiles={() => {}}
      />
      <button>Next composer action</button>
    </>,
  );
  const trigger = screen.getByRole("button", { name: "chat.features" });
  await user.click(trigger);
  expect(
    screen.getByRole("button", { name: "featureMenu.upload" }),
  ).toHaveFocus();
  await user.tab();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.getByRole("button", { name: "Next composer action" }),
  ).toHaveFocus();
  expect(
    within(document.body).queryByRole("button", { name: "featureMenu.upload" }),
  ).toBeNull();
});

test("the feature popup fits the visible space above the composer", async () => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    top: 180,
    left: 12,
  } as DOMRect);
  vi.stubGlobal("visualViewport", {
    offsetTop: 60,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  const user = userEvent.setup();
  render(
    <FeatureMenu
      activePanel={null}
      onOpen={() => {}}
      enabledToolsCount={1}
      totalToolsCount={1}
      enabledSkillsCount={0}
      totalSkillsCount={0}
      uploadCategories={[]}
      onUploadFiles={() => {}}
    />,
  );
  await user.click(screen.getByRole("button", { name: "chat.features" }));
  expect(document.querySelector(".feature-menu-dropdown")).toHaveStyle({
    maxHeight: "104px",
  });
});
