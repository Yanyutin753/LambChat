/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useMarketplace } from "../../../../hooks/useMarketplace";
import { marketplaceApi } from "../../../../services/api/marketplace";
import { SkillPreviewModal } from "../SkillPreviewModal";
import i18n from "../../../../i18n";
import type { MarketplaceSkillResponse } from "../../../../types";

vi.mock("../../../../services/api/marketplace", () => ({
  marketplaceApi: {
    list: vi.fn(),
    getTags: vi.fn(),
    listFiles: vi.fn(),
    getFile: vi.fn(),
  },
}));
const skill = (name: string): MarketplaceSkillResponse => ({
  skill_name: name,
  description: "Preview",
  tags: [],
  version: "1",
  is_active: true,
  is_owner: false,
  file_count: 2,
});
function Harness() {
  const state = useMarketplace();
  return (
    <>
      <button onClick={() => state.openPreview(skill("Alpha"))}>
        Open Alpha
      </button>
      <button onClick={() => state.openPreview(skill("Beta"))}>
        Open Beta
      </button>
      <button onClick={state.closePreview}>Close detail</button>
      {state.previewSkill && (
        <SkillPreviewModal
          key={state.previewSkill.skill_name}
          {...state}
          previewSkill={state.previewSkill}
          onClose={state.closePreview}
          onReadFile={state.readPreviewFile}
          onRetryFiles={() => state.openPreview(state.previewSkill!)}
        />
      )}
    </>
  );
}
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.mocked(marketplaceApi.list).mockResolvedValue([]);
  vi.mocked(marketplaceApi.getTags).mockResolvedValue({ tags: [] });
  vi.mocked(marketplaceApi.listFiles).mockResolvedValue({
    files: ["a.md", "b.md"],
  });
  vi.mocked(marketplaceApi.getFile).mockResolvedValue({ content: "" });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
async function open() {
  render(<Harness />);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Open Alpha" })),
  );
}
test("skill detail displays its version and description", async () => {
  await open();
  expect(screen.getByText("v1")).toBeInTheDocument();
  expect(screen.getByText("Preview", { exact: true })).toBeInTheDocument();
});
test("failed file list shows an error and retry recovers the detail", async () => {
  vi.mocked(marketplaceApi.listFiles).mockRejectedValueOnce(
    new Error("Unavailable"),
  );
  await open();
  expect(screen.getByRole("alert")).toBeInTheDocument();
  const retry = screen.getByRole("button", { name: i18n.t("common.retry") });
  retry.focus();
  await act(async () => fireEvent.click(retry));
  expect(screen.getByRole("button", { name: "a.md" })).toBeInTheDocument();
  expect(document.activeElement).not.toBe(document.body);
});
test("failed file retries, and an empty successful file stays cached", async () => {
  vi.mocked(marketplaceApi.getFile).mockRejectedValueOnce(
    new Error("Unavailable"),
  );
  await open();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "a.md" })),
  );
  expect(
    screen.getByRole("dialog", { name: "a.md", exact: true }),
  ).toBeInTheDocument();
  expect(screen.getByRole("alert")).toBeInTheDocument();
  const retry = screen.getByRole("button", { name: i18n.t("common.retry") });
  retry.focus();
  await act(async () => fireEvent.click(retry));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(document.activeElement).not.toBe(document.body);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("marketplace.closePreview") }),
  );
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "a.md" })),
  );
  expect(marketplaceApi.getFile).toHaveBeenCalledTimes(2);
});
test("a late list from another skill cannot replace the current files", async () => {
  const old = pending<{ files: string[] }>();
  vi.mocked(marketplaceApi.listFiles)
    .mockReturnValueOnce(old.promise)
    .mockResolvedValueOnce({ files: ["beta.md"] });
  await open();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Open Beta" })),
  );
  await act(async () => old.resolve({ files: ["alpha.md"] }));
  expect(screen.getByRole("button", { name: "beta.md" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "alpha.md" })).toBeNull();
});
test("finishing one file leaves another pending preview loading", async () => {
  const first = pending<{ content: string }>();
  const second = pending<{ content: string }>();
  vi.mocked(marketplaceApi.getFile)
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  await open();
  fireEvent.click(screen.getByRole("button", { name: "a.md" }));
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("marketplace.closePreview") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "b.md" }));
  await act(async () => first.resolve({ content: "First" }));
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull();
  await act(async () => second.resolve({ content: "Second" }));
  expect(screen.queryByRole("status")).toBeNull();
});
test("late file content from a closed skill cannot populate a new preview", async () => {
  const old = pending<{ content: string }>();
  vi.mocked(marketplaceApi.getFile)
    .mockReturnValueOnce(old.promise)
    .mockResolvedValueOnce({ content: "Beta content" });
  await open();
  fireEvent.click(screen.getByRole("button", { name: "a.md" }));
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("marketplace.closePreview") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Close detail" }));
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Open Beta" })),
  );
  await act(async () => old.resolve({ content: "Alpha content" }));
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "a.md" })),
  );
  expect(marketplaceApi.getFile).toHaveBeenLastCalledWith("Beta", "a.md");
  expect(screen.getByRole("textbox")).toHaveTextContent("Beta content");
});
