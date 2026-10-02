/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TeamPickerModal } from "../TeamPickerModal";
import { teamApi } from "../../../services/api/team";
import type { TeamListResponse } from "../../../types/team";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../services/api/team", () => ({ teamApi: { list: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
const response = (total = 65): TeamListResponse => ({
  teams: [],
  total,
  skip: 0,
  limit: 20,
});
const props = {
  isOpen: true,
  selectedTeamId: null,
  onSelect: vi.fn(),
  onClose: vi.fn(),
  onCreateNew: vi.fn(),
};

test("team picker paginates beyond the first 50 and searches on page one", async () => {
  vi.mocked(teamApi.list).mockResolvedValue(response());
  render(<TeamPickerModal {...props} />);
  await waitFor(() =>
    expect(teamApi.list).toHaveBeenCalledWith({
      skip: 0,
      limit: 20,
      q: undefined,
    }),
  );
  await waitFor(() =>
    expect(document.body.querySelectorAll(".pagination-page").length).toBe(4),
  );
  fireEvent.click(document.body.querySelectorAll(".pagination-page")[3]);
  await waitFor(() =>
    expect(teamApi.list).toHaveBeenLastCalledWith({
      skip: 60,
      limit: 20,
      q: undefined,
    }),
  );
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Research" },
  });
  await waitFor(() =>
    expect(teamApi.list).toHaveBeenLastCalledWith({
      skip: 0,
      limit: 20,
      q: "Research",
    }),
  );
});

test("team request failure offers retry instead of reporting an empty library", async () => {
  vi.mocked(teamApi.list)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(response(0));
  render(<TeamPickerModal {...props} />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText("team.noTeams")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(await screen.findByText("team.noTeams")).toBeTruthy();
  expect(screen.getByRole("button", { name: "common.close" })).toBeTruthy();
});

test("an older team search cannot replace a newer result", async () => {
  let resolveOld!: (value: TeamListResponse) => void;
  vi.mocked(teamApi.list)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
    )
    .mockResolvedValue(response(0));
  render(<TeamPickerModal {...props} />);
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Latest" },
  });
  expect(await screen.findByText("team.noMatchingTeams")).toBeTruthy();
  await act(async () => resolveOld(response(65)));
  expect(document.body.querySelector(".pagination-wrapper")).toBeNull();
});
