/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { RoleDetailSidebar } from "../RoleDetailSidebar";
import { Permission, type Role } from "../../../types";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
beforeEach(() => resetRightPanelCoordinator());
afterEach(cleanup);
const role: Role = {
  id: "system",
  name: "Administrator",
  permissions: [Permission.ROLE_MANAGE],
  is_system: true,
  created_at: "2026-10-01",
  updated_at: "2026-10-01",
};

test("system role detail explains its protected status without offering deletion", () => {
  render(
    <RoleDetailSidebar
      role={role}
      permissionGroups={[]}
      permissionLabels={{}}
      onClose={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  expect(
    within(screen.getByRole("tabpanel", { name: role.name })).getByText(
      i18n.t("roles.systemRole"),
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: i18n.t("common.delete") }),
  ).toBeNull();
  expect(
    screen.getByRole("button", { name: i18n.t("common.edit") }),
  ).toBeInTheDocument();
});

test("a role without permissions displays an explicit zero count", () => {
  render(
    <RoleDetailSidebar
      role={{ ...role, permissions: [] }}
      permissionGroups={[]}
      permissionLabels={{}}
      onClose={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  expect(
    within(screen.getByRole("tabpanel", { name: role.name })).getByText(
      i18n.t("roles.permissionCount", { count: 0 }),
    ),
  ).toBeInTheDocument();
});

test("role detail displays USD quotas including a zero budget", () => {
  render(
    <RoleDetailSidebar
      role={{
        ...role,
        limits: { five_hour_budget_usd: 0, weekly_budget_usd: 12.5 },
      }}
      permissionGroups={[]}
      permissionLabels={{}}
      onClose={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  expect(
    screen.getByText(i18n.t("roles.fiveHourBudgetUsd")),
  ).toBeInTheDocument();
  expect(screen.getByText(i18n.t("roles.weeklyBudgetUsd"))).toBeInTheDocument();
  expect(screen.getByText("$0.00")).toBeInTheDocument();
  expect(screen.getByText("$12.50")).toBeInTheDocument();
});
