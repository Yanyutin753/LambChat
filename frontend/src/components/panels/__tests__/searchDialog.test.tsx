/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SearchDialog } from "../SearchDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../i18n", () => ({ default: { language: "en" } }));
vi.mock("react-intersection-observer", () => ({
  useInView: () => ({ ref: vi.fn(), inView: false }),
}));
const { list } = vi.hoisted(() => ({ list: vi.fn() }));
list.mockResolvedValue({ sessions: [], has_more: false });
vi.mock("../../../services/api", () => ({
  sessionApi: { list },
}));
afterEach(cleanup);

test("search can be named, cleared with focus retained, and dismissed on touch", () => {
  const onClose = vi.fn();
  render(<SearchDialog isOpen onClose={onClose} onSelectSession={() => {}} />);
  expect(
    screen.getByRole("dialog", { name: "sidebar.searchSessions" }),
  ).toBeTruthy();
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "report" } });
  const clear = screen.getByRole("button", { name: "common.clear" });
  clear.focus();
  fireEvent.click(clear);
  expect((input as HTMLInputElement).value).toBe("");
  expect(document.activeElement).toBe(input);
  fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
  expect(onClose).toHaveBeenCalledOnce();
});

test("Enter on Cancel keeps native activation after a search result is highlighted", async () => {
  list.mockResolvedValueOnce({
    sessions: [{ id: "session-1", name: "Report", metadata: {} }],
    has_more: false,
  });
  const onSelectSession = vi.fn();
  const onClose = vi.fn();
  render(
    <SearchDialog isOpen onClose={onClose} onSelectSession={onSelectSession} />,
  );
  const result = await screen.findByRole("button", { name: "Report" });
  result.scrollIntoView = vi.fn();
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "ArrowDown" });
  const cancel = screen.getByRole("button", { name: "common.cancel" });
  cancel.focus();
  expect(fireEvent.keyDown(cancel, { key: "Enter" })).toBe(true);
  expect(onSelectSession).not.toHaveBeenCalled();
  fireEvent.click(cancel);
  expect(onClose).toHaveBeenCalledOnce();
});
