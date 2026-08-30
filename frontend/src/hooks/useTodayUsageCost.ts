// 当日个人用量统计：挂载拉取 + 5 分钟轮询 + 手动刷新，失败静默保留上次值。
// "今日"按客户端本地 0 点计算（每次请求重新取当天 0 点，跨天轮询自动切换）。
import { useCallback, useEffect, useRef, useState } from "react";
import { usageApi } from "../services/api/usage";
import { startOfLocalDay } from "../utils/datetime";
import type { UsageStats } from "../types/usage";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

export function useTodayUsageCost(): {
  stats: UsageStats | null;
  refresh: () => void;
} {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const inFlight = useRef(false);

  const fetchStats = useCallback(async () => {
    if (inFlight.current) return;
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
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const timer = setInterval(fetchStats, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchStats]);

  return { stats, refresh: fetchStats };
}
