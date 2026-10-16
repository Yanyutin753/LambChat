/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, test, expect, vi } from "vitest";
import i18n from "../../../i18n";
import { ScheduledTaskApprovalContent } from "../ScheduledTaskApprovalContent";

const api = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../../services/api/agent", () => ({ agentApi: api }));
const preview = {
  name: "Daily research",
  agent_id: "search",
  schedule: "0 9 * * *",
  run_on_start: false,
  timeout_seconds: 60,
  message: "Research",
};
beforeEach(async () => {
  api.list.mockReset();
  await i18n.changeLanguage("zh");
});
afterEach(cleanup);

test("task approval uses the configured catalog label", async () => {
  api.list.mockResolvedValue({
    agents: [
      {
        id: "search",
        name: "Search Agent",
        description: "",
        version: "1",
        labels: { zh: { name: "研究助手" } },
      },
    ],
  });
  render(<ScheduledTaskApprovalContent preview={preview} />);
  expect(await screen.findByText("研究助手")).toBeVisible();
  expect(screen.queryByText("search", { exact: true })).toBeNull();
});

test("task approval retains built-in translations if catalog loading fails", async () => {
  api.list.mockRejectedValue(new Error("offline"));
  render(<ScheduledTaskApprovalContent preview={preview} />);
  expect(await screen.findByText("探索助手")).toBeVisible();
});

test("unknown task agent IDs remain readable without a catalog", async () => {
  api.list.mockResolvedValue({ agents: [] });
  render(
    <ScheduledTaskApprovalContent
      preview={{ ...preview, agent_id: "archived-agent" }}
    />,
  );
  expect(await screen.findByText("archived-agent")).toBeVisible();
});
