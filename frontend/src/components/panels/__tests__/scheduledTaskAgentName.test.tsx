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

test("task approval presents labeled parameters and preserves plain prompt text", async () => {
  api.list.mockResolvedValue({ agents: [] });
  const message = "第一行 **原文**\n第二行 <script>literal</script>";
  render(<ScheduledTaskApprovalContent preview={{ ...preview, message }} />);
  expect(await screen.findByText("探索助手")).toBeVisible();
  expect(screen.getAllByRole("term")).toHaveLength(5);
  expect(screen.queryByText("超时时间")).toBeNull();
  expect(screen.queryByText("无总时长限制")).toBeNull();
  expect(screen.getAllByRole("definition")[0]).toHaveTextContent(preview.name);
  expect(screen.getByText(/第一行/).tagName).toBe("P");
  expect(screen.getByText(/第一行/).textContent).toBe(message);
});

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

test("conversation task approval explains independent execution and result delivery", async () => {
  api.list.mockResolvedValue({ agents: [] });
  const conversationPreview = {
    ...preview,
    execution_mode: "conversation" as const,
  };
  render(<ScheduledTaskApprovalContent preview={conversationPreview} />);
  expect(await screen.findByText("结果发回此对话")).toBeVisible();
  expect(
    screen.getByText("独立运行并保留任务历史，结果发送到此对话。"),
  ).toBeVisible();
  expect(screen.queryByText(/每次执行会启动一个新会话/)).toBeNull();
});
