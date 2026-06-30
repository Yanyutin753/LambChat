/**
 * Usage Details Panel — Token consumption tracking
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Zap,
  ArrowUpFromLine,
  Clock,
  Bot,
  Activity,
  RefreshCw,
  DatabaseZap,
  CalendarClock,
  Users,
  BadgeCheck,
  Wrench,
  PieChart,
  UserRound,
  LayoutDashboard,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { PanelFilterSelect } from "../common";
import { Pagination } from "../common/Pagination";
import { UsagePanelSkeleton } from "../skeletons";
import {
  DistributionList,
  InsightStrip,
  MiniTrend,
  RankingList,
  StatMetric,
  UsageLogsTable,
  fmt,
  fmtDur,
  pct,
} from "./UsagePanel/index";
import { usageApi } from "../../services/api/usage";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  UsageDashboardResponse,
  UsageLog,
  UsageStats,
} from "../../types/usage";

// ── Helpers ──────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

// ── Main Component ─────────────────────────────────────

export function UsagePanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const isAdmin = hasPermission(Permission.USAGE_ADMIN);

  const [logs, setLogs] = useState<UsageLog[]>([]);
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [dashboard, setDashboard] = useState<UsageDashboardResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);

  const [skip, setSkip] = useState(0);
  const pageSize = 20;

  const [searchQuery, setSearchQuery] = useState("");
  const [period, setPeriod] = useState<string>("all");
  const debouncedSearch = useDebounce(searchQuery, 300);

  const handleSearchQueryChange = useCallback((query: string) => {
    setSkip(0);
    setSearchQuery(query);
  }, []);
  const handlePeriodChange = useCallback((nextPeriod: string) => {
    setSkip(0);
    setPeriod(nextPeriod);
  }, []);

  const computeDateRange = useCallback((p: string): { start_date?: string } => {
    const now = new Date();
    if (p === "today")
      return {
        start_date: new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
        ).toISOString(),
      };
    if (p === "week")
      return { start_date: new Date(now.getTime() - 7 * 864e5).toISOString() };
    if (p === "month")
      return { start_date: new Date(now.getTime() - 30 * 864e5).toISOString() };
    return {};
  }, []);

  const tRef = useRef(t);
  tRef.current = t;

  // Fetch logs independently
  const fetchLogs = useCallback(async () => {
    const dateRange = computeDateRange(period);
    const search = isAdmin && debouncedSearch ? debouncedSearch : undefined;
    const response = await usageApi.list({
      skip,
      limit: pageSize,
      search,
      ...dateRange,
    });
    setLogs(response.items);
    setTotal(response.total);
    setStats(response.stats);
  }, [skip, period, debouncedSearch, isAdmin, computeDateRange]);

  // Fetch dashboard independently (silent failure)
  const fetchDashboard = useCallback(async () => {
    try {
      const search = isAdmin && debouncedSearch ? debouncedSearch : undefined;
      const data = await usageApi.getDashboard({
        period: period as "today" | "week" | "month" | "all",
        search,
      });
      setDashboard(data);
    } catch {
      setDashboard(null);
    }
  }, [period, debouncedSearch, isAdmin]);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      await fetchLogs();
    } catch (err) {
      toast.error((err as Error).message || tRef.current("usage.loadFailed"));
    } finally {
      setIsLoading(false);
    }
    fetchDashboard();
  }, [fetchLogs, fetchDashboard]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const isInitialLoading =
    isLoading && logs.length === 0 && searchQuery.trim().length === 0;
  const page = Math.floor(skip / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const hasAnyCache = useMemo(
    () => logs.some((l) => l.cache_read_tokens > 0),
    [logs],
  );

  const cacheHitLabel = useMemo(() => {
    if (!stats || stats.total_input_tokens <= 0) return "0%";
    return `${Math.round(
      (stats.total_cache_read_tokens / stats.total_input_tokens) * 100,
    )}%`;
  }, [stats]);

  const dashboardSummary = dashboard?.summary;
  const dashboardTitle = isAdmin
    ? t("usage.dashboard.titleAdmin")
    : t("usage.dashboard.titleUser");
  const dashboardSubtitle = isAdmin
    ? t("usage.dashboard.subtitleAdmin")
    : t("usage.dashboard.subtitleUser");
  const personaRankingTitle = isAdmin
    ? t("usage.ranking.personaAdmin")
    : t("usage.ranking.personaUser");
  const teamRankingTitle = isAdmin
    ? t("usage.ranking.teamAdmin")
    : t("usage.ranking.teamUser");
  const agentRankingTitle = isAdmin
    ? t("usage.ranking.agentAdmin")
    : t("usage.ranking.agentUser");
  const modelRankingTitle = isAdmin
    ? t("usage.ranking.modelAdmin")
    : t("usage.ranking.modelUser");
  const sourceDistributionTitle = isAdmin
    ? t("usage.ranking.sourceAdmin")
    : t("usage.ranking.sourceUser");

  useEffect(() => {
    if (!isLoading && total > 0 && page > totalPages) {
      setSkip((totalPages - 1) * pageSize);
    }
  }, [isLoading, page, total, totalPages]);

  // ── Header controls ──
  const periodFilter = (
    <PanelFilterSelect
      value={period}
      onChange={handlePeriodChange}
      active={period !== "all"}
      options={[
        { value: "all", label: t("usage.allPeriods") },
        { value: "today", label: t("usage.today") },
        { value: "week", label: t("usage.thisWeek") },
        { value: "month", label: t("usage.thisMonth") },
      ]}
    />
  );

  const refreshButton = (
    <button
      type="button"
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-card)] text-theme-text-secondary transition-all duration-200 hover:border-[var(--glass-border-hover)] hover:text-theme-text active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 sm:h-10 sm:w-10"
      onClick={fetchData}
      disabled={isLoading}
      aria-label={t("usage.refresh")}
      title={t("usage.refresh")}
    >
      <RefreshCw size={15} className={isLoading ? "animate-spin" : undefined} />
    </button>
  );

  if (isInitialLoading) return <UsagePanelSkeleton />;

  return (
    <div className="glass-shell usage-panel flex h-full min-h-0 flex-col overflow-y-auto">
      <PanelHeader
        title={t("usage.title")}
        subtitle={t("usage.subtitle")}
        icon={<Activity size={22} className="text-theme-text-secondary" />}
        searchValue={isAdmin ? searchQuery : undefined}
        onSearchChange={isAdmin ? handleSearchQueryChange : undefined}
        searchPlaceholder={t("usage.searchPlaceholder")}
        searchAccessory={isAdmin ? periodFilter : undefined}
        searchActions={isAdmin ? refreshButton : undefined}
        actions={
          !isAdmin ? (
            <>
              {periodFilter}
              {refreshButton}
            </>
          ) : undefined
        }
      />

      {/* KPI Cards */}
      {stats && (
        <div className="mx-auto w-full px-4 pt-5 pb-4 sm:px-6 sm:pt-6 sm:pb-5 lg:px-8">
          <div className="usage-surface grid grid-cols-2 overflow-hidden rounded-xl md:grid-cols-3 xl:grid-cols-6">
            <StatMetric
              icon={Zap}
              label={t("usage.totalRequests")}
              value={fmt(stats.total_requests)}
              hint={
                dashboardSummary
                  ? t("usage.successRate", {
                      rate: pct(dashboardSummary.success_rate),
                    })
                  : undefined
              }
            />
            <StatMetric
              icon={Clock}
              label={t("usage.kpi.durationLabel")}
              value={fmtDur(stats.total_duration)}
              hint={t("usage.kpi.durationHint")}
            />
            <StatMetric
              icon={CalendarClock}
              label={t("usage.kpi.scheduledLabel")}
              value={
                dashboardSummary ? fmt(dashboardSummary.scheduled_runs) : "-"
              }
              hint={t("usage.kpi.scheduledHint")}
            />
            <StatMetric
              icon={Wrench}
              label={t("usage.kpi.toolCallsLabel")}
              value={
                dashboardSummary ? fmt(dashboardSummary.total_tool_calls) : "-"
              }
              hint={t("usage.kpi.toolCallsHint")}
            />
            <StatMetric
              icon={DatabaseZap}
              label={t("usage.cacheHitRate")}
              value={cacheHitLabel}
              hint={t("usage.cacheTokens", {
                count: fmt(stats.total_cache_read_tokens),
              })}
            />
            <StatMetric
              icon={ArrowUpFromLine}
              label={t("usage.totalTokens")}
              value={fmt(stats.total_tokens)}
              hint={t("usage.kpi.tokensHint", {
                in: fmt(stats.total_input_tokens),
                out: fmt(stats.total_output_tokens),
              })}
            />
          </div>
        </div>
      )}

      {/* Dashboard sections */}
      <div className="mx-auto w-full flex-1 px-4 pt-3 pb-5 sm:px-6 sm:pt-4 sm:pb-6 lg:px-8">
        {/* Section header */}
        {dashboard && (
          <div className="mb-5 flex items-center gap-3 sm:mb-6 sm:gap-3.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--usage-icon-bg)] text-[var(--theme-primary)] sm:h-9 sm:w-9">
              <LayoutDashboard size={15} strokeWidth={2} />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-[13px] font-bold tracking-tight text-theme-text sm:text-sm">
                {dashboardTitle}
              </h2>
              <p className="mt-0.5 truncate text-[10px] leading-snug text-theme-text-tertiary sm:text-[11px]">
                {dashboardSubtitle}
              </p>
            </div>
          </div>
        )}

        {/* Insights */}
        {dashboard && (
          <div className="mb-5 sm:mb-6">
            <InsightStrip dashboard={dashboard} />
          </div>
        )}

        {/* Chart + Rankings */}
        {dashboard && (
          <div className="mb-5 grid gap-5 sm:mb-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(24rem,0.95fr)]">
            <MiniTrend points={dashboard.daily} />
            <div className="grid gap-5 xl:grid-cols-1">
              <RankingList
                title={personaRankingTitle}
                icon={BadgeCheck}
                items={
                  dashboard.top_personas.length
                    ? dashboard.top_personas
                    : dashboard.top_agents
                }
                emptyLabel={t("usage.empty.persona")}
              />
              <RankingList
                title={teamRankingTitle}
                icon={Users}
                items={dashboard.top_teams}
                emptyLabel={t("usage.empty.team")}
              />
            </div>
          </div>
        )}

        {/* Bottom grid */}
        {dashboard && (
          <div className="mb-5 grid grid-cols-1 gap-5 sm:mb-6 sm:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-4">
            <RankingList
              title={agentRankingTitle}
              icon={Bot}
              items={dashboard.top_agents}
              emptyLabel={t("usage.empty.agent")}
            />
            <RankingList
              title={modelRankingTitle}
              icon={DatabaseZap}
              items={dashboard.top_models}
              emptyLabel={t("usage.empty.model")}
            />
            {isAdmin && (
              <RankingList
                title={t("usage.ranking.userAdmin")}
                icon={UserRound}
                items={dashboard.top_users}
                emptyLabel={t("usage.empty.user")}
              />
            )}
            <DistributionList
              title={sourceDistributionTitle}
              icon={PieChart}
              items={dashboard.sources}
              total={dashboard.summary.total_requests}
              emptyLabel={t("usage.empty.source")}
            />
          </div>
        )}

        {/* Triggers */}
        {isAdmin && dashboard && dashboard.triggers.length > 0 && (
          <div className="mb-5 sm:mb-6">
            <DistributionList
              title={t("usage.ranking.triggers")}
              icon={CalendarClock}
              items={dashboard.triggers}
              total={dashboard.summary.scheduled_runs}
              emptyLabel={t("usage.empty.triggers")}
            />
          </div>
        )}

        {/* Refreshing pill */}
        {isLoading && logs.length > 0 && (
          <div className="pointer-events-none mb-2 flex justify-center">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--glass-bg-card)] px-3 py-1 text-[11px] text-theme-text-tertiary shadow-sm ring-1 ring-inset ring-[var(--theme-border-faint)]">
              <RefreshCw size={10} className="animate-spin" />
              {t("usage.refreshing")}
            </div>
          </div>
        )}

        {/* Logs */}
        <UsageLogsTable
          logs={logs}
          total={total}
          page={page}
          pageSize={pageSize}
          isAdmin={isAdmin}
          hasAnyCache={hasAnyCache}
        />
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="glass-divider px-4 py-2.5 sm:px-6 sm:py-3 lg:px-8">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            itemLabel={t("usage.logItems")}
            onChange={(p) => setSkip((p - 1) * pageSize)}
          />
        </div>
      )}
    </div>
  );
}

export default UsagePanel;
