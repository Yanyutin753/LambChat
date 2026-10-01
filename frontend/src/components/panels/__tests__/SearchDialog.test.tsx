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
import { sessionApi, type SessionListResponse } from "../../../services/api";
import { SearchDialog } from "../SearchDialog";
import i18n from "../../../i18n";

vi.mock("../../../services/api", () => ({ sessionApi: { list: vi.fn() } }));
const observer = vi.hoisted(() => ({ inView: false }));
vi.mock("react-intersection-observer", () => ({
  useInView: () => ({ ref: () => {}, inView: observer.inView }),
}));

function response(name?: string): SessionListResponse {
  return {
    sessions: name
      ? [
          {
            id: "session-1",
            agent_id: "default",
            created_at: "2026-10-01",
            updated_at: "2026-10-01",
            is_active: true,
            name,
            metadata: {},
          },
        ]
      : [],
    total: name ? 1 : 0,
    skip: 0,
    limit: 30,
    has_more: false,
  };
}
beforeEach(async () => {
  observer.inView = false;
  vi.mocked(sessionApi.list).mockReset();
  await i18n.changeLanguage("zh");
});

test("retrying a failed next page preserves results and continues the same offset", async () => {
  const first = response("First result");
  first.has_more = true;
  const next = response("Next result");
  next.sessions[0].id = "session-2";
  vi.mocked(sessionApi.list)
    .mockResolvedValueOnce(first)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(next);
  const select = vi.fn();
  const { rerender } = render(
    <SearchDialog isOpen onClose={() => {}} onSelectSession={select} />,
  );
  await screen.findByRole("button", { name: "First result" });
  observer.inView = true;
  rerender(<SearchDialog isOpen onClose={() => {}} onSelectSession={select} />);
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "First result" })).toBeVisible();
  fireEvent.mouseEnter(screen.getByRole("button", { name: "First result" }));
  const retry = screen.getByRole("button", { name: "重试" });
  retry.focus();
  expect(fireEvent.keyDown(retry, { key: "Enter" })).toBe(true);
  expect(select).not.toHaveBeenCalled();
  fireEvent.click(retry);
  await screen.findByRole("button", { name: "Next result" });
  expect(screen.getByRole("button", { name: "First result" })).toBeVisible();
  expect(vi.mocked(sessionApi.list).mock.lastCall?.[0]).toMatchObject({
    skip: 1,
  });
});
afterEach(cleanup);

test("empty recent sessions have a visible explanation and a named dialog", async () => {
  vi.mocked(sessionApi.list).mockResolvedValue(response());
  render(<SearchDialog isOpen onClose={() => {}} onSelectSession={() => {}} />);
  expect(await screen.findByText("暂无对话记录")).toBeVisible();
  expect(screen.getByRole("dialog", { name: "搜索会话" })).toBeInTheDocument();
});

test("failed searches show retry and recover to selectable results", async () => {
  vi.mocked(sessionApi.list)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(response("Recovered session"));
  const select = vi.fn();
  render(<SearchDialog isOpen onClose={() => {}} onSelectSession={select} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("加载会话失败");
  const retry = screen.getByRole("button", { name: "重试" });
  retry.focus();
  fireEvent.click(retry);
  expect(screen.getByRole("textbox", { name: "搜索会话" })).toHaveFocus();
  fireEvent.click(
    await screen.findByRole("button", { name: "Recovered session" }),
  );
  expect(select).toHaveBeenCalledWith("session-1");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("older search responses cannot replace the latest query results", async () => {
  let finishOld!: (value: SessionListResponse) => void;
  vi.mocked(sessionApi.list).mockImplementation(async (params) => {
    if (params?.search === "old")
      return new Promise<SessionListResponse>((resolve) => {
        finishOld = resolve;
      });
    return response(params?.search === "new" ? "New result" : undefined);
  });
  render(<SearchDialog isOpen onClose={() => {}} onSelectSession={() => {}} />);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "old" } });
  await waitFor(() => expect(finishOld).toBeDefined());
  fireEvent.change(input, { target: { value: "new" } });
  await screen.findByRole("button", { name: "New result" });
  await act(async () => finishOld(response("Old result")));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Old result" }),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: "New result" })).toBeVisible();
});
