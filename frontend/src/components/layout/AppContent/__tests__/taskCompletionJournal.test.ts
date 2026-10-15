import { expect, test, vi } from "vitest";
import { drainTaskCompletions } from "../taskCompletionJournal";

const event = (id: string) => ({
  id,
  created_at: "2026-10-13T00:00:00Z",
  session_id: "child",
  run_id: id,
  status: "completed",
  dedupe_key: `task:${id}:completed`,
  notification_kind: "background_task_complete",
});

test("offline completions are delivered in page order and final page cursor is retained", async () => {
  const load = vi
    .fn()
    .mockResolvedValueOnce({
      items: [event("one")],
      cursor: "one",
      next_cursor: "one",
    })
    .mockResolvedValueOnce({
      items: [event("two")],
      cursor: "two",
      next_cursor: null,
    });
  const delivered: string[] = [];
  const cursors: string[] = [];
  await drainTaskCompletions({
    cursor: null,
    loadPage: load,
    deliver: async (item) => {
      delivered.push(item.id);
    },
    saveCursor: (value) => cursors.push(value),
    isCurrent: () => true,
  });
  expect(delivered).toEqual(["one", "two"]);
  expect(cursors).toEqual(["one", "two"]);
  expect(load.mock.calls).toEqual([[null], ["one"]]);
});

test("failed delivery does not advance a cursor past the undelivered page", async () => {
  const save = vi.fn();
  await expect(
    drainTaskCompletions({
      cursor: "previous",
      loadPage: async () => ({
        items: [event("one")],
        cursor: "one",
        next_cursor: null,
      }),
      deliver: async () => {
        throw new Error("delivery failed");
      },
      saveCursor: save,
      isCurrent: () => true,
    }),
  ).rejects.toThrow("delivery failed");
  expect(save).not.toHaveBeenCalled();
});

test("late page from a signed-out user cannot deliver or save another account cursor", async () => {
  let current = true;
  const deliver = vi.fn();
  const save = vi.fn();
  await drainTaskCompletions({
    cursor: null,
    loadPage: async () => {
      current = false;
      return { items: [event("one")], cursor: "one", next_cursor: null };
    },
    deliver,
    saveCursor: save,
    isCurrent: () => current,
  });
  expect(deliver).not.toHaveBeenCalled();
  expect(save).not.toHaveBeenCalled();
});

test("an unchanged continuation cursor cannot create an infinite GET loop", async () => {
  const load = vi
    .fn()
    .mockResolvedValue({ items: [], cursor: "same", next_cursor: "same" });
  await drainTaskCompletions({
    cursor: "same",
    loadPage: load,
    deliver: async () => {},
    saveCursor: () => {},
    isCurrent: () => true,
  });
  expect(load).toHaveBeenCalledOnce();
});

test("historical pages advance the bookmark without replaying old toasts", async () => {
  const deliver = vi.fn();
  const save = vi.fn();
  await drainTaskCompletions({
    cursor: null,
    notBefore: Date.parse("2026-10-14T00:00:00Z"),
    loadPage: async () => ({
      items: [
        event("old"),
        { ...event("new"), created_at: "2026-10-15T00:00:00Z" },
      ],
      cursor: "new",
      next_cursor: null,
    }),
    deliver,
    saveCursor: save,
    isCurrent: () => true,
  });
  expect(deliver.mock.calls.map(([item]) => item.id)).toEqual(["new"]);
  expect(save).toHaveBeenCalledWith("new");
});
