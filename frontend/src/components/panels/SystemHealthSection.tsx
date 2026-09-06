import { useState, useEffect, useCallback } from "react";
import type { TFunction } from "i18next";
import {
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  MemoryStick,
  Cpu,
  FileText,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { StatusBadge } from "../common/StatusBadge";
import type { StatusColor } from "../common/StatusBadge";
import {
  healthApi,
  type MemoryDiagnostics,
  type MemoryHighlight,
  type MemoryOverview,
} from "../../services/api/health";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";

const HEALTH_STATUS_COLOR: Record<string, StatusColor> = {
  stable: "green",
  suspected_leak: "red",
};

const HEALTH_STATUS_LABEL: Record<string, string> = {
  stable: "systemHealth.stable",
  suspected_leak: "systemHealth.suspectedLeak",
  unavailable: "systemHealth.unavailable",
};

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number | null;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-2">
      <Icon size={16} className="shrink-0 text-stone-400 dark:text-stone-500" />
      <div className="min-w-0">
        <p className="text-11 text-stone-400 dark:text-stone-500">{label}</p>
        <p className="text-sm font-medium tabular-nums text-stone-700 dark:text-stone-200">
          {value ?? "-"}
        </p>
      </div>
    </div>
  );
}

function renderHighlightText(
  highlight: MemoryHighlight,
  overview: MemoryOverview,
  t: TFunction,
) {
  switch (highlight.kind) {
    case "status":
      if (highlight.status === "suspected_leak") {
        return t("systemHealth.statusSuspectedLeak", {
          rss: overview.rss ?? "-",
          growth: overview.growth ?? "-",
        });
      }
      return t("systemHealth.statusStable", {
        rss: overview.rss ?? "-",
        growth: overview.growth ?? "-",
      });
    case "unavailable":
      return t(
        "systemHealth.statusUnavailableReason",
        `Memory monitoring is unavailable: ${highlight.reason}`,
      );
    case "top_growth":
      return t("systemHealth.highlightTopGrowth", {
        location: highlight.location,
        size_diff: highlight.size_diff ?? "-",
      });
    case "top_allocation":
      return t("systemHealth.highlightTopAllocation", {
        location: highlight.location,
        size: highlight.size ?? "-",
      });
    case "top_object_type":
      return t("systemHealth.highlightTopObjectType", {
        type: highlight.type,
        count: highlight.count,
      });
  }
}

export function SystemHealthSection() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [diagnostics, setDiagnostics] = useState<MemoryDiagnostics | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const canView = hasPermission(Permission.SETTINGS_MANAGE);

  const fetchDiagnostics = useCallback(
    async (refresh = false) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await healthApi.getMemoryDiagnostics(refresh);
        setDiagnostics(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t("systemHealth.fetchFailed"),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (canView) {
      fetchDiagnostics(false);
    }
  }, [canView, fetchDiagnostics]);

  if (!canView) return null;

  const overview = diagnostics?.overview;

  return (
    <div className="mb-4 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)]">
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 select-none"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
      >
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-100 to-cyan-50 text-blue-600 dark:from-blue-900/50 dark:to-cyan-900/30 dark:text-blue-400">
            <Activity size={16} />
          </div>
          <div>
            <span className="text-sm font-semibold font-serif text-stone-800 dark:text-stone-100">
              {t("systemHealth.title", "System Health")}
            </span>
            {overview && (
              <div className="mt-0.5">
                <StatusBadge
                  color={HEALTH_STATUS_COLOR[overview.status] ?? "stone"}
                  label={t(
                    HEALTH_STATUS_LABEL[overview.status] ??
                      "systemHealth.unavailable",
                  )}
                  size="sm"
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              fetchDiagnostics(true);
            }}
            disabled={isLoading}
            className="rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-[var(--glass-bg)] hover:text-stone-600 disabled:opacity-50 dark:text-stone-500 dark:hover:text-stone-300"
          >
            <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
          </button>
          {expanded ? (
            <ChevronUp size={16} className="text-stone-400" />
          ) : (
            <ChevronDown size={16} className="text-stone-400" />
          )}
        </div>
      </div>

      {/* Collapsed summary line */}
      {!expanded && overview && (
        <div className="border-t border-[var(--glass-border)] px-4 py-2">
          <p className="text-xs text-stone-500 dark:text-stone-400">
            RSS: {overview.rss ?? "-"} &middot;{" "}
            {t("systemHealth.threads", "Threads")}: {overview.threads ?? "-"}{" "}
            &middot; {t("systemHealth.openFiles", "Files")}:{" "}
            {overview.open_files ?? "-"}
          </p>
        </div>
      )}

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[var(--glass-border)] px-4 py-3">
          {isLoading && !diagnostics && (
            <div className="flex items-center justify-center py-6">
              <LoadingSpinner size="sm" />
            </div>
          )}

          {error && (
            <p className="py-2 text-center text-sm text-red-500">{error}</p>
          )}

          {diagnostics && overview && (
            <div className="space-y-4">
              {/* Metrics grid */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <MetricCard
                  icon={MemoryStick}
                  label={t("systemHealth.rss", "RSS")}
                  value={overview.rss}
                />
                <MetricCard
                  icon={TrendingUp}
                  label={t("systemHealth.growth", "Growth")}
                  value={overview.growth}
                />
                <MetricCard
                  icon={Cpu}
                  label={t("systemHealth.threads", "Threads")}
                  value={overview.threads}
                />
                <MetricCard
                  icon={FileText}
                  label={t("systemHealth.openFiles", "Open Files")}
                  value={overview.open_files}
                />
              </div>

              {/* Highlights */}
              {diagnostics.highlights.length > 0 && (
                <div className="space-y-1">
                  {diagnostics.highlights.map((highlight, i) => (
                    <p
                      key={i}
                      className={`text-xs ${
                        highlight.kind === "status" &&
                        highlight.status === "suspected_leak"
                          ? "text-red-600 dark:text-red-400"
                          : "text-stone-500 dark:text-stone-400"
                      }`}
                    >
                      {renderHighlightText(highlight, overview, t)}
                    </p>
                  ))}
                </div>
              )}

              {/* Top growth allocations */}
              {diagnostics.top_growth.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-stone-400">
                    {t("systemHealth.topGrowth", "Top Growth")}
                  </h4>
                  <div className="space-y-1">
                    {diagnostics.top_growth.map((row, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md bg-[var(--glass-bg)] px-2.5 py-1.5 text-xs"
                      >
                        <code className="max-w-[70%] truncate text-stone-600 dark:text-stone-300">
                          {row.location}
                        </code>
                        <span className="shrink-0 font-medium tabular-nums text-orange-600 dark:text-orange-400">
                          +{row.size_diff}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top allocations */}
              {diagnostics.top_allocations.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-stone-400">
                    {t("systemHealth.topAllocations", "Top Allocations")}
                  </h4>
                  <div className="space-y-1">
                    {diagnostics.top_allocations.map((row, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md bg-[var(--glass-bg)] px-2.5 py-1.5 text-xs"
                      >
                        <code className="max-w-[70%] truncate text-stone-600 dark:text-stone-300">
                          {row.location}
                        </code>
                        <span className="shrink-0 font-medium tabular-nums text-blue-600 dark:text-blue-400">
                          {row.size} ({row.count}x)
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top object types */}
              {diagnostics.top_objects.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-stone-400">
                    {t("systemHealth.topObjects", "Top Object Types")}
                  </h4>
                  <div className="space-y-1">
                    {diagnostics.top_objects.map((row, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md bg-[var(--glass-bg)] px-2.5 py-1.5 text-xs"
                      >
                        <code className="text-stone-600 dark:text-stone-300">
                          {row.type}
                        </code>
                        <span className="shrink-0 font-medium tabular-nums text-stone-500 dark:text-stone-400">
                          {row.count.toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {overview.last_sample_at && (
                <p className="text-11 text-stone-400 dark:text-stone-500">
                  {t("systemHealth.lastSample", "Last sample")}:{" "}
                  {overview.last_sample_at}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
