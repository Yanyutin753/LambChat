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
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { UsersPanel } from "../UsersPanel";
import { RolesPanel } from "../RolesPanel";
import { UserQuotaControls } from "../UserQuotaControls";

const mocks = vi.hoisted(() => ({
  permissions: new Set<string>(),
  updateUser: vi.fn(),
  updateRole: vi.fn(),
  getUserQuota: vi.fn(),
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "operator",
      grantable_permissions: [],
      assignable_role_ids: [],
    },
    hasPermission: (permission: string) => mocks.permissions.has(permission),
  }),
}));
vi.mock("../../../services/api", () => ({
  getFullUrl: (value: string) => value,
  userApi: {
    list: vi.fn(async () => ({
      users: [
        {
          id: "target",
          username: "Target",
          email: "target@example.com",
          roles: ["member"],
          is_active: true,
          created_at: "2026-10-24",
        },
      ],
      total: 1,
    })),
    update: mocks.updateUser,
  },
  roleApi: {
    list: vi.fn(async () => ({
      roles: [
        {
          id: "member",
          name: "Member",
          permissions: ["chat:write"],
          limits: {
            five_hour_budget_usd: 5,
            weekly_budget_usd: 15,
            max_files: 7,
            max_concurrent_chats: 2,
          },
          is_system: false,
          created_at: "2026-10-24",
          updated_at: "2026-10-24",
        },
      ],
      total: 1,
    })),
    update: mocks.updateRole,
  },
  authApi: {
    getPermissions: vi.fn(async () => ({
      groups: [
        {
          name: "Chat",
          permissions: [
            { value: "chat:write", label: "Chat", description: "Chat" },
          ],
        },
      ],
      all_permissions: [],
    })),
  },
}));
vi.mock("../../../services/api/usage", () => ({
  usageApi: { getUserQuota: mocks.getUserQuota },
}));
beforeEach(() => {
  resetRightPanelCoordinator();
  mocks.permissions = new Set();
  mocks.updateUser.mockReset().mockResolvedValue({});
  mocks.updateRole.mockReset().mockImplementation(async (id, data) => ({
    id,
    name: "Member",
    permissions: ["chat:write"],
    is_system: false,
    created_at: "2026-10-24",
    updated_at: "2026-10-24",
    ...data,
  }));
  mocks.getUserQuota.mockReset();
});
afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test("profile editors cannot create users, change passwords, status or role assignments", async () => {
  mocks.permissions = new Set(["user:read", "user:write"]);
  render(<UsersPanel />);
  fireEvent.click(
    (await screen.findAllByRole("button", { name: i18n.t("users.edit") }))[0],
  );
  expect(
    screen.queryByRole("button", { name: i18n.t("users.createUser") }),
  ).toBeNull();
  expect(document.querySelector('input[type="password"]')).toBeNull();
  fireEvent.change(screen.getByLabelText(i18n.t("users.username")), {
    target: { value: "Renamed" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(mocks.updateUser).toHaveBeenCalledWith("target", {
      username: "Renamed",
    }),
  );
});

test("role metadata editors do not submit permissions, delegation scopes or quotas", async () => {
  mocks.permissions = new Set(["role:read", "role:write"]);
  render(<RolesPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("common.edit") }),
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(mocks.updateRole).toHaveBeenCalledWith("member", {
      name: "Member",
      description: "",
    }),
  );
  expect(
    screen.queryByRole("button", { name: i18n.t("common.delete") }),
  ).toBeNull();
});

test("global usage viewing does not authorize quota changes or issuance", () => {
  mocks.permissions = new Set(["usage:admin"]);
  const { container } = render(<UserQuotaControls userId="target" />);
  expect(container).toBeEmptyDOMElement();
  expect(mocks.getUserQuota).not.toHaveBeenCalled();
});

test("status operators submit account status without profile or authority fields", async () => {
  mocks.permissions = new Set(["user:read", "user:status"]);
  render(<UsersPanel />);
  fireEvent.click(
    (await screen.findAllByRole("button", { name: i18n.t("users.edit") }))[0],
  );
  expect(screen.getByLabelText(i18n.t("users.username"))).toBeDisabled();
  fireEvent.click(
    screen.getByRole("checkbox", { name: i18n.t("users.enableAccount") }),
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(mocks.updateUser).toHaveBeenCalledWith("target", {
      is_active: false,
    }),
  );
});

test("read-only role viewers cannot open mutation forms", async () => {
  mocks.permissions = new Set(["role:read"]);
  render(<RolesPanel />);
  await screen.findByRole("button", { name: "Member" });
  expect(
    screen.queryByRole("button", { name: i18n.t("common.edit") }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: i18n.t("common.delete") }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: i18n.t("roles.createRole") }),
  ).toBeNull();
});

test("delegated grant and quota editors omit metadata limits they cannot write", async () => {
  mocks.permissions = new Set([
    "role:read",
    "role:grant",
    "usage:quota_manage",
  ]);
  render(<RolesPanel />);
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("common.edit") }),
  );
  fireEvent.change(screen.getByLabelText(i18n.t("roles.fiveHourBudgetUsd")), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(mocks.updateRole).toHaveBeenCalledWith("member", {
      permissions: ["chat:write"],
      grantable_permissions: [],
      assignable_role_ids: [],
      limits: { five_hour_budget_usd: 0, weekly_budget_usd: 15 },
    }),
  );
});
