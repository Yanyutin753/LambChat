/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryPanel } from "../index";
const { list, t } = vi.hoisted(() => ({
  list: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../../services/api/memory", () => ({ memoryApi: { list } }));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
test("a failed memory load shows a persistent error and can retry into a real empty state", async () => {
  list
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ memories: [], total: 0 });
  render(<MemoryPanel />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "memory.fetchError",
  );
  expect(screen.queryByText("memory.empty")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() =>
    expect(screen.getByText("memory.empty")).toBeInTheDocument(),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(list).toHaveBeenCalledTimes(2);
});

test("a failed refresh keeps the previous memories available through named buttons", async () => {
  list
    .mockResolvedValueOnce({
      memories: [
        {
          memory_id: "one",
          memory_type: "user",
          source: "manual",
          title: "Research notes",
          summary: "Constraints",
          tags: [],
          updated_at: "2026-10-01T00:00:00Z",
        },
      ],
      total: 1,
    })
    .mockRejectedValueOnce(new Error("offline"));
  render(<MemoryPanel />);
  expect(
    await screen.findByRole("button", { name: "Research notes" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "memory.fetchError",
  );
  expect(
    screen.getByRole("button", { name: "Research notes" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("memory.empty")).toBeNull();
});
