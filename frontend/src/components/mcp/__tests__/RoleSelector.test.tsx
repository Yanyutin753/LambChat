/** @vitest-environment jsdom */
import { useState } from "react";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { RoleSelector } from "../RoleSelector";
const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../../services/api/role", () => ({ roleApi: { list } }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
beforeEach(() =>
  list.mockReset().mockResolvedValue({
    roles: [{ name: "Research", description: "Workspace", is_system: false }],
  }),
);
function ControlledRoles() {
  const [roles, setRoles] = useState<string[]>([]);
  return <RoleSelector selectedRoles={roles} onChange={setRoles} />;
}
test("keyboard opens roles, changes selection and Escape returns focus to its trigger", async () => {
  const user = userEvent.setup();
  render(<ControlledRoles />);
  const trigger = screen.getByRole("button", {
    name: i18n.t("mcp.form.allowedRoles"),
  });
  await user.tab();
  await user.keyboard("{Enter}");
  const choice = await screen.findByRole("checkbox", { name: "Research" });
  await user.click(choice);
  expect(choice).toBeChecked();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("checkbox")).toBeNull();
});
test("a failed role request stays visible and can be retried", async () => {
  list.mockRejectedValueOnce(new Error("Offline"));
  const user = userEvent.setup();
  render(<ControlledRoles />);
  await user.click(
    screen.getByRole("button", { name: i18n.t("mcp.form.allowedRoles") }),
  );
  const alert = await screen.findByRole("alert");
  expect(screen.queryByText(i18n.t("mcp.form.noRoles"))).toBeNull();
  await user.click(
    within(alert).getByRole("button", { name: i18n.t("common.refresh") }),
  );
  await screen.findByRole("checkbox", { name: "Research" });
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(list).toHaveBeenCalledTimes(2);
});

test.each([0, 300])(
  "keyboard viewport offset %s preserves the layout anchor",
  async (offsetTop) => {
    vi.stubGlobal("innerHeight", 844);
    vi.stubGlobal("visualViewport", {
      height: 400,
      width: 320,
      offsetTop,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    const user = userEvent.setup();
    render(<ControlledRoles />);
    const trigger = screen.getByRole("button", {
      name: i18n.t("mcp.form.allowedRoles"),
    });
    trigger.getBoundingClientRect = () =>
      new DOMRect(12, 350 + offsetTop, 296, 44);
    await user.click(trigger);
    const popup = screen.getByRole("group", {
      name: i18n.t("mcp.form.allowedRoles"),
    });
    expect(popup.style.bottom).toBe(`${844 - (350 + offsetTop) + 4}px`);
    expect(popup.style.maxHeight).toBe("320px");
  },
);

test("Tab stays within choices and dismisses the popup when leaving either boundary", async () => {
  const user = userEvent.setup();
  render(
    <>
      <button>Previous field</button>
      <ControlledRoles />
      <button>Next field</button>
    </>,
  );
  const trigger = screen.getByRole("button", {
    name: i18n.t("mcp.form.allowedRoles"),
  });
  await user.click(trigger);
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Previous field" })).toHaveFocus();
  await user.click(trigger);
  await user.tab();
  expect(screen.getByRole("checkbox", { name: "Research" })).toHaveFocus();
  await user.keyboard(" ");
  await user.tab();
  expect(
    screen.getByRole("button", { name: i18n.t("mcp.form.clearAll") }),
  ).toHaveFocus();
  await user.tab();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Next field" })).toHaveFocus();
});
