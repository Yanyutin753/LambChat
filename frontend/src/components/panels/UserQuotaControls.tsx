import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { TODAY_USAGE_REFRESH_EVENT } from "../../hooks/useTodayUsageCost";
import { usageApi, type UsageQuota } from "../../services/api/usage";
import { Permission } from "../../types";
import { Button } from "../common/ui/Button";

export function UserQuotaControls({ userId }: { userId: string }) {
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const allowed = hasPermission(Permission.USAGE_ADMIN);
  const [quota, setQuota] = useState<UsageQuota | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const operationKeys = useRef<Record<string, string>>({});
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setQuota(await usageApi.getUserQuota(userId));
    } catch (error) {
      setError(
        error instanceof Error ? error.message : t("usage.quotaUnavailable"),
      );
    } finally {
      setLoading(false);
    }
  }, [userId, t]);
  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  const act = async (
    action: "five_hour" | "weekly" | "issue-five_hour" | "issue-weekly",
  ) => {
    if (busy || !allowed) return;
    setBusy(true);
    setError("");
    setNotice("");
    const key = (operationKeys.current[action] ??= crypto.randomUUID());
    try {
      const result =
        action === "five_hour" || action === "weekly"
          ? await usageApi.resetUserQuota(userId, action, key)
          : await usageApi.issueResetCard(
              userId,
              key,
              action === "issue-weekly" ? "weekly" : "five_hour",
            );
      delete operationKeys.current[action];
      setNotice(
        t(
          result.outcome === "issued" || result.outcome === "alreadyIssued"
            ? "usage.resetCardIssued"
            : result.outcome === "nothingToReset"
              ? "usage.resetNothingToReset"
              : result.outcome === "alreadyRedeemed"
                ? "usage.resetAlreadyRedeemed"
                : "usage.resetSuccess",
        ),
      );
    } catch (error) {
      setError(
        error instanceof Error ? error.message : t("common.operationFailed"),
      );
    } finally {
      await load();
      window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT));
      setBusy(false);
    }
  };

  if (!allowed) return null;
  const usd = new Intl.NumberFormat(i18n.language, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 6,
  });
  return (
    <section
      className="flex min-w-0 flex-col gap-4"
      aria-label={t("usage.adminQuotaTitle")}
      aria-busy={loading || busy}
    >
      <p className="es-hint">{t("usage.adminQuotaHint")}</p>
      {loading && !quota && (
        <p role="status" className="es-hint">
          {t("usage.quotaLoading")}
        </p>
      )}
      {quota && (
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-4 rounded-lg bg-theme-bg-subtle p-3 text-13">
          {(["five_hour", "weekly"] as const).map((period) => {
            const window = quota[period];
            const eligible =
              window.limit_usd !== null &&
              window.limit_usd > 0 &&
              (window.unknown || window.used_usd > 0);
            return (
              <Fragment key={period}>
                <div className="min-w-0 space-y-1">
                  <div className="text-theme-text-secondary">
                    {t(
                      period === "five_hour"
                        ? "usage.quotaFiveHour"
                        : "usage.quotaWeekly",
                    )}
                  </div>
                  <div className="tabular-nums text-theme-text">
                    {window.limit_usd === null
                      ? t("usage.quotaUnlimited")
                      : window.remaining_usd === null
                        ? "—"
                        : `${usd.format(window.remaining_usd)} / ${usd.format(
                            window.limit_usd,
                          )}`}
                  </div>
                </div>
                <Button
                  size="sm"
                  className="max-w-40"
                  disabled={busy || loading || !eligible}
                  onClick={() => void act(period)}
                >
                  <span className="whitespace-normal">
                    {t(
                      period === "five_hour"
                        ? "usage.resetFiveHour"
                        : "usage.resetWeekly",
                    )}
                  </span>
                </Button>
              </Fragment>
            );
          })}
        </div>
      )}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          {(["five_hour", "weekly"] as const).map((window) => (
            <Button
              key={window}
              size="sm"
              disabled={busy || loading}
              onClick={() => void act(`issue-${window}`)}
            >
              {t(
                window === "five_hour"
                  ? "usage.issueFiveHourCard"
                  : "usage.issueWeeklyCard",
              )}
            </Button>
          ))}
        </div>
        <p className="es-hint">{t("usage.resetCardGrantHint")}</p>
        {quota?.reset_credits && (
          <p className="text-12 tabular-nums text-theme-text-secondary">
            {t("usage.resetCardsAvailable", {
              count: quota.reset_credits.available_count,
            })}
          </p>
        )}
      </div>
      {error && (
        <div className="space-y-2">
          <p role="alert" className="es-error">
            {error}
          </p>
          <Button
            size="sm"
            disabled={busy || loading}
            onClick={() => {
              setError("");
              void load();
            }}
          >
            {t("common.refresh")}
          </Button>
        </div>
      )}
      {notice && (
        <p role="status" className="es-hint">
          {notice}
        </p>
      )}
    </section>
  );
}
