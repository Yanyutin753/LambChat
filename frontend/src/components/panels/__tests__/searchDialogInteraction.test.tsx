/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import appI18n from "../../../i18n";
import { SearchDialog } from "../SearchDialog";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  inView: false,
  resultsRoot: undefined as Element | null | undefined,
}));
vi.mock("../../../services/api", () => ({ sessionApi: { list: api.list } }));
vi.mock("react-intersection-observer", () => ({
  useInView: (options: { root?: Element | null }) => {
    api.resultsRoot = options.root;
    return { ref: vi.fn(), inView: api.inView };
  },
}));
const sessions = ["Alpha", "Beta"].map((name) => ({
  id: name.toLowerCase(),
  name,
  user_id: "user",
  agent_id: "fast",
  is_active: true,
  metadata: {},
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
}));
const scrollDescriptor = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "scrollIntoView",
);
beforeEach(() => {
  api.inView = false;
  api.resultsRoot = undefined;
  api.list.mockReset().mockResolvedValue({ sessions, has_more: false });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
});
afterEach(() => {
  cleanup();
  if (scrollDescriptor)
    Object.defineProperty(
      HTMLElement.prototype,
      "scrollIntoView",
      scrollDescriptor,
    );
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});
const i18n = appI18n.cloneInstance({ lng: "en" });
function dialog(select: (id: string) => void, close = vi.fn()) {
  return (
    <I18nextProvider i18n={i18n}>
      <SearchDialog isOpen onClose={close} onSelectSession={select} />
    </I18nextProvider>
  );
}

test("appending a result page preserves the current keyboard choice", async () => {
  api.list.mockResolvedValueOnce({ sessions, has_more: true });
  let finish!: (result: unknown) => void;
  api.list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const select = vi.fn();
  const { rerender } = render(dialog(select));
  await screen.findByRole("option", { name: "Beta", exact: true });
  const input = screen.getByLabelText("Search sessions", { selector: "input" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  api.inView = true;
  rerender(dialog(select));
  await act(async () =>
    finish({
      sessions: [{ ...sessions[0], id: "gamma", name: "Gamma" }],
      has_more: false,
    }),
  );
  await screen.findByRole("option", { name: "Gamma", exact: true });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).toHaveBeenCalledWith("beta");
});

test("pagination observes visibility inside its scrolling results", async () => {
  render(dialog(vi.fn()));
  await screen.findByRole("option", { name: "Beta" });
  expect(api.resultsRoot).toBe(
    screen.getByRole("listbox", { name: "Search sessions" }),
  );
});

test("keyboard choices are announced while focus stays in the search field", async () => {
  const select = vi.fn();
  render(dialog(select));
  const beta = await screen.findByRole("option", { name: "Beta", exact: true });
  const input = screen.getByRole("combobox", { name: "Search sessions" });
  const results = screen.getByRole("listbox", { name: "Search sessions" });
  act(() => input.focus());
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(input).toHaveAttribute("aria-controls", results.id);
  expect(input).toHaveAttribute("aria-activedescendant", beta.id);
  expect(beta).toHaveAttribute("aria-selected", "true");
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, { key: "ArrowUp" });
  fireEvent.keyDown(input, { key: "ArrowUp" });
  expect(input).not.toHaveAttribute("aria-activedescendant");
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).not.toHaveBeenCalled();
});

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "IME candidate keys keep the current session choice and dialog open (%j)",
  async (composition) => {
    const select = vi.fn();
    const close = vi.fn();
    render(dialog(select, close));
    const alpha = await screen.findByRole("option", { name: "Alpha" });
    const input = screen.getByRole("combobox", { name: "Search sessions" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown", ...composition });
    fireEvent.keyDown(input, { key: "Enter", ...composition });
    fireEvent.keyDown(input, { key: "Escape", ...composition });
    expect(input).toHaveAttribute("aria-activedescendant", alpha.id);
    expect(select).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(select).toHaveBeenCalledWith("alpha");
  },
);

test("a failed next page preserves results and retry appends without losing the choice", async () => {
  api.list.mockResolvedValueOnce({ sessions, has_more: true });
  api.list.mockRejectedValueOnce(new Error("Page failed"));
  api.list.mockResolvedValueOnce({
    sessions: [{ ...sessions[0], id: "gamma", name: "Gamma" }],
    has_more: false,
  });
  const select = vi.fn();
  const { rerender } = render(dialog(select));
  const beta = await screen.findByRole("option", { name: "Beta" });
  const input = screen.getByRole("combobox", { name: "Search sessions" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  api.inView = true;
  rerender(dialog(select));
  await screen.findByRole("alert");
  expect(beta).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByRole("option", { name: "Gamma" });
  expect(input).toHaveFocus();
  expect(input).toHaveAttribute("aria-activedescendant", beta.id);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(api.list).toHaveBeenLastCalledWith({
    limit: 30,
    skip: 2,
    status: "active",
  });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).toHaveBeenCalledWith("beta");
});

test("clearing a query updates the focused field and reloads initial results", async () => {
  render(dialog(vi.fn()));
  await screen.findByRole("option", { name: "Alpha" });
  const input = screen.getByRole("combobox", { name: "Search sessions" });
  act(() => input.focus());
  fireEvent.change(input, { target: { value: "Alpha" } });
  await waitFor(() =>
    expect(api.list).toHaveBeenLastCalledWith({
      limit: 30,
      skip: 0,
      status: "active",
      search: "Alpha",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect(input).toHaveValue("");
  expect(input).toHaveFocus();
  await waitFor(() =>
    expect(api.list).toHaveBeenLastCalledWith({
      limit: 30,
      skip: 0,
      status: "active",
    }),
  );
});

test("a new query clears the old selection before delayed results arrive", async () => {
  const select = vi.fn();
  render(dialog(select));
  await screen.findByRole("option", { name: "Beta", exact: true });
  const input = screen.getByRole("combobox", { name: "Search sessions" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(input).toHaveAttribute("aria-activedescendant");
  fireEvent.change(input, { target: { value: "Gamma" } });
  expect(input).not.toHaveAttribute("aria-activedescendant");
  expect(screen.queryByRole("option", { name: "Alpha" })).toBeNull();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).not.toHaveBeenCalled();
});
