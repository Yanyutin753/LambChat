/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { UsersPanel } from "../UsersPanel";
const { roles } = vi.hoisted(() => ({ roles: vi.fn() }));
vi.mock("../../../services/api", () => ({
  userApi: { list: vi.fn().mockResolvedValue({ users: [], total: 0 }) },
  roleApi: { list: roles },
  getFullUrl: (value: string) => value,
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
beforeEach(() =>
  roles.mockReset().mockResolvedValue({
    roles: [{ id: "research", name: "Research", is_system: false }],
  }),
);
test("user fields have labels and the role label toggles its native checkbox", async () => {
  render(<UsersPanel />);
  fireEvent.click(
    (
      await screen.findAllByRole("button", { name: i18n.t("users.createUser") })
    )[0],
  );
  for (const key of ["username", "email", "password"])
    expect(screen.getByLabelText(i18n.t(`users.${key}`))).toBeTruthy();
  const checkbox = screen.getByRole("checkbox", { name: "Research" });
  fireEvent.click(screen.getByText("Research"));
  expect(checkbox).toBeChecked();
});
test("failed roles can be retried without losing the user draft", async () => {
  roles.mockRejectedValueOnce(new Error("Offline"));
  render(<UsersPanel />);
  fireEvent.click(
    (
      await screen.findAllByRole("button", { name: i18n.t("users.createUser") })
    )[0],
  );
  const username = screen.getByPlaceholderText(
    i18n.t("users.usernamePlaceholder"),
  );
  fireEvent.change(username, { target: { value: "Draft name" } });
  const alert = await screen.findByRole("alert");
  expect(screen.queryByText(i18n.t("users.noRolesAvailable"))).toBeNull();
  fireEvent.click(
    within(alert).getByRole("button", { name: i18n.t("common.refresh") }),
  );
  await screen.findByRole("checkbox", { name: "Research" });
  expect(username).toHaveValue("Draft name");
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});
