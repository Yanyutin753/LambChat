import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, ChevronRight } from "lucide-react";
import { useFxRates } from "../../hooks/useFxRates";
import { useTodayUsageCost } from "../../hooks/useTodayUsageCost";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import {
  buildTodayUsageSnapshot,
  type TokenShareKey,
} from "./todayUsageSnapshot";
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

/** 输入框工具栏的当日用量入口：金额 chip + 点击弹出用量卡（Token 构成 / 缓存命中 / 详情入口）。 */
export function ComposerUsageChip() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const fxRates = useFxRates();
  const { stats } = useTodayUsageCost();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const snapshot = buildTodayUsageSnapshot(stats, {
    language: i18n.language,
    rates: fxRates,
  });

  const position = useStickyDropdownPosition(triggerRef, open, (rect) =>
    getUsagePopoverPosition({
      triggerRect: rect,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    }),
  );

  // 点击浮层外关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      const popover = document.getElementById("composer-usage-popover");
      if (popover?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Escape 关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  if (!snapshot) return null;

  const label = t("usage.todayShort", { amount: snapshot.amount });
  const visibleShares = snapshot.shares.filter((s) => s.share > 0);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        className="chat-tool-btn shrink-0"
        title={label}
      >
        <span className="flex items-center gap-2">
          <Activity size={16} className="shrink-0" />
          <span className="hidden sm:inline max-w-40 sm:max-w-52 truncate text-base font-semibold text-blue-600 dark:text-blue-400 font-serif tabular-nums">
            {snapshot.amount}
          </span>
        </span>
      </button>

      {open &&
        createPortal(
          <div
            id="composer-usage-popover"
            className="feature-menu-dropdown"
            style={position}
          >
            {/* ── 头部：今日用量 + 金额 ── */}
            <div className="flex items-center justify-between gap-3 px-3 pt-3">
              <span
                className="text-xs font-medium"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("usage.todaySpend")}
              </span>
              <span
                className="font-serif text-sm font-semibold tabular-nums"
                style={{ color: "var(--theme-text)" }}
              >
                {snapshot.amount}
              </span>
            </div>

            {/* ── Token 构成 ── */}
            <div className="px-3 pb-2 pt-2.5">
              <div
                className="mb-1.5 text-11"
                style={{ color: "var(--theme-text-tertiary)" }}
              >
                {t("usage.tokenMix")}
              </div>
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
                  <div key={s.key} className="flex items-center gap-2 text-xs">
                    <span
                      className={`size-1.5 shrink-0 rounded-full ${
                        SEGMENT_STYLE[s.key].color
                      }`}
                    />
                    <span
                      className="flex-1"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {t(SEGMENT_STYLE[s.key].labelKey)}
                    </span>
                    <span
                      className="tabular-nums"
                      style={{ color: "var(--theme-text-tertiary)" }}
                    >
                      {s.tokens.toLocaleString()}
                    </span>
                    <span
                      className="w-9 text-right tabular-nums"
                      style={{ color: "var(--theme-text-tertiary)" }}
                    >
                      {Math.round(s.share)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* ── 请求数 / 缓存命中 ── */}
            <div
              className="flex items-center justify-between gap-2 border-t px-3 py-2 text-xs"
              style={{ borderColor: "var(--theme-border)" }}
            >
              <span style={{ color: "var(--theme-text-secondary)" }}>
                {t("usage.requestsCount")}
                <span
                  className="ml-1.5 font-medium tabular-nums"
                  style={{ color: "var(--theme-text)" }}
                >
                  {snapshot.requests}
                </span>
              </span>
              <span style={{ color: "var(--theme-text-secondary)" }}>
                {t("usage.cacheHitRate")}
                <span
                  className="ml-1.5 font-medium tabular-nums"
                  style={{ color: "var(--theme-text)" }}
                >
                  {snapshot.cacheHitRate === null
                    ? "—"
                    : `${(snapshot.cacheHitRate * 100).toFixed(1)}%`}
                </span>
              </span>
            </div>

            {/* ── 详情入口 ── */}
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate("/usage");
              }}
              className="flex w-full cursor-pointer items-center justify-between border-t px-3 py-2 text-xs transition-colors"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text-secondary)",
              }}
            >
              {t("usage.viewDetails")}
              <ChevronRight size={14} />
            </button>
          </div>,
          document.body,
        )}
    </>
  );
}
