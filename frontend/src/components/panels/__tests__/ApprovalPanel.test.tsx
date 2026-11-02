/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";
import i18n from "../../../i18n";
import type { PendingApproval } from "../../../types";
import { ApprovalPanel } from "../ApprovalPanel";
import {
  loadApprovalFormDraft,
  saveApprovalFormDraft,
} from "../approvalDraftStore";

vi.mock("../../agent/useAgentCatalog", () => ({
  useAgentCatalog: () => [],
}));
vi.mock("../../common/InteractiveIcon", () => ({
  InteractiveIcon: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("../../../services/api/fetch", () => ({
  authFetch: vi.fn().mockResolvedValue(null),
}));

beforeEach(async () => {
  await i18n.changeLanguage("zh");
});
afterEach(cleanup);
afterEach(() => vi.useRealTimers());

function approval(overrides: Partial<PendingApproval> = {}): PendingApproval {
  return {
    id: "confirmation",
    type: "form",
    status: "pending",
    message: "确认继续？",
    fields: [],
    ...overrides,
  };
}

test("scheduled confirmation opens as the same full card as ask human", async () => {
  const onRespond = vi.fn();
  const { container } = render(
    <ApprovalPanel
      approvals={[
        approval({
          message: "Please confirm.\n| **Name** | 每分钟随机数字 |",
          metadata: {
            approval_type: "scheduled_task_create",
            preview: {
              name: "每分钟随机数字",
              agent_id: "search",
              schedule: "every 1 minute(s)",
              run_on_start: true,
              timeout_seconds: 0,
              message: "回复一个随机数字。",
            },
          },
        }),
      ]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );

  expect(await screen.findByText("每分钟随机数字")).toBeVisible();
  expect(screen.getByText("回复一个随机数字。")).toBeVisible();
  expect(screen.getAllByRole("term")).toHaveLength(5);
  expect(screen.getAllByText("请确认创建此定时任务。")).toHaveLength(1);
  expect(container.querySelector(".approval-ask-human-header")).toBeVisible();
  expect(container.querySelector(".approval-ask-human-footer")).toBeVisible();
  expect(container.querySelector("[aria-expanded]")).toBeNull();
  expect(screen.queryByText(/Please confirm/)).toBeNull();
  expect(onRespond).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "提交" }));
  expect(onRespond).toHaveBeenCalledWith("confirmation", {}, true);
});

test.each([undefined, { mode: "interrupt" }])(
  "confirmation shares visible choices and validation (metadata: %j)",
  (metadata) => {
    const onRespond = vi.fn();
    const { container } = render(
      <ApprovalPanel
        approvals={[
          approval({
            metadata,
            fields: [
              {
                name: "platform",
                type: "radio",
                label: "验证平台",
                options: ["桌面端", "移动端"],
                required: true,
              },
            ],
          }),
        ]}
        onRespond={onRespond}
        isLoading={false}
      />,
    );
    const submit = screen.getByRole("button", { name: "提交" });
    expect(submit).toBeDisabled();
    expect(container.querySelector(".approval-card--ask-human")).toBeVisible();
    fireEvent.click(screen.getByRole("option", { name: /桌面端/ }));
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    expect(onRespond).toHaveBeenCalledWith(
      "confirmation",
      { platform: "桌面端" },
      true,
    );
  },
);

test("restores a saved browser draft when the approval reappears", async () => {
  localStorage.clear();
  const askHumanFields: PendingApproval["fields"] = [
    {
      name: "platform",
      type: "radio",
      label: "验证平台",
      options: ["桌面端", "移动端"],
      required: true,
    },
    {
      name: "note",
      type: "text",
      label: "备注",
      required: false,
      placeholder: "补充说明",
    },
  ];
  saveApprovalFormDraft("confirmation", { platform: "桌面端" });
  render(
    <ApprovalPanel
      approvals={[
        approval({ metadata: { mode: "interrupt" }, fields: askHumanFields }),
      ]}
      onRespond={vi.fn()}
      isLoading={false}
    />,
  );

  expect(await screen.findByRole("option", { name: /桌面端/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByRole("button", { name: "提交" })).toBeEnabled();
  expect(screen.getByPlaceholderText("补充说明")).toHaveValue("");
});

test("persists edits as a browser draft and clears it once submitted", async () => {
  localStorage.clear();
  const askHumanFields: PendingApproval["fields"] = [
    {
      name: "platform",
      type: "radio",
      label: "验证平台",
      options: ["桌面端", "移动端"],
      required: true,
    },
  ];
  const onRespond = vi.fn().mockResolvedValue(true);
  render(
    <ApprovalPanel
      approvals={[
        approval({ metadata: { mode: "interrupt" }, fields: askHumanFields }),
      ]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );

  fireEvent.click(screen.getByRole("option", { name: /桌面端/ }));
  expect(loadApprovalFormDraft("confirmation", askHumanFields)).toEqual({
    platform: "桌面端",
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
  });
  expect(onRespond).toHaveBeenCalledWith(
    "confirmation",
    { platform: "桌面端" },
    true,
  );
  expect(loadApprovalFormDraft("confirmation", askHumanFields)).toBeNull();
});

test("keeps the browser draft when responding fails", async () => {
  localStorage.clear();
  const askHumanFields: PendingApproval["fields"] = [
    {
      name: "platform",
      type: "radio",
      label: "验证平台",
      options: ["桌面端", "移动端"],
      required: true,
    },
  ];
  const onRespond = vi.fn().mockResolvedValue(false);
  render(
    <ApprovalPanel
      approvals={[
        approval({ metadata: { mode: "interrupt" }, fields: askHumanFields }),
      ]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );

  fireEvent.click(screen.getByRole("option", { name: /桌面端/ }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
  });
  expect(loadApprovalFormDraft("confirmation", askHumanFields)).toEqual({
    platform: "桌面端",
  });
});

test("ordinary confirmation renders markdown immediately and keeps cancellation", () => {
  const onRespond = vi.fn();
  render(
    <ApprovalPanel
      approvals={[
        approval({
          message: "**请确认**\n\n| 名称 | 值 |\n| --- | --- |\n| 次数 | 1 |",
        }),
      ]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );
  expect(screen.getByRole("table")).toBeVisible();
  expect(screen.getByText("请确认").tagName).toBe("STRONG");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onRespond).toHaveBeenCalledWith("confirmation", {}, false);
});

test("a loading confirmation keeps both actions disabled", () => {
  render(
    <ApprovalPanel approvals={[approval()]} onRespond={vi.fn()} isLoading />,
  );
  expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
});

test("restoring a confirmation keeps its original absolute deadline", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-18T00:00:00.000Z"));
  const pending = approval({
    expires_at: "2026-10-18T00:05:00.000Z",
    timeout: 3600,
  });
  const onRespond = vi.fn();
  const view = render(
    <ApprovalPanel
      approvals={[pending]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );
  expect(screen.getByText("5:00")).toBeVisible();
  act(() => vi.advanceTimersByTime(61_000));
  expect(screen.getByText("3:59")).toBeVisible();
  view.unmount();
  render(
    <ApprovalPanel
      approvals={[pending]}
      onRespond={onRespond}
      isLoading={false}
    />,
  );
  expect(screen.getByText("3:59")).toBeVisible();
  expect(onRespond).not.toHaveBeenCalled();
});

test.each([undefined, { mode: "interrupt" }])(
  "only timed ordinary confirmations show a countdown (metadata: %j)",
  (metadata) => {
    const { container } = render(
      <ApprovalPanel
        approvals={[approval({ metadata, timeout: 120 })]}
        onRespond={vi.fn()}
        isLoading={false}
      />,
    );
    if (metadata) {
      expect(container.querySelector(".approval-timer")).toBeNull();
    } else {
      expect(container.querySelector(".approval-timer")).toBeVisible();
    }
  },
);
