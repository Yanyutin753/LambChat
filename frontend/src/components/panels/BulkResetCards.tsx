import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { usageApi, type ResetCardBatch } from "../../services/api/usage";
import { Permission } from "../../types";
import { Dialog } from "../common/Dialog";
import { Button } from "../common/ui/Button";
import { Select } from "../common/ui/Select";

type PendingIssue = { key: string; window: ResetCardBatch["window"] };

export function BulkResetCards({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { hasPermission, user, token } = useAuth();
  const allowed = hasPermission(Permission.USAGE_ADMIN);
  const storageKey = `lambchat:reset-card-batch:${user?.id ?? ""}`;
  const [window, setWindow] = useState<ResetCardBatch["window"]>("five_hour");
  const [batch, setBatch] = useState<ResetCardBatch | null>(null);
  const [pending, setPending] = useState<PendingIssue | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const selected = useRef(window);
  const pendingRef = useRef<PendingIssue | null>(null);
  const batchRef = useRef<ResetCardBatch | null>(null);
  const controller = useRef<AbortController | null>(null);
  const inFlight = useRef(false);

  const run = useCallback(
    async (loadLatest: boolean) => {
      const signal = controller.current?.signal;
      if (!signal || signal.aborted || inFlight.current) return;
      inFlight.current = true;
      setBusy(true);
      setError("");
      try {
        if (loadLatest) {
          const saved = localStorage.getItem(storageKey);
          if (saved) {
            const value = JSON.parse(saved) as PendingIssue;
            if (
              typeof value.key !== "string" ||
              !value.key ||
              !["five_hour", "weekly"].includes(value.window)
            )
              throw new Error(t("usage.quotaUnavailable"));
            pendingRef.current = value;
            setPending(value);
            selected.current = value.window;
            setWindow(value.window);
          }
          const { items } = await usageApi.listResetCardBatches(signal);
          if (signal.aborted) return;
          const active = items.find((item) => item.status !== "completed");
          if (!active) return;
          batchRef.current = active;
          setBatch(active);
          selected.current = active.window;
          setWindow(active.window);
        } else if (!batchRef.current) {
          const operation = pendingRef.current ?? {
            key: crypto.randomUUID(),
            window: selected.current,
          };
          // Persist before sending so a lost response or reload cannot issue another batch.
          localStorage.setItem(storageKey, JSON.stringify(operation));
          pendingRef.current = operation;
          setPending(operation);
          const created = await usageApi.createResetCardBatch(
            operation.window,
            operation.key,
            signal,
          );
          if (signal.aborted) return;
          batchRef.current = created;
          setBatch(created);
        }
        while (
          !signal.aborted &&
          batchRef.current &&
          batchRef.current.status !== "completed"
        ) {
          const next = await usageApi.advanceResetCardBatch(
            batchRef.current.id,
            signal,
          );
          if (signal.aborted) return;
          batchRef.current = next;
          setBatch(next);
          if (next.status !== "completed") {
            // Another tab may hold the server lease; pace successful steps without retrying errors.
            await new Promise<void>((resolve) => {
              const finish = () => {
                clearTimeout(timer);
                signal.removeEventListener("abort", finish);
                resolve();
              };
              const timer = setTimeout(finish, 250);
              signal.addEventListener("abort", finish, { once: true });
            });
          }
        }
        if (!signal.aborted && batchRef.current?.status === "completed") {
          localStorage.removeItem(storageKey);
          pendingRef.current = null;
          setPending(null);
        }
      } catch (cause) {
        if (!signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : t("common.operationFailed"),
          );
      } finally {
        if (!signal.aborted) {
          inFlight.current = false;
          setBusy(false);
        }
      }
    },
    [storageKey, t],
  );

  useEffect(() => {
    if (!open || !allowed) return;
    const current = new AbortController();
    controller.current = current;
    inFlight.current = false;
    batchRef.current = null;
    pendingRef.current = null;
    setBatch(null);
    setPending(null);
    void run(true);
    return () => current.abort();
  }, [open, allowed, user?.id, token, run]);

  if (!allowed) return null;
  const completed = batch?.status === "completed";
  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="md"
      title={<span className="font-serif">{t("usage.bulkCardsTitle")}</span>}
      footer={
        <>
          <Button className="font-serif" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          {!completed && (
            <Button
              variant="primary"
              className="max-w-full font-serif [&>span]:whitespace-normal"
              disabled={busy}
              onClick={() => void run(Boolean(error && !pending && !batch))}
            >
              {t(
                error || pending || batch
                  ? "common.retry"
                  : "usage.bulkCardsConfirm",
              )}
            </Button>
          )}
        </>
      }
    >
      <div
        className="space-y-4 font-serif text-14 text-theme-text-secondary"
        aria-busy={busy}
      >
        <p>{t("usage.bulkCardsScope")}</p>
        <div className="space-y-2">
          <p className="es-label">{t("usage.bulkCardsType")}</p>
          <Select
            ariaLabel={t("usage.bulkCardsType")}
            value={window}
            disabled={busy || Boolean(pending || batch)}
            onChange={(value) => {
              const next = value as ResetCardBatch["window"];
              selected.current = next;
              setWindow(next);
            }}
            options={[
              { value: "five_hour", label: t("usage.quotaFiveHour") },
              { value: "weekly", label: t("usage.quotaWeekly") },
            ]}
          />
          <p className="es-hint">{t("usage.resetCardGrantHint")}</p>
        </div>
        {busy && !batch && <p role="status">{t("common.loading")}</p>}
        {batch && (
          <div
            role="status"
            aria-live="polite"
            className="space-y-2 tabular-nums"
          >
            <p>
              {t(
                completed
                  ? "usage.bulkCardsComplete"
                  : batch.status === "preparing"
                    ? "usage.bulkCardsPreparing"
                    : "usage.bulkCardsProgress",
                { processed: batch.processed, total: batch.total },
              )}
            </p>
            <p>
              {t("usage.bulkCardsSummary", {
                issued: batch.issued,
                failed: batch.failed,
              })}
            </p>
          </div>
        )}
        {batch && batch.errors.length > 0 && (
          <ul className="max-h-40 list-inside list-disc space-y-1 overflow-y-auto text-12 [overflow-wrap:anywhere]">
            {batch.errors.slice(0, 10).map((item, index) => (
              <li key={`${item.user_id}:${index}`}>
                {item.user_id}: {item.message}
              </li>
            ))}
          </ul>
        )}
        {pending && !busy && !batch && <p>{t("usage.bulkCardsPending")}</p>}
        <p className="es-hint">{t("usage.bulkCardsResumeHint")}</p>
        {error && (
          <p role="alert" className="break-words text-theme-error">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
