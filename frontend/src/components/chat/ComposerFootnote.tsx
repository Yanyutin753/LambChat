import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useFxRates } from "../../hooks/useFxRates";
import { useTodayUsageCost } from "../../hooks/useTodayUsageCost";
import { buildDailyUsageAmount } from "./dailyUsageLabel";

/** 输入框下方脚注：AI 免责声明 + 当日用量金额（统计未就绪时仅显示声明）。 */
export function ComposerFootnote({
  isLoading = false,
}: {
  isLoading?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const fxRates = useFxRates();
  const { stats, refresh } = useTodayUsageCost();

  // 一轮对话运行结束后刷新当日金额
  const prevLoading = useRef(isLoading);
  useEffect(() => {
    if (prevLoading.current && !isLoading) refresh();
    prevLoading.current = isLoading;
  }, [isLoading, refresh]);

  const amount = buildDailyUsageAmount(stats, {
    language: i18n.language,
    rates: fxRates,
  });

  return (
    <div className="pointer-events-none mx-auto w-full max-w-4xl text-center lg:max-w-5xl xl:max-w-6xl">
      <span
        className="text-xs leading-none"
        style={{ color: "var(--theme-text-tertiary)" }}
      >
        {t("chat.aiDisclaimer")}
        {amount !== null && (
          <>
            <span className="mx-1.5 opacity-40">·</span>
            <span>{t("usage.todayCost", { amount })}</span>
          </>
        )}
      </span>
    </div>
  );
}
