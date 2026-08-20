import type { PendingApproval } from "../../types";
import { filterApprovalsBySession } from "../approvals";
import { buildSteerUserMessage } from "../steerMessages";

function approval(overrides: Partial<PendingApproval>): PendingApproval {
  return {
    id: "a-1",
    message: "请确认",
    type: "form",
    fields: [],
    status: "pending",
    ...overrides,
  };
}

describe("filterApprovalsBySession", () => {
  test("只保留当前会话的审批", () => {
    const approvals = [
      approval({ id: "mine", session_id: "s-1" }),
      approval({ id: "other", session_id: "s-2" }),
    ];
    expect(filterApprovalsBySession(approvals, "s-1").map((a) => a.id)).toEqual([
      "mine",
    ]);
  });

  test("无会话归属的审批（如全局任务）始终显示", () => {
    const approvals = [
      approval({ id: "global", session_id: null }),
      approval({ id: "global-undef" }),
      approval({ id: "other", session_id: "s-2" }),
    ];
    expect(filterApprovalsBySession(approvals, "s-1").map((a) => a.id)).toEqual([
      "global",
      "global-undef",
    ]);
  });

  test("新对话（无当前会话）只显示无会话归属的审批", () => {
    const approvals = [
      approval({ id: "global", session_id: null }),
      approval({ id: "session-scoped", session_id: "s-1" }),
    ];
    expect(filterApprovalsBySession(approvals, null).map((a) => a.id)).toEqual([
      "global",
    ]);
  });
});

describe("buildSteerUserMessage", () => {
  test("构造待送达的用户消息（带 steer 标记）", () => {
    const message = buildSteerUserMessage({
      previousCount: 3,
      content: "中途插话",
      createId: () => "fixed-id",
      now: new Date("2026-08-20T12:00:00Z"),
    });
    expect(message.id).toBe("fixed-id");
    expect(message.role).toBe("user");
    expect(message.content).toBe("中途插话");
    expect(message.metadata?.steered).toBe(true);
  });

  test("不修改原数组", () => {
    const previous = [{ id: "u1", role: "user", content: "hi", timestamp: new Date() }];
    buildSteerUserMessage({
      previousCount: previous.length,
      content: "x",
      createId: () => "id2",
    });
    expect(previous).toHaveLength(1);
  });
});
