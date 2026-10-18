/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { Role } from "../../../types";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { RolesPanel } from "../RolesPanel";

const roles: Role[] = ["Alpha", "Beta"].map((name) => ({
  id: name.toLowerCase(),
  name,
  description: `${name} description`,
  permissions: [],
  is_system: false,
  created_at: "2026-10-18T00:00:00Z",
  updated_at: "2026-10-18T00:00:00Z",
}));

vi.mock("../../../services/api", () => ({
  roleApi: { list: vi.fn(async () => ({ roles, total: roles.length })) },
  authApi: {
    getPermissions: vi.fn(async () => ({ groups: [], all_permissions: [] })),
  },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

beforeEach(() => {
  resetRightPanelCoordinator();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});
afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test.each([
  ["title", "Alpha"],
  ["title", "Beta"],
  ["card", "Alpha"],
  ["card", "Beta"],
])(
  "clicking the %s reopens collapsed role details for %s",
  async (target, name) => {
    render(<RolesPanel />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Alpha", exact: true }),
    );
    const panel = screen.getByRole("complementary", { name: "Alpha" });
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    expect(panel).not.toBeVisible();
    expect(
      screen.getByRole("button", { name: i18n.t("common.expandPanel") }),
    ).toBeVisible();

    const title = screen.getByRole("button", { name, exact: true });
    fireEvent.click(
      target === "title" ? title : title.closest(".resource-detail-card")!,
    );

    expect(screen.getByRole("complementary", { name })).toBe(panel);
    expect(panel).toBeVisible();
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(screen.getByRole("tab", { name })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.queryByRole("button", { name: i18n.t("common.expandPanel") }),
    ).toBeNull();
  },
);

test.each(["other", "create"])(
  "role editor preserves the same draft but resets for %s",
  async (target) => {
    render(<RolesPanel />);
    await screen.findByRole("button", { name: "Alpha", exact: true });
    const edit = (name: string) =>
      within(
        screen
          .getByRole("button", { name, exact: true })
          .closest(".resource-detail-card") as HTMLElement,
      ).getByRole("button", { name: i18n.t("common.edit") });
    fireEvent.click(edit("Alpha"));
    const draft = screen.getByLabelText(i18n.t("roles.roleName"));
    fireEvent.change(draft, { target: { value: "Unsaved Alpha" } });
    fireEvent.change(screen.getByLabelText(i18n.t("roles.weeklyBudgetUsd")), {
      target: { value: "42" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    fireEvent.click(edit("Alpha"));
    expect(screen.getByLabelText(i18n.t("roles.roleName"))).toBe(draft);
    expect(draft).toHaveValue("Unsaved Alpha");
    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("common.collapsePanel") }),
    );
    fireEvent.click(
      target === "other"
        ? edit("Beta")
        : screen.getByRole("button", { name: i18n.t("roles.createRole") }),
    );
    expect(screen.getByLabelText(i18n.t("roles.roleName"))).toHaveValue(
      target === "other" ? "Beta" : "",
    );
    expect(screen.getByLabelText(i18n.t("roles.weeklyBudgetUsd"))).toHaveValue(
      null,
    );
    expect(screen.getByLabelText(i18n.t("roles.roleName"))).not.toBe(draft);
  },
);
