import { ResetCardHistory } from "./ResetCardHistory";
import { InteractiveIcon } from "../common/InteractiveIcon";
import { Button } from "../common/ui/Button";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, ChevronRight } from "lucide-react";
import { useFxRates } from "../../hooks/useFxRates";
import {
  TODAY_USAGE_REFRESH_EVENT,
  useTodayUsageCost,
} from "../../hooks/useTodayUsageCost";
import {
  parseUsageQuota,
  canRedeemResetCard,
  usageApi,
  type UsageQuota,
  type UsageResetCredit,
} from "../../services/api/usage";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import {
  buildTodayUsageSnapshot,
  type TokenShareKey,
} from "./todayUsageSnapshot";
import { historicalEstimateHint, usageCostOptions } from "../../utils/currency";
import { getUsagePopoverPosition } from "./usagePopoverPosition";

const SEGMENT_STYLE: Record<
  TokenShareKey,
  { color: string; labelKey: string }
> = {
  input: {
    color: "bg-amber-400 dark:bg-amber-500",
    labelKey: "usage.tokensInput",
  },
  output: {
    color: "bg-orange-500 dark:bg-orange-400",
    labelKey: "usage.tokensOutput",
  },
  cacheWrite: {
    color: "bg-stone-400 dark:bg-stone-600",
    labelKey: "usage.cacheWrite",
  },
  cacheRead: {
    color: "bg-emerald-500 dark:bg-emerald-400",
    labelKey: "usage.cacheRead",
  },
};

/** 页头的当日用量入口：金额 chip + 点击弹出用量卡（Token 构成 / 缓存命中 / 详情入口）。 */
export function ComposerUsageChip({
  embedded = false,
}: {
  embedded?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const fxRates = useFxRates();
  const { stats } = useTodayUsageCost();
  const [quota, setQuota] = useState<UsageQuota | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(true);
  const [quotaError, setQuotaError] = useState(false);
  const [open, setOpen] = useState(false);
  const [redeeming, setRedeeming] = useState(false);
  const [confirmCredit, setConfirmCredit] = useState<UsageResetCredit | null>(
    null,
  );
  const [resetNotice, setResetNotice] = useState("");
  const [resetError, setResetError] = useState(false);
  const resetOperation = useRef<{ key: string; creditId: string } | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const refreshQuotaRef = useRef<(() => void) | null>(null);
  const refreshedDeadlines = useRef(new Set<number>());

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let pending = false;
    let requestController: AbortController | null = null;
    const fetchQuota = async () => {
      if (!active) return;
      if (inFlight) {
        pending = true;
        return;
      }
      inFlight = true;
      const controller = new AbortController();
      requestController = controller;
      let timeout: number | undefined;
      let onAbort: (() => void) | undefined;
      let succeeded = false;
      setQuotaLoading(true);
      try {
        // Bound token refresh too; abort alone cannot settle a stalled auth promise.
        const deadline = new Promise<never>((_, reject) => {
          onAbort = () =>
            reject(new DOMException("Quota request aborted", "AbortError"));
          controller.signal.addEventListener("abort", onAbort, { once: true });
          timeout = window.setTimeout(() => controller.abort(), 15_000);
        });
        const data = parseUsageQuota(
          await Promise.race([usageApi.getQuota(controller.signal), deadline]),
        );
        if (active) {
          setQuota(data);
          setQuotaError(false);
          succeeded = true;
        }
      } catch {
        if (active) setQuotaError(true);
      } finally {
        window.clearTimeout(timeout);
        if (onAbort) controller.signal.removeEventListener("abort", onAbort);
        requestController = null;
        inFlight = false;
        if (active) {
          setQuotaLoading(false);
          const refreshAgain = pending && succeeded;
          pending = false;
          if (refreshAgain) void fetchQuota();
        }
      }
    };
    refreshQuotaRef.current = fetchQuota;
    void fetchQuota();
    const timer = window.setInterval(fetchQuota, 5 * 60 * 1000);
    window.addEventListener(TODAY_USAGE_REFRESH_EVENT, fetchQuota);
    return () => {
      active = false;
      requestController?.abort();
      refreshQuotaRef.current = null;
      window.clearInterval(timer);
      window.removeEventListener(TODAY_USAGE_REFRESH_EVENT, fetchQuota);
    };
  }, []);

  useEffect(() => {
    if (!quota) return;
    const deadlines = [
      quota.five_hour.reset_at,
      quota.weekly.reset_at,
      ...(quota.reset_credits?.credits.map((card) => card.expires_at) ?? []),
    ]
      .filter((value): value is string => value !== null)
      .map((value) => Date.parse(value));
    const now = Date.now();
    const missed = deadlines.some(
      (value) => value <= now && !refreshedDeadlines.current.has(value),
    );
    const next = missed
      ? now
      : Math.min(...deadlines.filter((value) => value > now));
    if (!Number.isFinite(next)) return;
    const timer = window.setTimeout(
      () => {
        refreshedDeadlines.current = new Set(
          deadlines.filter((value) => value <= Date.now()),
        );
        refreshQuotaRef.current?.();
      },
      Math.min(next - Date.now() + 100, 2_147_483_647),
    );
    return () => window.clearTimeout(timer);
  }, [quota]);

  // 快照包含 Intl.NumberFormat 构造，只在用量或语言变化时重算。
  const snapshot = useMemo(
    () =>
      buildTodayUsageSnapshot(stats, {
        language: i18n.language,
        rates: fxRates,
      }),
    [stats, fxRates, i18n.language],
  );

  const position = useStickyDropdownPosition(triggerRef, open, (rect) =>
    getUsagePopoverPosition({
      triggerRect: rect,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    }),
  );

  // 点击浮层外关闭
  useEffect(() => {
    if (!open || confirmCredit) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      const popover = document.getElementById("composer-usage-popover");
      if (popover?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, confirmCredit]);

  // Escape 关闭
  useEffect(() => {
    if (!open || confirmCredit) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, confirmCredit]);

  const estimateHint = stats
    ? historicalEstimateHint(
        {
          ...usageCostOptions(stats),
          language: i18n.language,
          rates: fxRates,
        },
        t("usage.historicalEstimate"),
      )
    : undefined;
  const credits = quota?.reset_credits;
  const resetChoices = [
    ...new Set(credits?.credits.map((card) => card.window)),
  ].map(
    (window) =>
      credits!.credits
        .filter((card) => card.window === window)
        .sort((a, b) => Date.parse(a.expires_at) - Date.parse(b.expires_at))[0],
  );
  const redeemCard = async (credit: Pick<UsageResetCredit, "id">) => {
    if (redeeming) return;
    setRedeeming(true);
    setResetNotice("");
    setResetError(false);
    const operation = (resetOperation.current ??= {
      key: crypto.randomUUID(),
      creditId: credit.id,
    });
    try {
      const result = await usageApi.consumeResetCard(
        operation.key,
        operation.creditId,
      );
      resetOperation.current = null;
      setResetNotice(
        t(
          result.outcome === "reset"
            ? "usage.resetSuccess"
            : result.outcome === "alreadyRedeemed"
              ? "usage.resetAlreadyRedeemed"
              : result.outcome === "noCredit"
                ? "usage.resetNoCredit"
                : "usage.resetNothingToReset",
        ),
      );
    } catch (error) {
      setResetError(true);
      setResetNotice(
        error instanceof Error ? error.message : t("usage.quotaUnavailable"),
      );
    } finally {
      window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT));
      setRedeeming(false);
      setConfirmCredit(null);
    }
  };
  const label = [
    t("usage.todayShort", { amount: snapshot?.amount ?? "—" }),
    estimateHint,
  ]
    .filter(Boolean)
    .join(" · ");
  const visibleShares = snapshot?.sharesKnown
    ? snapshot.shares.filter((s) => s.share > 0)
    : [];

  const content = (
    <div
      id={embedded ? undefined : "composer-usage-popover"}
      className={
        embedded
          ? "font-serif"
          : "feature-menu-dropdown font-serif overflow-y-auto"
      }
      style={embedded ? undefined : { ...position, paddingInline: "1.125rem" }}
    >
      {/* ── 头部：今日用量 + 金额 ── */}
      <div className="flex items-baseline justify-between gap-3 pb-3 pt-4">
        <span
          className="text-12 font-medium"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {t("usage.todaySpend")}
        </span>
        <span
          className="font-serif text-14 font-medium leading-5 tabular-nums"
          style={{ color: "var(--theme-text)" }}
        >
          {snapshot?.amount ?? "—"}
        </span>
      </div>

      {estimateHint && (
        <p className="pt-2 text-11 text-theme-text-muted">{estimateHint}</p>
      )}

      <section
        className="space-y-3 border-t py-3 font-serif"
        style={{ borderColor: "var(--theme-border)" }}
        aria-busy={quotaLoading}
        aria-label={t("usage.quotaTitle")}
      >
        <h3 className="text-13 font-semibold text-theme-text">
          {t("usage.quotaTitle")}
        </h3>
        {quotaError && (
          <div className="flex items-center justify-between gap-3">
            <p role="status" className="text-12 text-theme-text-muted">
              {t("usage.quotaUnavailable")}
            </p>
            <Button
              size="sm"
              variant="ghost"
              disabled={quotaLoading}
              onClick={() =>
                window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT))
              }
            >
              {t("common.retry")}
            </Button>
          </div>
        )}
        {!quota ? (
          !quotaError && (
            <p role="status" className="text-12 text-theme-text-muted">
              {t("usage.quotaLoading")}
            </p>
          )
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {(["five_hour", "weekly"] as const).map((period) => {
              const window = quota[period];
              const periodLabel = t(
                period === "five_hour"
                  ? "usage.quotaFiveHour"
                  : "usage.quotaWeekly",
              );
              const percent =
                window.limit_usd === null
                  ? 100
                  : window.remaining_usd === null
                    ? null
                    : window.limit_usd === 0
                      ? 0
                      : Math.max(
                          0,
                          Math.min(
                            100,
                            (window.remaining_usd / window.limit_usd) * 100,
                          ),
                        );
              const roundedPercent =
                percent === null ? null : Number(percent.toFixed(1));
              const percentLabel =
                roundedPercent === null
                  ? "—"
                  : roundedPercent === 100 &&
                      window.used_usd > 0 &&
                      window.limit_usd !== null
                    ? "<100%"
                    : roundedPercent === 0 && percent !== null && percent > 0
                      ? ">0%"
                      : `${roundedPercent.toLocaleString(i18n.language)}%`;
              const status =
                window.limit_usd === null
                  ? t("usage.quotaUnlimited")
                  : undefined;
              return (
                <div
                  key={period}
                  data-period={period}
                  className="min-w-0 space-y-1.5 text-12"
                >
                  <div className="flex min-h-5 flex-wrap items-center gap-x-1.5 gap-y-1 font-medium text-theme-text-secondary">
                    <span>{periodLabel}</span>
                    {credits &&
                      credits.available_count > 0 &&
                      resetChoices
                        .filter(
                          (card) =>
                            card.window === period ||
                            (!card.window && period === "five_hour"),
                        )
                        .map((card) => {
                          const count = credits.credits.filter(
                            (credit) => credit.window === card.window,
                          ).length;
                          const action =
                            card.window === "weekly"
                              ? "usage.useWeeklyCard"
                              : card.window === "five_hour"
                                ? "usage.useFiveHourCard"
                                : "usage.useResetCard";
                          return (
                            <Button
                              key={card.window ?? "legacy"}
                              size="sm"
                              className="usage-quota-reset"
                              aria-label={`${t(action)} ${count}`}
                              title={t("usage.resetCardsAvailable", { count })}
                              disabled={
                                redeeming ||
                                quotaLoading ||
                                quotaError ||
                                !canRedeemResetCard(quota, card.window) ||
                                (resetOperation.current !== null &&
                                  resetOperation.current.creditId !== card.id)
                              }
                              loading={redeeming}
                              onClick={() => setConfirmCredit(card)}
                            >
                              {t("common.reset")} {count}
                            </Button>
                          );
                        })}
                  </div>
                  <div className="flex min-h-5 flex-wrap items-baseline gap-x-1 tabular-nums">
                    <span className="text-13 font-medium text-theme-text">
                      {percentLabel}
                    </span>
                    {window.reset_at && (
                      <span className="whitespace-nowrap text-11 text-theme-text-muted">
                        <span aria-hidden="true">· </span>
                        <time
                          dateTime={window.reset_at}
                          title={`${t("usage.quotaResets")} (${
                            quota.timezone
                          })`}
                        >
                          {new Intl.DateTimeFormat(i18n.language, {
                            timeZone: quota.timezone,
                            hour:
                              period === "five_hour" ? "2-digit" : undefined,
                            minute:
                              period === "five_hour" ? "2-digit" : undefined,
                            month: period === "weekly" ? "short" : undefined,
                            day: period === "weekly" ? "numeric" : undefined,
                          }).format(new Date(window.reset_at))}
                        </time>
                      </span>
                    )}
                  </div>
                  <progress
                    className="usage-quota-progress block h-1.5 w-full"
                    value={percent ?? undefined}
                    max={100}
                    aria-label={periodLabel}
                    aria-valuetext={status}
                    title={status}
                  />
                  {window.blocked && (
                    <p className="text-11 text-theme-text-secondary">
                      {t(
                        window.used_usd < (window.limit_usd ?? Infinity)
                          ? "usage.quotaReservedBlocked"
                          : "usage.quotaBlocked",
                      )}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
      {resetNotice && (
        <p
          role={resetError ? "alert" : "status"}
          className="py-2 text-12 text-theme-text-secondary"
        >
          {resetNotice}
        </p>
      )}
      {resetError && resetOperation.current && (
        <Button
          size="sm"
          variant="ghost"
          disabled={redeeming}
          onClick={() => {
            const operation = resetOperation.current;
            if (operation) void redeemCard({ id: operation.creditId });
          }}
        >
          {t("common.retry")}
        </Button>
      )}
      {embedded && quota && credits && (
        <section
          aria-label={t("usage.resetCardsTitle")}
          className="space-y-2 border-t border-theme-border py-3"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-13 font-semibold text-theme-text">
              {t("usage.resetCardsTitle")}
            </h3>
            <span className="text-12 text-theme-text-muted">
              {t("usage.resetCardsAvailable", {
                count: credits.available_count,
              })}
            </span>
          </div>
          {credits.credits.length > 0 ? (
            <>
              <p className="text-12 text-theme-text-secondary">
                {t("usage.resetCardUsageHint")}
              </p>
              <div
                className="ai-data-table ai-data-table__scroll overflow-x-auto font-sans"
                tabIndex={0}
              >
                <table
                  aria-label={t("usage.resetCardsTitle")}
                  className="ai-data-table__table whitespace-nowrap"
                >
                  <thead className="ai-data-table__head">
                    <tr className="ai-data-table__row">
                      {[
                        "usage.bulkCardsType",
                        "usage.resetCardGranted",
                        "usage.resetCardExpires",
                      ].map((key) => (
                        <th
                          key={key}
                          scope="col"
                          className="ai-data-table__header-cell"
                        >
                          {t(key)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="ai-data-table__body">
                    {[...credits.credits]
                      .sort(
                        (a, b) =>
                          Date.parse(a.expires_at) - Date.parse(b.expires_at),
                      )
                      .map((card) => (
                        <tr key={card.id} className="ai-data-table__row">
                          <td className="ai-data-table__cell">
                            {t(
                              card.window === "five_hour"
                                ? "usage.fiveHourCard"
                                : card.window === "weekly"
                                  ? "usage.weeklyCard"
                                  : "usage.legacyResetCard",
                            )}
                          </td>
                          {(["granted_at", "expires_at"] as const).map(
                            (field) => (
                              <td key={field} className="ai-data-table__cell">
                                <time
                                  dateTime={card[field]}
                                  className="tabular-nums"
                                >
                                  {new Date(card[field]).toLocaleString(
                                    i18n.language,
                                    {
                                      timeZone: quota.timezone,
                                      year: "numeric",
                                      month: "short",
                                      day: "numeric",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    },
                                  )}
                                </time>
                              </td>
                            ),
                          )}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {credits.credits.some((card) => !card.window) && (
                <p className="text-12 text-theme-text-muted">
                  {t("usage.resetLegacyCardHint")}
                </p>
              )}
            </>
          ) : (
            <p className="text-12 text-theme-text-muted">
              {t("usage.resetCardsEmpty")}
            </p>
          )}
        </section>
      )}

      {embedded && quota && credits?.history && (
        <ResetCardHistory history={credits.history} timezone={quota.timezone} />
      )}

      {snapshot && (
        <details className="group border-t border-theme-border">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3 text-12 text-theme-text-secondary">
            <span>{t("usage.tokenMix")}</span>
            <ChevronRight
              size={14}
              className="transition-transform group-open:rotate-90 motion-reduce:transition-none"
            />
          </summary>
          {/* ── Token 构成 ── */}
          <div className="pb-2 pt-2.5">
            <div
              className="flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full"
              style={{ background: "var(--theme-border)" }}
              role="presentation"
            >
              {visibleShares.map((s) => (
                <div
                  key={s.key}
                  className={SEGMENT_STYLE[s.key].color}
                  style={{ width: `${s.share}%` }}
                />
              ))}
            </div>
            <div className="mt-2 flex flex-col gap-1">
              {snapshot.shares.map((s) => (
                <div
                  key={s.key}
                  className="grid grid-cols-[0.375rem_minmax(0,1fr)_auto_2.25rem] items-baseline gap-2 text-12"
                >
                  <span
                    className={`size-1.5 shrink-0 self-center rounded-full ${
                      SEGMENT_STYLE[s.key].color
                    }`}
                  />
                  <span
                    className="min-w-0"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {t(
                      s.reported
                        ? "usage.tokensInputReported"
                        : SEGMENT_STYLE[s.key].labelKey,
                    )}
                  </span>
                  <span
                    className="text-right tabular-nums"
                    style={{ color: "var(--theme-text-tertiary)" }}
                  >
                    {s.tokens === null ? "—" : s.tokens.toLocaleString()}
                  </span>
                  <span
                    className="w-9 text-right tabular-nums"
                    style={{ color: "var(--theme-text-tertiary)" }}
                  >
                    {snapshot.sharesKnown ? `${Math.round(s.share)}%` : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* ── 请求数 / 缓存命中 ── */}
          <div
            className="flex items-baseline justify-between gap-2 border-t py-2 text-12"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <span
              className="inline-flex items-baseline gap-1.5"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {t("usage.requestsCount")}
              <span
                className="font-medium tabular-nums"
                style={{ color: "var(--theme-text)" }}
              >
                {snapshot.requests}
              </span>
            </span>
            <span
              className="inline-flex items-baseline gap-1.5"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {t("usage.cacheHitRate")}
              <span
                className="font-medium tabular-nums"
                style={{ color: "var(--theme-text)" }}
              >
                {snapshot.cacheHitRate === null
                  ? "—"
                  : `${(snapshot.cacheHitRate * 100).toFixed(1)}%`}
              </span>
            </span>
          </div>
        </details>
      )}

      {/* ── 详情入口 ── */}
      {!embedded && (
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            navigate("/usage");
          }}
          className="flex w-full cursor-pointer items-center justify-between border-t py-2 text-12 transition-colors"
          style={{
            borderColor: "var(--theme-border)",
            color: "var(--theme-text-secondary)",
          }}
        >
          {t("usage.viewDetails")}
          <InteractiveIcon>
            <ChevronRight size={14} />
          </InteractiveIcon>
        </button>
      )}
    </div>
  );

  return (
    <>
      {!embedded && (
        <button
          ref={triggerRef}
          type="button"
          onClick={() => {
            if (!open) refreshQuotaRef.current?.();
            setOpen(!open);
          }}
          aria-label={label}
          aria-expanded={open}
          aria-controls={open ? "composer-usage-popover" : undefined}
          className="chat-tool-btn shrink-0"
          title={label}
        >
          <span className="flex items-center gap-2">
            <InteractiveIcon>
              <Activity size={16} className="shrink-0" />
            </InteractiveIcon>
            <span className="composer-usage-amount max-w-40 sm:max-w-52 truncate text-14 leading-5 font-medium text-theme-text-secondary font-serif tabular-nums">
              {snapshot?.amount ?? "—"}
            </span>
          </span>
        </button>
      )}
      {embedded ? content : open && createPortal(content, document.body)}
      <ConfirmDialog
        isOpen={confirmCredit !== null}
        title={t("usage.resetConfirmTitle")}
        message={t(
          confirmCredit?.window === "five_hour"
            ? "usage.resetFiveHourConfirm"
            : confirmCredit?.window === "weekly"
              ? "usage.resetWeeklyConfirm"
              : "usage.resetLegacyConfirm",
        )}
        confirmText={t("common.reset")}
        variant="warning"
        loading={redeeming}
        onConfirm={() => {
          if (confirmCredit) void redeemCard(confirmCredit);
        }}
        onCancel={() => setConfirmCredit(null)}
      />
    </>
  );
}
