/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { Permission } from "../../../types";
import { RolesPanel } from "../RolesPanel";

const { list, update, updateQuota } = vi.hoisted(() => ({
  list: vi.fn(),
  update: vi.fn(),
  updateQuota: vi.fn(),
}));
vi.mock("../../../services/api", () => ({
  roleApi: { list, update, updateQuota },
  authApi: {
    getPermissions: vi
      .fn()
      .mockResolvedValue({ groups: [], all_permissions: [] }),
  },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <section>
      {children}
      {footer}
    </section>
  ),
}));
afterEach(cleanup);
beforeEach(() => {
  list.mockReset().mockResolvedValue({
    roles: [
      {
        id: "research",
        name: "Research",
        is_system: false,
        permissions: [Permission.ROLE_MANAGE],
        limits: {
          five_hour_budget_usd: 0,
          weekly_budget_usd: 12.5,
          max_channels: 3,
        },
      },
    ],
    total: 1,
  });
  update
    .mockReset()
    .mockResolvedValue({ id: "research", name: "Research", permissions: [] });
  updateQuota.mockReset().mockResolvedValue({
    id: "admin",
    name: "Admin",
    is_system: true,
    permissions: [],
  });
});

async function openEditor() {
  render(<RolesPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("common.edit") }),
  );
}

test("editing a role preserves configured USD budgets and other limits", async () => {
  await openEditor();
  expect(screen.getByLabelText(i18n.t("roles.fiveHourBudgetUsd"))).toHaveValue(
    0,
  );
  expect(screen.getByLabelText(i18n.t("roles.weeklyBudgetUsd"))).toHaveValue(
    12.5,
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "research",
      expect.objectContaining({
        limits: expect.objectContaining({
          five_hour_budget_usd: 0,
          weekly_budget_usd: 12.5,
          max_channels: 3,
        }),
      }),
    ),
  );
});

test("clearing a role budget sends null to remove the limit", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText(i18n.t("roles.fiveHourBudgetUsd")), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "research",
      expect.objectContaining({
        limits: expect.objectContaining({
          five_hour_budget_usd: null,
          weekly_budget_usd: 12.5,
        }),
      }),
    ),
  );
});

test("negative role budgets are rejected before saving", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText(i18n.t("roles.fiveHourBudgetUsd")), {
    target: { value: "-1" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(
    await screen.findByText(i18n.t("roles.validation.budgetNonnegative")),
  ).toBeInTheDocument();
  expect(update).not.toHaveBeenCalled();
});

test("system roles show only budget controls and save through the quota-only endpoint", async () => {
  list.mockResolvedValue({
    roles: [
      {
        id: "admin",
        name: "Admin",
        is_system: true,
        permissions: [Permission.ROLE_MANAGE],
        limits: {
          five_hour_budget_usd: 5,
          weekly_budget_usd: 25,
          max_channels: 3,
        },
      },
    ],
    total: 1,
  });
  await openEditor();
  const form = screen.getByLabelText(i18n.t("roles.roleName")).closest("form");
  expect(form).toContainElement(
    screen.getByText(i18n.t("roles.systemRoleHint")),
  );
  expect(screen.getByLabelText(i18n.t("roles.roleName"))).toBeDisabled();
  expect(screen.queryByLabelText(i18n.t("roles.description"))).toBeNull();
  expect(screen.queryByLabelText(i18n.t("roles.maxChannels"))).toBeNull();
  expect(screen.queryByText(i18n.t("roles.uploadLimitsTitle"))).toBeNull();
  expect(screen.queryByText(i18n.t("roles.permissions"))).toBeNull();
  fireEvent.change(screen.getByLabelText(i18n.t("roles.fiveHourBudgetUsd")), {
    target: { value: "0" },
  });
  fireEvent.change(screen.getByLabelText(i18n.t("roles.weeklyBudgetUsd")), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(updateQuota).toHaveBeenCalledWith("admin", {
      five_hour_budget_usd: 0,
      weekly_budget_usd: null,
    }),
  );
  expect(update).not.toHaveBeenCalled();
});
