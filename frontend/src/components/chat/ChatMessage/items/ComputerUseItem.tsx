import { memo, useMemo } from "react";
import { MousePointerClick } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { CollapsiblePill } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { getFullUrl } from "../../../../services/api/config";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { useImagePreviewFallback } from "./imagePreviewFallback";
import { computerUseRecord, parseComputerUseResult } from "./computerUseResult";

const key = "chat.message.computerUse";

function actionLabel(action: string, t: TFunction) {
  return t(`${key}.actions.${action}`, { defaultValue: action });
}

function displayValue(value: unknown): string {
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function resultSummary(
  parsed: ReturnType<typeof parseComputerUseResult>,
  t: TFunction,
) {
  const { data, error, text } = parsed;
  if (error) return error;
  if (typeof data.ready === "boolean")
    return t(`${key}.${data.ready ? "ready" : "notReady"}`);
  if (Array.isArray(data.apps))
    return t(`${key}.appCount`, { count: data.apps.length });
  if (Array.isArray(data.windows))
    return t(`${key}.windowCount`, { count: data.windows.length });
  if (typeof data.element_count === "number")
    return t(`${key}.elementCount`, { count: data.element_count });
  if (data.ok === true) return t(`${key}.succeeded`);
  return (
    text
      .split("\n")
      .find((line) => line.trim())
      ?.slice(0, 72) ?? ""
  );
}

function ComputerUseDetail({
  args,
  result,
  isPending,
  cancelled,
  success,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const { openImage, viewer } = useImagePreviewFallback();
  const parsed = useMemo(() => parseComputerUseResult(result), [result]);
  const { data, text, error, screenshotSrc } = parsed;
  const action = typeof args.action === "string" ? args.action : "";
  const windowInfo = computerUseRecord(data.window);
  const screenshot = computerUseRecord(data.screenshot);
  const needsPermission =
    ["ax_not_trusted", "screen_recording_denied"].includes(error) ||
    screenshot.error === "screen_recording_denied" ||
    data.accessibility === "denied" ||
    data.screen_recording === "denied";
  const offline = error === "dispatch_failed" && /offline/i.test(text);
  const state = typeof data.state === "string" ? data.state : "";
  const permission = (value: unknown) =>
    t(
      `${key}.permissions.${["granted", "denied"].includes(String(value)) ? value : "unknown"}`,
    );
  const resultFields: Record<string, unknown> = {
    platform: data.platform === "darwin" ? "macOS" : data.platform,
    ready:
      typeof data.ready === "boolean"
        ? t(`${key}.${data.ready ? "ready" : "notReady"}`)
        : undefined,
    accessibility: data.accessibility
      ? permission(data.accessibility)
      : undefined,
    screen_recording: data.screen_recording
      ? permission(data.screen_recording)
      : undefined,
    pid: data.pid,
    window_title: windowInfo.title,
    window_id: windowInfo.window_id,
    bounds: windowInfo.bounds,
    element_count: data.element_count,
    strategy: data.strategy,
    method: data.method,
    target: data.target,
    clicks: data.clicks,
  };
  const fields = (values: Record<string, unknown>) => (
    <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-2 text-12">
      {Object.entries(values)
        .filter(
          ([, value]) => value !== undefined && value !== null && value !== "",
        )
        .map(([field, value]) => (
          <div key={field} className="contents">
            <dt className="text-theme-text-tertiary break-words">
              {t(`${key}.fields.${field}`, { defaultValue: field })}
            </dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-theme-text-secondary [overflow-wrap:anywhere]">
              {displayValue(value)}
            </dd>
          </div>
        ))}
    </dl>
  );
  const parameterFields = Object.fromEntries(
    Object.entries(args).filter(([field]) => field !== "action"),
  );
  const lists = Array.isArray(data.apps)
    ? data.apps
    : Array.isArray(data.windows)
      ? data.windows
      : null;
  const apps = Array.isArray(data.apps);

  return (
    <div className="min-w-0 space-y-5 p-2 sm:p-4">
      <ToolArgsBlock size="detail" copyText={JSON.stringify(args, null, 2)}>
        <span className="flex items-center gap-2">
          <MousePointerClick
            size={14}
            className="shrink-0 text-indigo-500 dark:text-indigo-400"
          />
          <span className="font-semibold text-indigo-600 dark:text-indigo-400">
            {actionLabel(action, t)}
          </span>
        </span>
      </ToolArgsBlock>
      {Object.keys(parameterFields).length > 0 && fields(parameterFields)}
      {(isPending ||
        cancelled ||
        error ||
        success === false ||
        result === undefined) && (
        <div
          role="status"
          className="rounded-[var(--radius-sm)] border border-theme-border bg-theme-bg px-3 py-2 text-12 text-theme-text-secondary break-words"
        >
          {isPending
            ? t(`${key}.waiting`)
            : cancelled
              ? t(`${key}.cancelled`)
              : error || success === false
                ? t(`${key}.failed`)
                : t(`${key}.noResult`)}
          {error && <span className="ml-2 font-mono">{error}</span>}
        </div>
      )}
      {(needsPermission || offline) && (
        <p className="text-12 text-theme-text-secondary" role="status">
          {t(
            `${key}.${offline ? "offlineHint" : data.platform === "linux" ? "linuxPermissionHint" : data.platform === "win32" ? "windowsPermissionHint" : "permissionHint"}`,
          )}
        </p>
      )}
      {Object.values(resultFields).some((value) => value !== undefined) && (
        <section className="space-y-3">
          <h3 className="text-12 font-medium text-theme-text">
            {t(`${key}.observation`)}
          </h3>
          {fields(resultFields)}
        </section>
      )}
      {!!data.message && (
        <p className="text-12 text-theme-text-secondary break-words">
          {displayValue(data.message)}
        </p>
      )}
      {lists && (
        <section className="space-y-3">
          <h3 className="text-12 font-medium text-theme-text">
            {resultSummary(parsed, t)}
          </h3>
          {lists.length === 0 ? (
            <p className="text-12 text-theme-text-tertiary">
              {t(`${key}.${apps ? "noApps" : "noWindows"}`)}
            </p>
          ) : (
            <ul className="divide-y divide-theme-border">
              {lists.map((entry, index) => {
                const row = computerUseRecord(entry);
                return (
                  <li key={index} className="space-y-1 py-2 text-12">
                    <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="min-w-0 break-words text-theme-text-secondary [overflow-wrap:anywhere]">
                        {displayValue(row.name ?? row.title ?? "—")}
                      </span>
                      {row.active === true && (
                        <span className="text-theme-text-tertiary">
                          {t(`${key}.active`)}
                        </span>
                      )}
                      {row.focused === true && (
                        <span className="text-theme-text-tertiary">
                          {t(`${key}.focused`)}
                        </span>
                      )}
                      {row.main === true && (
                        <span className="text-theme-text-tertiary">
                          {t(`${key}.mainWindow`)}
                        </span>
                      )}
                    </div>
                    {fields(
                      apps
                        ? { pid: row.pid }
                        : { window_id: row.window_id, bounds: row.bounds },
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
      {screenshotSrc && (
        <figure className="min-w-0 space-y-2">
          <button
            type="button"
            onClick={() =>
              openImage(getFullUrl(screenshotSrc) || screenshotSrc)
            }
            className="block w-full cursor-zoom-in rounded-[var(--radius-sm)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary"
            aria-label={t("chat.message.openImage")}
          >
            <ImageWithSkeleton
              src={screenshotSrc}
              alt={t(`${key}.screenshot`)}
              loading="eager"
              aspectRatio={
                typeof screenshot.width === "number" &&
                typeof screenshot.height === "number"
                  ? `${screenshot.width}/${screenshot.height}`
                  : undefined
              }
              className="mx-auto max-h-[60dvh] w-full object-contain"
              wrapperClassName="!my-0 !shadow-none"
            />
          </button>
          <figcaption className="text-12 text-theme-text-tertiary">
            {t(`${key}.screenshot`)}
            {typeof screenshot.width === "number" &&
              typeof screenshot.height === "number" &&
              ` · ${screenshot.width} × ${screenshot.height}`}
          </figcaption>
        </figure>
      )}
      {(!!screenshot.upload_error || !!screenshot.error) && (
        <p role="status" className="text-12 text-theme-text-secondary">
          {t(`${key}.screenshotFailed`)}
          <span className="ml-2 font-mono">
            {displayValue(screenshot.error ?? screenshot.upload_error)}
          </span>
        </p>
      )}
      {state && (
        <section className="space-y-2">
          <h3 className="text-12 font-medium text-theme-text">
            {t(`${key}.tree`)}
          </h3>
          {data.truncated === true && (
            <p className="text-12 text-theme-text-tertiary">
              {t(`${key}.truncated`)}
            </p>
          )}
          <div className="group/result relative min-w-0">
            <ToolHoverCopyButton text={state} position="resultCompact" />
            <pre className="whitespace-pre-wrap break-words font-mono text-12 leading-relaxed text-theme-text-secondary [overflow-wrap:anywhere]">
              {state}
            </pre>
          </div>
        </section>
      )}
      {text && (
        <details
          open={Object.keys(data).length === 0}
          className="group/result relative min-w-0 text-12 text-theme-text-secondary"
        >
          <summary className="min-h-11 cursor-pointer py-3 text-theme-text-tertiary focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary">
            {t(`${key}.rawResult`)}
          </summary>
          <ToolHoverCopyButton text={text} position="resultCompact" />
          <pre className="whitespace-pre-wrap break-words font-mono leading-relaxed [overflow-wrap:anywhere]">
            {text}
          </pre>
        </details>
      )}
      {!isPending && !cancelled && result !== undefined && !text && (
        <p className="text-12 text-theme-text-tertiary">
          {t(`${key}.noResult`)}
        </p>
      )}
      {viewer}
    </div>
  );
}

const ComputerUseItem = memo(function ComputerUseItem({
  id,
  ...props
}: ToolDetailProps & { id?: string }) {
  const {
    args,
    result,
    success,
    isPending,
    cancelled,
    startedAt,
    completedAt,
  } = props;
  const { t } = useTranslation();
  const parsed = useMemo(() => parseComputerUseResult(result), [result]);
  const action = typeof args.action === "string" ? args.action : "";
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : parsed.error || success === false
        ? "error"
        : success || result !== undefined
          ? "success"
          : "idle";
  const target =
    args.name ??
    args.app ??
    (args.pid !== undefined ? `PID ${args.pid}` : args.machine_id);
  const element =
    args.index !== undefined
      ? `#${args.index}`
      : args.x !== undefined && args.y !== undefined
        ? `(${args.x}, ${args.y})`
        : "";
  const summary = isPending
    ? ""
    : cancelled
      ? t(`${key}.cancelled`)
      : resultSummary(parsed, t);
  const titleLabel = t("chat.message.computerUseTitle");
  const pillLabel = [
    titleLabel,
    actionLabel(action, t),
    target,
    element,
    summary,
  ]
    .filter(Boolean)
    .join(" · ");
  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });
  const canExpand = !!action || result !== undefined || isPending;
  return (
    <CollapsiblePill
      status={status}
      icon={<MousePointerClick size={12} className="shrink-0 opacity-50" />}
      label={label}
      animatedDots={isStreamingLabel}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title: titleLabel,
          icon: <MousePointerClick size={16} />,
          status,
          subtitle: actionLabel(action, t),
          fallback: <ComputerUseDetail {...props} />,
          buildDetail: (data) => (
            <ComputerUseDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: (
            <ToolDurationFooter
              startedAt={startedAt}
              completedAt={completedAt}
            />
          ),
        });
      }}
    />
  );
});

export { ComputerUseItem };
