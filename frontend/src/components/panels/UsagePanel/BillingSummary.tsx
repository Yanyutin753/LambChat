import { useTranslation } from "react-i18next";
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { useFxRates } from "../../../hooks/useFxRates";
import {
  formatCostUsd,
  historicalEstimateHint,
  isCostAmount,
  usageCostOptions,
} from "../../../utils/currency";
import type { UsageStats } from "../../../types/usage";

export function BillingSummary({ stats }: { stats: UsageStats }) {
  const { t, i18n } = useTranslation();
  const rates = useFxRates();
  const options = {
    language: i18n.language,
    rates,
    ...usageCostOptions(stats),
  };
  const categories = [
    {
      key: "priced",
      count: stats.priced_requests,
      color: "var(--theme-primary)",
    },
    {
      key: "partial",
      count: stats.partial_requests,
      color: "var(--usage-chart-secondary)",
    },
    {
      key: "estimated",
      count: stats.estimated_requests,
      color: "var(--theme-text-tertiary)",
    },
    {
      key: "unpriced",
      count: stats.unpriced_requests,
      color: "var(--usage-border)",
    },
  ];
  const data = Object.fromEntries(
    categories.map(({ key, count }) => [key, count ?? 0]),
  );
  const estimate = historicalEstimateHint(
    options,
    t("usage.historicalEstimate"),
  );
  return (
    <section
      aria-label={t("usage.billing.title")}
      className="mt-4 grid gap-4 border-t border-[var(--usage-border)] pt-4 sm:grid-cols-2"
    >
      <div className="min-w-0">
        <h3 className="text-13 font-semibold text-theme-text">
          {t("usage.billing.title")}
        </h3>
        <dl className="mt-2 space-y-1.5 text-12 text-theme-text-secondary">
          {(
            [
              ["confirmedAmount", stats.total_cost_usd],
              ["partialAmount", stats.partial_cost_usd],
            ] as const
          ).map(([label, amount]) => (
            <div
              key={label}
              className="flex flex-wrap justify-between gap-x-3 gap-y-1"
            >
              <dt>{t(`usage.billing.${label}`)}</dt>
              <dd className="font-semibold tabular-nums text-theme-text">
                {isCostAmount(amount) ? formatCostUsd(amount, options) : "—"}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-12 leading-relaxed text-theme-text-tertiary">
          {t("usage.billing.knownOnly")}
        </p>
        {estimate && (
          <p className="mt-1 text-12 text-theme-text-tertiary">{estimate}</p>
        )}
      </div>
      <div className="min-w-0">
        <p className="text-12 text-theme-text-secondary">
          {t("usage.billing.coverageScope")}
        </p>
        <div className="mt-2 h-3" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={[data]}
              layout="vertical"
              margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
              accessibilityLayer={false}
            >
              <XAxis type="number" hide />
              <YAxis type="category" hide />
              {categories.map(({ key, color }) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId="coverage"
                  fill={color}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-12 text-theme-text-secondary">
          {categories
            .filter(({ count }) => count !== undefined)
            .map(({ key, count, color }) => (
              <li key={key} className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 shrink-0 rounded-sm"
                  style={{ backgroundColor: color }}
                />
                {t(`usage.billing.${key}`, { count })}
              </li>
            ))}
        </ul>
      </div>
    </section>
  );
}
