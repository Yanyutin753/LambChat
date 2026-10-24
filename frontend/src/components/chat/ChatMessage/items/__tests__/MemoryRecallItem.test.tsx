/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { memoryApi } from "../../../../../services/api/memory";
import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";
import { MemoryRecallItem } from "../MemoryRecallItem";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

vi.mock("../../../../../services/api/memory", () => ({
  memoryApi: { get: vi.fn() },
}));

const full = {
  memory_id: "contract-review",
  title: "API 契约审查",
  summary: "检查接口分页",
  content: "完整内容：检查接口分页、错误码、权限与兼容性。",
  memory_type: "reference",
  source: "manual",
  tags: ["API"],
  created_at: "2026-10-01T08:00:00Z",
  updated_at: "2026-10-02T08:00:00Z",
  access_count: 7,
  has_full_content: false,
};

beforeEach(() => {
  resetRightPanelCoordinator();
  vi.mocked(memoryApi.get).mockReset();
});

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
});

function openRecallPanel() {
  const row = render(
    <MemoryRecallItem
      args={{ query: "API" }}
      success
      result={{
        memories: [
          {
            memory_id: full.memory_id,
            title: full.title,
            summary: full.summary,
            text: "截断的召回内容",
            type: full.memory_type,
            source: full.source,
            created_at: full.created_at,
            score: 1,
          },
        ],
      }}
    />,
  );
  fireEvent.click(within(row.container).getByRole("button"));
  const panel = render(<>{getPersistentToolPanelState()!.children}</>);
  return within(panel.container).getByRole("button", { name: full.title });
}

test("clicking a recalled card loads its full memory and opens read-only details", async () => {
  vi.mocked(memoryApi.get).mockResolvedValue(full);
  const card = openRecallPanel();
  expect(memoryApi.get).not.toHaveBeenCalled();
  fireEvent.click(card);
  expect(await screen.findByText(full.content)).toBeVisible();
  expect(memoryApi.get).toHaveBeenCalledWith(full.memory_id);
  expect(screen.getByText(`7 ${i18n.t("memory.accesses")}`)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: i18n.t("common.edit") }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: i18n.t("common.delete") }),
  ).toBeNull();
  fireEvent.click(
    screen.getAllByRole("button", { name: i18n.t("common.close") })[0],
  );
  expect(screen.queryByText(full.content)).toBeNull();
});

test("a failed card read reports an error and retries the full memory", async () => {
  vi.mocked(memoryApi.get)
    .mockRejectedValueOnce(new Error("unavailable"))
    .mockResolvedValueOnce(full);
  fireEvent.click(openRecallPanel());
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(screen.queryByText("截断的召回内容")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  expect(await screen.findByText(full.content)).toBeVisible();
  expect(memoryApi.get).toHaveBeenCalledTimes(2);
});
