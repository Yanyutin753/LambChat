/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { SkillsHubPanel } from "../../SkillsHubPanel";

const { config } = vi.hoisted(() => ({
  config: {
    settings: null as object | null,
    isLoading: true,
    error: null,
    enableSkills: false,
  },
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => config,
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => true }),
}));
vi.mock("../../SkillsPanel", () => ({
  SkillsPanel: () => <p>Skills content</p>,
}));
vi.mock("../../MarketplacePanel", () => ({
  MarketplacePanel: () => <p>Marketplace content</p>,
}));
afterEach(cleanup);

test.each(["/skills", "/marketplace"])(
  "%s waits for configuration before declaring skills disabled",
  (path) => {
    Object.assign(config, {
      settings: null,
      isLoading: true,
      enableSkills: false,
    });
    const view = render(
      <MemoryRouter initialEntries={[path]}>
        <SkillsHubPanel />
      </MemoryRouter>,
    );
    expect(screen.queryByText(i18n.t("skills.featureDisabled"))).toBeNull();
    expect(view.container.querySelector(".skeleton-line")).not.toBeNull();
    Object.assign(config, { settings: {}, isLoading: false });
    view.rerender(
      <MemoryRouter initialEntries={[path]}>
        <SkillsHubPanel />
      </MemoryRouter>,
    );
    expect(screen.getByText(i18n.t("skills.featureDisabled"))).toBeTruthy();
    config.enableSkills = true;
    view.rerender(
      <MemoryRouter initialEntries={[path]}>
        <SkillsHubPanel />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(
        path === "/marketplace" ? "Marketplace content" : "Skills content",
      ),
    ).toBeTruthy();
  },
);

test("the first render waits before the configuration request starts", () => {
  Object.assign(config, {
    settings: null,
    isLoading: false,
    enableSkills: false,
  });
  const view = render(
    <MemoryRouter>
      <SkillsHubPanel />
    </MemoryRouter>,
  );
  expect(screen.queryByText(i18n.t("skills.featureDisabled"))).toBeNull();
  expect(view.container.querySelector(".skeleton-line")).not.toBeNull();
});
