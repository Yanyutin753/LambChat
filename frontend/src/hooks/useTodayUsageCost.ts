// 当日个人用量统计：挂载拉取 + 5 分钟轮询 + 手动刷新，失败静默保留上次值。
// "今日"按客户端本地 0 点计算（每次请求重新取当天 0 点，跨天轮询自动切换）。
// 监听 today-usage-refresh 事件（一轮对话结束时 ChatInput 派发）立即刷新。
import { useCallback, useEffect, useRef, useState } from "react";
import { usageApi } from "../services/api/usage";
import { startOfLocalDay } from "../utils/datetime";
import type { UsageStats } from "../types/usage";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000;
export const TODAY_USAGE_REFRESH_EVENT = "today-usage-refresh";

export function useTodayUsageCost(): {
  stats: UsageStats | null;
  refresh: () => void;
} {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const inFlight = useRef(false);
  const pending = useRef(false);

  const fetchStats = useCallback(async () => {
    // 在途时到达的刷新（如 WS 推送撞上 SSE 关流刷新）不能并发也不能丢：记一笔，结束后补拉
    if (inFlight.current) {
      pending.current = true;
      return;
    }
    inFlight.current = true;
    try {
      const data = await usageApi.getStats({
        period: "today",
        start_date: startOfLocalDay(new Date()).toISOString(),
      });
      setStats(data);
    } catch {
      // 静默失败：徽标保留上次值或保持隐藏
    } finally {
      inFlight.current = false;
      if (pending.current) {
        pending.current = false;
        void fetchStats();
      }
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const timer = setInterval(fetchStats, REFRESH_INTERVAL_MS);
    const onRefresh = () => fetchStats();
    window.addEventListener(TODAY_USAGE_REFRESH_EVENT, onRefresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener(TODAY_USAGE_REFRESH_EVENT, onRefresh);
    };
  }, [fetchStats]);

  return { stats, refresh: fetchStats };
}

/** 一轮对话运行结束（isLoading true→false）时派发刷新事件，供 useTodayUsageCost 立即拉取。 */
export function useNotifyTodayUsageRefresh(isLoading: boolean) {
  const prevLoading = useRef(isLoading);
  useEffect(() => {
    if (prevLoading.current && !isLoading) {
      window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT));
    }
    prevLoading.current = isLoading;
  }, [isLoading]);
}
