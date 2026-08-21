import { useState, useCallback, useEffect, useRef } from "react";
import type { PendingApproval } from "../types";
import { authFetch } from "../services/api/fetch";
import { API_BASE } from "../services/api/config";
import {
  isApprovalResponseAccepted,
  type ApprovalRespondResult,
} from "../utils/approvals";

interface UseApprovalsOptions {
  sessionId: string | null;
  onInterruptResume?: () => void;
}

export function useApprovals({
  sessionId,
  onInterruptResume,
}: UseApprovalsOptions) {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const hasApprovalsRef = useRef(false);

  const fetchApprovals = useCallback(async () => {
    try {
      const data = await authFetch<{ approvals?: PendingApproval[] }>(
        `${API_BASE}/human/pending`,
      );
      if (data) {
        const newApprovals = data.approvals || [];
        setApprovals(newApprovals);
        hasApprovalsRef.current = newApprovals.length > 0;
      }
    } catch (error) {
      console.error("Failed to fetch approvals:", error);
    }
  }, []);

  // 添加来自 SSE 的 approval（不再需要轮询来发现）
  const addApproval = useCallback((approval: PendingApproval) => {
    setApprovals((prev) => {
      // 避免重复添加
      if (prev.some((a) => a.id === approval.id)) {
        return prev;
      }
      hasApprovalsRef.current = true;
      return [...prev, approval];
    });
  }, []);

  // 清除 approvals（用于对话失败时）；传入 sessionId 时只清除该会话的，
  // 避免误清其他会话（如后台等待审批的会话）的待处理审批
  const clearApprovals = useCallback((sessionId?: string | null) => {
    setApprovals((prev) => {
      const next =
        sessionId == null ? [] : prev.filter((a) => a.session_id !== sessionId);
      hasApprovalsRef.current = next.length > 0;
      return next;
    });
  }, []);

  const respondToApproval = useCallback(
    async (
      approvalId: string,
      response: Record<string, unknown>,
      approved: boolean = true,
    ) => {
      setIsLoading(true);
      try {
        // 将响应对象序列化为 JSON 字符串
        const responseJson = JSON.stringify(response);
        const params = new URLSearchParams({
          approved: String(approved),
          response: responseJson,
        });
        const res = await authFetch<ApprovalRespondResult>(
          `${API_BASE}/human/${approvalId}/respond?${params}`,
          {
            method: "POST",
          },
        );

        if (isApprovalResponseAccepted(res)) {
          setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
          if (res?.hitl_resume?.submitted) {
            onInterruptResume?.();
          }
          return true;
        }
        return false;
      } catch (error) {
        console.error("Failed to respond to approval:", error);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [onInterruptResume],
  );

  // 初始加载时获取一次（用于页面刷新后恢复状态）
  useEffect(() => {
    if (!sessionId) return;
    fetchApprovals();
  }, [fetchApprovals, sessionId]);

  return {
    approvals,
    isLoading,
    respondToApproval,
    addApproval,
    clearApprovals,
    refresh: fetchApprovals,
  };
}
