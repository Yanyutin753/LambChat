/**
 * Feedback API - 用户反馈管理
 * 每个用户对每个 run 只能提交一次反馈
 */

import { authFetch } from "./fetch";
import type {
  Feedback,
  FeedbackCreate,
  FeedbackListResponse,
  FeedbackStats,
  RatingValue,
} from "../../types/feedback";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const feedbackApi = {
  /**
   * 提交反馈
   */
  async submit(data: FeedbackCreate): Promise<Feedback> {
    return authFetch<Feedback>(`${API_BASE}/api/feedback/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * 获取当前用户对某个 run 的反馈
   */
  async getMyByRun(sessionId: string, runId: string): Promise<Feedback | null> {
    try {
      return await authFetch<Feedback | null>(
        `${API_BASE}/api/feedback/my/by-run/${sessionId}/${runId}`,
      );
    } catch {
      return null;
    }
  },

  /**
   * 获取某个 run 的所有反馈
   */
  async getByRun(sessionId: string, runId: string): Promise<Feedback[]> {
    return authFetch<Feedback[]>(
      `${API_BASE}/api/feedback/by-run/${sessionId}/${runId}`,
    );
  },

  /**
   * 获取某个 run 的统计信息
   */
  async getRunStats(sessionId: string, runId: string): Promise<FeedbackStats> {
    return authFetch<FeedbackStats>(
      `${API_BASE}/api/feedback/stats/${sessionId}/${runId}`,
    );
  },

  /**
   * 获取反馈列表
   */
  async list(
    skip: number = 0,
    limit: number = 50,
    rating?: RatingValue,
    userId?: string,
    sessionId?: string,
  ): Promise<FeedbackListResponse> {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
    });
    if (rating) {
      params.append("rating", rating);
    }
    if (userId) {
      params.append("user_id", userId);
    }
    if (sessionId) {
      params.append("session_id", sessionId);
    }
    return authFetch<FeedbackListResponse>(
      `${API_BASE}/api/feedback/?${params}`,
    );
  },

  /**
   * 获取统计信息
   */
  async getStats(sessionId?: string, runId?: string): Promise<FeedbackStats> {
    const params = new URLSearchParams();
    if (sessionId) {
      params.append("session_id", sessionId);
    }
    if (runId) {
      params.append("run_id", runId);
    }
    const query = params.toString() ? `?${params}` : "";
    return authFetch<FeedbackStats>(`${API_BASE}/api/feedback/stats${query}`);
  },

  /**
   * 删除反馈
   */
  async delete(feedbackId: string): Promise<void> {
    return authFetch(`${API_BASE}/api/feedback/${feedbackId}`, {
      method: "DELETE",
    });
  },
};
