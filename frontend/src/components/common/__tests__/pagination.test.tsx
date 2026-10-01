/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Pagination } from "../Pagination";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, args?: { page?: number }) =>
      args?.page ? `Page ${args.page}` : key,
  }),
}));
vi.stubGlobal("matchMedia", () => ({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
}));
afterEach(cleanup);

test("announces the current page and keeps navigation inside its bounds", () => {
  const onChange = vi.fn();
  render(<Pagination page={1} pageSize={20} total={65} onChange={onChange} />);
  expect(screen.getByRole("navigation")).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Page 1" }).getAttribute("aria-current"),
  ).toBe("page");
  fireEvent.click(screen.getByRole("button", { name: "common.previous" }));
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(onChange).toHaveBeenCalledWith(2);
});

test("returns to a valid page when the last item on the last page is removed", () => {
  const onChange = vi.fn();
  render(<Pagination page={2} pageSize={20} total={20} onChange={onChange} />);
  expect(onChange).toHaveBeenCalledWith(1);
  expect(screen.getByRole("navigation")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});
