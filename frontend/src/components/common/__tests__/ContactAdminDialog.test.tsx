/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { ContactAdminDialog } from "../ContactAdminDialog";
const fetchMock = vi.fn<typeof fetch>();
function response(email = "", url = "") {
  return new Response(
    JSON.stringify({
      providers: [],
      registration_enabled: true,
      admin_contact: { email, url },
    }),
    { status: 200 },
  );
}
beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage("zh");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("anonymous contact read announces loading and resolves public contact links", async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValue(
    new Promise<Response>((done) => {
      resolve = done;
    }),
  );
  render(
    <ContactAdminDialog isOpen onClose={vi.fn()} reason="emailActivation" />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(/加载/);
  expect(screen.queryByText(/暂无管理员联系方式/)).toBeNull();
  const email = `${"research-support".repeat(8)}@example.test`;
  await act(async () =>
    resolve(response(email, "https://example.test/support")),
  );
  expect(screen.getByRole("link", { name: email })).toHaveAttribute(
    "href",
    `mailto:${email}`,
  );
  expect(screen.getByRole("link", { name: "联系管理员" })).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/auth\/oauth\/providers$/);
  expect(
    new Headers(fetchMock.mock.calls[0][1]?.headers).has("Authorization"),
  ).toBe(false);
});

test("contact read failure remains visible and retry preserves stable focus", async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ detail: { message: "Contact read unavailable" } }),
      { status: 503 },
    ),
  );
  render(<ContactAdminDialog isOpen onClose={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Contact read unavailable",
  );
  expect(screen.queryByText(/暂无管理员联系方式/)).toBeNull();
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(
    new Promise<Response>((done) => {
      resolve = done;
    }),
  );
  const retry = screen.getByRole("button", { name: "重试" });
  retry.focus();
  fireEvent.click(retry);
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(screen.getByRole("status")).toBeTruthy();
  await act(async () => resolve(response("support@example.test")));
  expect(
    await screen.findByRole("link", { name: "support@example.test" }),
  ).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("loaded empty contact uses the labelled shared dialog and closes with Escape", async () => {
  fetchMock.mockResolvedValue(response());
  const onClose = vi.fn();
  render(
    <ContactAdminDialog isOpen onClose={onClose} reason="emailActivation" />,
  );
  await waitFor(() =>
    expect(screen.getByText(/暂无管理员联系方式/)).toBeTruthy(),
  );
  expect(screen.getByRole("dialog", { name: "邮箱验证问题" })).toBeTruthy();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("closed contact waits until opening and isolates a cancelled read from the next opening", async () => {
  let oldResolve!: (value: Response) => void;
  let newResolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(
    new Promise<Response>((done) => {
      oldResolve = done;
    }),
  );
  fetchMock.mockReturnValueOnce(
    new Promise<Response>((done) => {
      newResolve = done;
    }),
  );
  const onClose = vi.fn();
  const view = render(<ContactAdminDialog isOpen={false} onClose={onClose} />);
  expect(fetchMock).not.toHaveBeenCalled();
  view.rerender(<ContactAdminDialog isOpen onClose={onClose} />);
  const signal = fetchMock.mock.calls[0][1]?.signal;
  view.rerender(<ContactAdminDialog isOpen={false} onClose={onClose} />);
  expect(signal?.aborted).toBe(true);
  view.rerender(<ContactAdminDialog isOpen onClose={onClose} />);
  await act(async () => oldResolve(response("old@example.test")));
  expect(screen.queryByText("old@example.test")).toBeNull();
  expect(screen.getByRole("status")).toBeTruthy();
  await act(async () => newResolve(response("new@example.test")));
  expect(screen.getByRole("link", { name: "new@example.test" })).toBeTruthy();
});

test("a late failure after closing cannot replace the next opening's loaded contact", async () => {
  let oldResolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(
    new Promise<Response>((done) => {
      oldResolve = done;
    }),
  );
  fetchMock.mockResolvedValueOnce(response("current@example.test"));
  const props = { onClose: vi.fn() };
  const view = render(<ContactAdminDialog {...props} isOpen />);
  view.rerender(<ContactAdminDialog {...props} isOpen={false} />);
  view.rerender(<ContactAdminDialog {...props} isOpen />);
  await screen.findByRole("link", { name: "current@example.test" });
  await act(async () => oldResolve(new Response("{}", { status: 503 })));
  expect(
    screen.getByRole("link", { name: "current@example.test" }),
  ).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("an empty successful response is a read error instead of missing contact information", async () => {
  fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
  render(<ContactAdminDialog isOpen onClose={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("settings.loadFailed"),
  );
  expect(screen.queryByText(/暂无管理员联系方式/)).toBeNull();
});
