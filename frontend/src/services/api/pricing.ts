/**
 * Pricing API - 模型价格与 USD 汇率
 *
 * 汇率表由组件按需拉取，模块内缓存 30 分钟（后端本身 24h 同步一次）；
 * 拉取失败返回 null，调用方回落 USD 展示。
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export interface FxRatesResponse {
  base: string;
  rates: Record<string, number>;
  synced_at: string | null;
}

export interface PricingLookupResponse {
  found: boolean;
  source: string;
  rates: Record<string, number | null> | null;
  matched_provider: string;
  matched_model_id: string;
}

export interface PricingStatusResponse {
  prices: { entry_count: number; source_url: string; synced_at: string | null };
  fx: { base: string; rate_count: number; synced_at: string | null };
}

export interface PricingSyncResponse extends PricingStatusResponse {
  refreshed: boolean;
  error: string | null;
}

export interface PricingBackfillResponse {
  scanned: number;
  priced: number;
  still_unpriced: number;
  unpriced_models: Record<string, number>;
  dry_run: boolean;
}

const FX_CACHE_TTL_MS = 30 * 60 * 1000;

let fxCache: { doc: FxRatesResponse | null; at: number } | null = null;
let fxInflight: Promise<FxRatesResponse | null> | null = null;

/** 获取 USD 基准汇率表（带缓存；失败返回 null） */
export async function getFxRates(force = false): Promise<FxRatesResponse | null> {
  const now = Date.now();
  if (!force && fxCache && now - fxCache.at < FX_CACHE_TTL_MS) {
    return fxCache.doc;
  }
  if (!force && fxInflight) return fxInflight;

  fxInflight = authFetch<FxRatesResponse>(`${API_BASE}/api/pricing/rates`)
    .then((doc) => {
      fxCache = { doc, at: Date.now() };
      return doc;
    })
    .catch(() => {
      // 失败保留旧缓存（若有），调用方回落 USD
      if (fxCache) fxCache = { doc: fxCache.doc, at: Date.now() };
      return fxCache?.doc ?? null;
    })
    .finally(() => {
      fxInflight = null;
    });
  return fxInflight;
}

export const pricingApi = {
  /** 管理员：手动同步 models.dev 价格 + 汇率 */
  async sync(): Promise<PricingSyncResponse> {
    const doc = await authFetch<PricingSyncResponse>(`${API_BASE}/api/pricing/sync`, {
      method: "POST",
    });
    void getFxRates(true).catch(() => null);
    return doc;
  },

  /** 管理员：补算存量 usage_logs 费用（幂等） */
  async backfillUsage(dryRun = false): Promise<PricingBackfillResponse> {
    return authFetch<PricingBackfillResponse>(
      `${API_BASE}/api/pricing/backfill-usage?dry_run=${dryRun}`,
      { method: "POST" },
    );
  },

  /** 管理员：同步状态 */
  async status(): Promise<PricingStatusResponse> {
    return authFetch<PricingStatusResponse>(`${API_BASE}/api/pricing/status`);
  },

  /** 管理员：按模型标识查询单价 */
  async lookup(params: {
    value: string;
    provider?: string;
    model_id?: string;
  }): Promise<PricingLookupResponse> {
    const searchParams = new URLSearchParams({ value: params.value });
    if (params.provider) searchParams.append("provider", params.provider);
    if (params.model_id) searchParams.append("model_id", params.model_id);
    return authFetch<PricingLookupResponse>(
      `${API_BASE}/api/pricing/lookup?${searchParams.toString()}`,
    );
  },
};
