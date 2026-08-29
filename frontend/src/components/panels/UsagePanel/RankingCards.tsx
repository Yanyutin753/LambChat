import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UsageRankingItem } from "../../../types/usage";
import { useFxRates } from "../../../hooks/useFxRates";
import { fmt, fmtDur, fmtCostUsd, pct } from "./formatters";

function RankBadge({ rank }: { rank: number }) {
  if (rank > 3) return null;
  const styles = [
    "bg-amber-500/15 text-amber-600 dark:text-amber-400 ring-amber-500/20",
    "bg-stone-500/10 text-stone-500 dark:text-stone-400 ring-stone-500/20",
    "bg-orange-500/10 text-orange-600 dark:text-orange-400 ring-orange-500/20",
  ];
  return (
    <span
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[9px] font-bold ring-1 ring-inset ${
        styles[rank - 1]
      }`}
    >
      {rank}
    </span>
  );
}

function CustomProgressBar({ percentage }: { percentage: number }) {
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--usage-inset-bg)]">
      <div
        className="h-full rounded-full transition-all duration-700 ease-out"
        style={{
          width: `${percentage}%`,
          background: "var(--usage-progress-fill)",
        }}
      />
    </div>
  );
}

export function RankingList({
  title,
  icon: Icon,
  items,
  emptyLabel,
  showCacheMetrics = false,
}: {
  title: string;
  icon: LucideIcon;
  items: UsageRankingItem[];
  emptyLabel: string;
  showCacheMetrics?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const fxRates = useFxRates();
  const maxTokens = Math.max(...items.map((i) => i.tokens), 1);
  return (
    <div className="usage-surface rounded-xl p-4 transition-colors duration-200 hover:border-[var(--usage-border-hover)] sm:p-5">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <Icon
          size={14}
          strokeWidth={2}
          className="shrink-0 text-theme-text-tertiary"
        />
        <h3 className="min-w-0 flex-1 truncate text-[13px] font-bold text-theme-text sm:text-sm">
          {title}
        </h3>
        {items.length > 0 && (
          <span className="shrink-0 text-[10px] tabular-nums text-theme-text-tertiary">
            {t("usage.ranking.top", { n: Math.min(items.length, 5) })}
          </span>
        )}
      </div>

      {/* Items */}
      <div className="flex flex-col gap-3">
        {items.length === 0 ? (
          <p className="py-6 text-center text-xs text-theme-text-tertiary sm:py-8">
            {emptyLabel}
          </p>
        ) : (
          items.slice(0, 5).map((item, idx) => (
            <div
              key={`${title}-${item.id}`}
              className="min-w-0 transition-transform duration-200 hover:-translate-y-px"
            >
              <div className="mb-1 flex items-center gap-1.5 sm:gap-2">
                <RankBadge rank={idx + 1} />
                <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-theme-text-secondary sm:text-xs">
                  {item.name || item.id || "-"}
                </span>
                <span className="shrink-0 text-[11px] font-bold tabular-nums text-theme-text sm:text-xs">
                  {fmt(item.tokens)}
                </span>
              </div>
              <CustomProgressBar
                percentage={Math.max(4, (item.tokens / maxTokens) * 100)}
              />
              <div className="mt-1 flex justify-between gap-2 text-[10px] text-theme-text-tertiary">
                <span>
                  {t("usage.ranking.countSuffix", { count: item.requests })}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {(item.cost_usd ?? 0) > 0 && (
                    <span className="tabular-nums">
                      {fmtCostUsd(item.cost_usd ?? 0, true, {
                        language: i18n.language,
                        rates: fxRates,
                      })}
                    </span>
                  )}
                  <span>{fmtDur(item.duration)}</span>
                </span>
              </div>
              {showCacheMetrics && (
                <div className="mt-1 flex flex-wrap justify-between gap-x-2 text-[10px] text-theme-text-tertiary">
                  <span>
                    {t("usage.cacheHitRate")}: {pct(item.cache_read_share)}
                  </span>
                  <span>
                    {t("usage.cacheRead")}: {fmt(item.cache_read_tokens)}
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function DistributionList({
  title,
  icon: Icon,
  items,
  total,
  emptyLabel,
}: {
  title: string;
  icon: LucideIcon;
  items: UsageRankingItem[];
  total: number;
  emptyLabel: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="usage-surface rounded-xl p-4 transition-colors duration-200 hover:border-[var(--usage-border-hover)] sm:p-5">
      <div className="mb-4 flex items-center gap-2">
        <Icon
          size={14}
          strokeWidth={2}
          className="shrink-0 text-theme-text-tertiary"
        />
        <h3 className="min-w-0 flex-1 truncate text-[13px] font-bold text-theme-text sm:text-sm">
          {title}
        </h3>
      </div>

      <div className="flex flex-col gap-3">
        {items.length === 0 ? (
          <p className="py-6 text-center text-xs text-theme-text-tertiary sm:py-8">
            {emptyLabel}
          </p>
        ) : (
          items.slice(0, 4).map((item) => {
            const share = total > 0 ? item.requests / total : 0;
            return (
              <div
                key={`${title}-${item.id}`}
                className="min-w-0 transition-transform duration-200 hover:-translate-y-px"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-[11px] font-medium text-theme-text-secondary sm:text-xs">
                    {item.name || item.id || "-"}
                  </span>
                  <span className="shrink-0 text-[11px] font-bold tabular-nums text-theme-text sm:text-xs">
                    {pct(share)}
                  </span>
                </div>
                <CustomProgressBar percentage={Math.max(5, share * 100)} />
                <div className="mt-1 flex justify-between text-[10px] text-theme-text-tertiary">
                  <span>
                    {t("usage.ranking.countSuffix", { count: item.requests })}
                  </span>
                  <span>
                    {t("usage.ranking.tokensValue", {
                      count: fmt(item.tokens),
                    })}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
