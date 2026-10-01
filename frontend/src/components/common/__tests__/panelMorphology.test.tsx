/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PanelHeader } from "../PanelHeader";
import { Pagination } from "../Pagination";
import { StatusBadge } from "../StatusBadge";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("page identity includes its count beside the heading", () => {
  render(
    <PanelHeader title="Users" count={65} actions={<button>Create</button>} />,
  );
  expect(screen.getByRole("heading", { name: "Users" })).toBeTruthy();
  expect(screen.getByText("65").className).toContain("panel-header__count");
});

test("single-page lists keep their summary but hide navigation controls", () => {
  render(<Pagination page={1} pageSize={20} total={4} onChange={vi.fn()} />);
  expect(screen.getByText("common.paginationSummary")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

test("status keeps a text label alongside a decorative semantic dot", () => {
  const { container } = render(<StatusBadge color="green" label="Enabled" />);
  expect(screen.getByText("Enabled").className).toContain("status-dot");
  expect(container.querySelector('[aria-hidden="true"]')?.className).toContain(
    "bg-theme-success",
  );
});
