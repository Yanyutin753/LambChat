/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Pagination } from "../Pagination";
import i18n from "../../../i18n";
afterEach(cleanup);

test("pagination in a modal returns the content to the top", () => {
  const change = vi.fn();
  const { container } = render(
    <div className="modal-surface">
      <div className="overflow-y-auto" />
      <Pagination page={1} pageSize={20} total={65} onChange={change} />
    </div>,
  );
  const content = container.querySelector<HTMLDivElement>(".overflow-y-auto")!;
  content.scrollTop = 240;
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.next") }));
  expect(change).toHaveBeenCalledWith(2);
  expect(content.scrollTop).toBe(0);
});
