/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ToolbarChip } from "../ToolbarChip";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("clearing an identity is a separate named button and does not open its selector", async () => {
  const open = vi.fn(),
    clear = vi.fn();
  const user = userEvent.setup();
  render(
    <ToolbarChip
      label="Research team"
      icon={<span>Avatar</span>}
      onClick={open}
      onClear={clear}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "common.clear Research team" }),
  );
  expect(clear).toHaveBeenCalledOnce();
  expect(open).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Research team", exact: true }),
  );
  expect(open).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("button", { name: "Research team", exact: true }),
  ).toHaveAttribute("aria-label", "Research team");
  expect(document.querySelector("button button")).toBeNull();
});
