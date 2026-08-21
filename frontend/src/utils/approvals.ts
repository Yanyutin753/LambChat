import type { PendingApproval } from "../types";

export interface ApprovalRespondResult {
  status: string;
  approval_id: string;
  approved: boolean;
  hitl_resume?: {
    submitted: boolean;
    run_id: string | null;
    message: string;
  } | null;
}

export function isApprovalResponseAccepted(
  result: ApprovalRespondResult | null,
): boolean {
  return (
    result?.status === "success" && result.hitl_resume?.submitted !== false
  );
}

/**
 * 按当前会话过滤审批列表。
 *
 * - 只显示当前会话的审批
 * - 无会话归属的审批（如全局定时任务）始终显示
 * - 新对话（sessionId 为 null）时只显示无会话归属的审批
 */
export function filterApprovalsBySession(
  approvals: PendingApproval[],
  sessionId: string | null | undefined,
): PendingApproval[] {
  return approvals.filter(
    (approval) =>
      approval.session_id == null || approval.session_id === sessionId,
  );
}
