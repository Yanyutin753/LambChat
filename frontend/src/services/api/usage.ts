/**
 * Usage API - Token consumption tracking
 */

import i18n from "i18next";
import { authFetch } from "./fetch";
import { API_BASE } from "./config";
import type {
  UsageDashboardResponse,
  UsageLogListResponse,
  UsageStats,
} from "../../types/usage";

export interface UsageQuotaWindow {
  limit_usd: number | null;
  used_usd: number;
  reserved_usd: number;
  remaining_usd: number | null;
  reset_at: string | null;
  blocked: boolean;
  unknown: boolean;
}

export interface UsageResetCredit {
  id: string;
  status: "available";
  granted_at: string;
  expires_at: string;
  window?: "five_hour" | "weekly";
}

export interface UsageResetHistory {
  id: string;
  window?: "five_hour" | "weekly";
  redeemed_at: string;
}

export type QuotaResetOutcome =
  | "reset"
  | "alreadyRedeemed"
  | "nothingToReset"
  | "noCredit";

export interface UsageQuota {
  currency: "USD";
  timezone: string;
  five_hour: UsageQuotaWindow;
  weekly: UsageQuotaWindow;
  reset_credits?: {
    available_count: number;
    credits: UsageResetCredit[];
    history?: UsageResetHistory[];
  };
}

export interface ResetCardBatch {
  id: string;
  window: "five_hour" | "weekly";
  status: "preparing" | "running" | "completed";
  total: number;
  processed: number;
  issued: number;
  failed: number;
  errors: { user_id: string; code: string; message: string }[];
}

function parseResetCardBatch(data: unknown): ResetCardBatch {
  const batch = data as ResetCardBatch | null;
  if (
    !batch ||
    typeof batch.id !== "string" ||
    !batch.id ||
    !["five_hour", "weekly"].includes(batch.window) ||
    !["preparing", "running", "completed"].includes(batch.status) ||
    ![batch.total, batch.processed, batch.issued, batch.failed].every(
      (count) => Number.isSafeInteger(count) && count >= 0,
    ) ||
    batch.processed > batch.total ||
    batch.issued + batch.failed !== batch.processed ||
    (batch.status === "completed" && batch.processed !== batch.total) ||
    !Array.isArray(batch.errors) ||
    !batch.errors.every(
      (error) =>
        error &&
        typeof error.user_id === "string" &&
        typeof error.code === "string" &&
        typeof error.message === "string",
    )
  )
    throw new Error(i18n.t("usage.quotaUnavailable"));
  return batch;
}

export function canRedeemResetCard(
  quota: UsageQuota,
  window?: "five_hour" | "weekly",
): boolean {
  return (window ? [quota[window]] : [quota.five_hour, quota.weekly]).some(
    (pool) =>
      pool.limit_usd !== null &&
      pool.limit_usd > 0 &&
      (window ? pool.used_usd > 0 : pool.used_usd >= pool.limit_usd),
  );
}

export function parseUsageQuota(data: unknown): UsageQuota {
  const quota = data as Partial<UsageQuota> | null;
  const validAmount = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value) && value >= 0;
  const validDate = (value: unknown) =>
    typeof value === "string" && Number.isFinite(Date.parse(value));
  const credits = quota?.reset_credits;
  if (
    !quota ||
    typeof quota !== "object" ||
    quota.currency !== "USD" ||
    typeof quota.timezone !== "string" ||
    !quota.timezone ||
    ![quota.five_hour, quota.weekly].every(
      (window) =>
        window &&
        typeof window === "object" &&
        (window.limit_usd === null || validAmount(window.limit_usd)) &&
        (window.remaining_usd === null || validAmount(window.remaining_usd)) &&
        validAmount(window.used_usd) &&
        validAmount(window.reserved_usd) &&
        typeof window.blocked === "boolean" &&
        typeof window.unknown === "boolean" &&
        (window.reset_at === null || validDate(window.reset_at)),
    ) ||
    (credits !== undefined &&
      (!credits ||
        !Number.isInteger(credits.available_count) ||
        credits.available_count < 0 ||
        (credits.history !== undefined &&
          (!Array.isArray(credits.history) ||
            !credits.history.every(
              (entry) =>
                entry &&
                typeof entry.id === "string" &&
                entry.id.length > 0 &&
                validDate(entry.redeemed_at) &&
                (entry.window === undefined ||
                  entry.window === "five_hour" ||
                  entry.window === "weekly"),
            ))) ||
        !Array.isArray(credits.credits) ||
        !credits.credits.every(
          (card) =>
            card &&
            typeof card.id === "string" &&
            card.id.length > 0 &&
            card.status === "available" &&
            (card.window === undefined ||
              card.window === "five_hour" ||
              card.window === "weekly") &&
            validDate(card.granted_at) &&
            validDate(card.expires_at),
        )))
  )
    throw new Error(i18n.t("usage.quotaUnavailable"));
  return quota as UsageQuota;
}

function validateQuotaMutation(
  data: unknown,
  outcomes: readonly string[],
): void {
  const result = data as { outcome?: unknown; credit_id?: unknown } | null;
  if (
    !result ||
    typeof result.outcome !== "string" ||
    !outcomes.includes(result.outcome) ||
    ((result.outcome === "issued" || result.outcome === "alreadyIssued") &&
      (typeof result.credit_id !== "string" || !result.credit_id))
  )
    throw new Error(i18n.t("usage.quotaUnavailable"));
}

export interface UsageLogsParams {
  skip?: number;
  limit?: number;
  user_id?: string;
  model?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
}

export interface UsageStatsParams {
  user_id?: string;
  period?: "today" | "week" | "month" | "all";
  /** ISO 起始时间（含时区），优先于 period 推导；今日按客户端本地 0 点传 */
  start_date?: string;
}

export interface UsageDashboardParams extends UsageStatsParams {
  model?: string;
  search?: string;
  /** ISO 起始时间（含时区），优先于 period 推导 */
  start_date?: string;
}

export const usageApi = {
  async createResetCardBatch(
    window: ResetCardBatch["window"],
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<ResetCardBatch> {
    return parseResetCardBatch(
      await authFetch(`${API_BASE}/api/usage/quota/reset-card-batches`, {
        method: "POST",
        body: JSON.stringify({ window, idempotency_key: idempotencyKey }),
        signal,
      }),
    );
  },

  async getResetCardBatch(
    id: string,
    signal?: AbortSignal,
  ): Promise<ResetCardBatch> {
    return parseResetCardBatch(
      await authFetch(
        `${API_BASE}/api/usage/quota/reset-card-batches/${encodeURIComponent(
          id,
        )}`,
        { signal },
      ),
    );
  },

  async listResetCardBatches(
    signal?: AbortSignal,
  ): Promise<{ items: ResetCardBatch[] }> {
    const result = await authFetch<{ items: unknown[] }>(
      `${API_BASE}/api/usage/quota/reset-card-batches?limit=1`,
      { signal },
    );
    if (!result || !Array.isArray(result.items))
      throw new Error(i18n.t("usage.quotaUnavailable"));
    return { items: result.items.map(parseResetCardBatch) };
  },

  async advanceResetCardBatch(
    id: string,
    signal?: AbortSignal,
  ): Promise<ResetCardBatch> {
    return parseResetCardBatch(
      await authFetch(
        `${API_BASE}/api/usage/quota/reset-card-batches/${encodeURIComponent(
          id,
        )}/advance`,
        { method: "POST", signal },
      ),
    );
  },

  async getQuota(signal?: AbortSignal): Promise<UsageQuota> {
    const url = `${API_BASE}/api/usage/quota`;
    return parseUsageQuota(
      await (signal ? authFetch(url, { signal }) : authFetch(url)),
    );
  },

  async getUserQuota(userId: string): Promise<UsageQuota> {
    return parseUsageQuota(
      await authFetch(
        `${API_BASE}/api/usage/users/${encodeURIComponent(userId)}/quota`,
      ),
    );
  },

  async resetUserQuota(
    userId: string,
    window: "five_hour" | "weekly",
    idempotencyKey: string,
  ): Promise<{ outcome: Exclude<QuotaResetOutcome, "noCredit"> }> {
    const result = await authFetch<{
      outcome: Exclude<QuotaResetOutcome, "noCredit">;
    }>(
      `${API_BASE}/api/usage/users/${encodeURIComponent(userId)}/quota/reset`,
      {
        method: "POST",
        body: JSON.stringify({ window, idempotency_key: idempotencyKey }),
      },
    );
    validateQuotaMutation(result, [
      "reset",
      "alreadyRedeemed",
      "nothingToReset",
    ]);
    return result;
  },

  async issueResetCard(
    userId: string,
    idempotencyKey: string,
    window: "five_hour" | "weekly" = "five_hour",
  ): Promise<{ outcome: "issued" | "alreadyIssued"; credit_id: string }> {
    const result = await authFetch<{
      outcome: "issued" | "alreadyIssued";
      credit_id: string;
    }>(
      `${API_BASE}/api/usage/users/${encodeURIComponent(
        userId,
      )}/quota/reset-cards`,
      {
        method: "POST",
        body: JSON.stringify({ idempotency_key: idempotencyKey, window }),
      },
    );
    validateQuotaMutation(result, ["issued", "alreadyIssued"]);
    return result;
  },

  async consumeResetCard(
    idempotencyKey: string,
    creditId?: string,
  ): Promise<{ outcome: QuotaResetOutcome }> {
    const result = await authFetch<{ outcome: QuotaResetOutcome }>(
      `${API_BASE}/api/usage/quota/reset-cards/consume`,
      {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: idempotencyKey,
          ...(creditId ? { credit_id: creditId } : {}),
        }),
      },
    );
    validateQuotaMutation(result, [
      "reset",
      "alreadyRedeemed",
      "nothingToReset",
      "noCredit",
    ]);
    return result;
  },

  /**
   * Get usage logs (paginated)
   */
  async list(params: UsageLogsParams = {}): Promise<UsageLogListResponse> {
    const searchParams = new URLSearchParams();
    if (params.skip !== undefined)
      searchParams.append("skip", params.skip.toString());
    if (params.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params.user_id) searchParams.append("user_id", params.user_id);
    if (params.model) searchParams.append("model", params.model);
    if (params.start_date) searchParams.append("start_date", params.start_date);
    if (params.end_date) searchParams.append("end_date", params.end_date);
    if (params.search) searchParams.append("search", params.search);
    const query = searchParams.toString() ? `?${searchParams}` : "";
    return authFetch<UsageLogListResponse>(
      `${API_BASE}/api/usage/logs${query}`,
    );
  },

  /**
   * Get aggregated usage stats
   */
  async getStats(params: UsageStatsParams = {}): Promise<UsageStats> {
    const searchParams = new URLSearchParams();
    if (params.user_id) searchParams.append("user_id", params.user_id);
    if (params.period && params.period !== "all")
      searchParams.append("period", params.period);
    if (params.start_date) searchParams.append("start_date", params.start_date);
    const query = searchParams.toString() ? `?${searchParams}` : "";
    return authFetch<UsageStats>(`${API_BASE}/api/usage/stats${query}`);
  },

  /**
   * Get dashboard aggregates for the digital worker operations view
   */
  async getDashboard(
    params: UsageDashboardParams = {},
  ): Promise<UsageDashboardResponse> {
    const searchParams = new URLSearchParams();
    if (params.user_id) searchParams.append("user_id", params.user_id);
    if (params.period) searchParams.append("period", params.period);
    if (params.model) searchParams.append("model", params.model);
    if (params.search) searchParams.append("search", params.search);
    if (params.start_date) searchParams.append("start_date", params.start_date);
    const query = searchParams.toString() ? `?${searchParams}` : "";
    return authFetch<UsageDashboardResponse>(
      `${API_BASE}/api/usage/dashboard${query}`,
    );
  },
};
