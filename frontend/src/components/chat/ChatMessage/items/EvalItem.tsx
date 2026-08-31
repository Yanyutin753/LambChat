import { memo } from "react";
import { Code2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton } from "../../../common";
import { parseEvalWireResult } from "./evalWireResult";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

function isEvalToolName(toolName: string): boolean {
  return toolName.toLowerCase() === "eval";
}

function getStringArg(
  args: Record<string, unknown>,
  names: string[],
): string | undefined {
  for (const name of names) {
    const value = args[name];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }
  return undefined;
}

function getEvalCodePreview(
  args: Record<string, unknown>,
): { code: string; language?: string } | null {
  const code = getStringArg(args, [
    "code",
    "script",
    "source",
    "input",
    "expression",
    "command",
  ]);
  if (!code) return null;

  return {
    code,
    language: getStringArg(args, ["language", "lang", "runtime", "kernel"]),
  };
}

function formatCompactPreview(value: string, maxLength = 96): string {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 1)}…`;
}

function getEvalPillSummary(
  args: Record<string, unknown>,
  codePreview: { code: string; language?: string } | null,
): string | undefined {
  if (codePreview) return formatCompactPreview(codePreview.code);

  const entries = Object.entries(args)
    .filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    )
    .slice(0, 2)
    .map(([key, value]) => {
      const text =
        typeof value === "string"
          ? value
          : JSON.stringify(value) || String(value);
      return `${key}=${formatCompactPreview(text, 42)}`;
    });

  if (entries.length === 0) return undefined;
  return entries.join(" ");
}

function deriveStatus({
  isPending,
  cancelled,
  success,
  hasResult,
}: {
  isPending?: boolean;
  cancelled?: boolean;
  success?: boolean;
  hasResult: boolean;
}) {
  if (isPending) return "loading";
  if (cancelled) return "cancelled";
  if (success) return "success";
  if (hasResult) return "error";
  return "idle";
}

const evalCodePreviewClassName =
  "eval-code-preview rounded-xl border border-theme-border bg-[color-mix(in_srgb,var(--theme-bg)_78%,var(--theme-bg-card)_22%)] px-3.5 py-3 text-sm text-theme-text-secondary shadow-inner overflow-x-auto overflow-y-auto min-w-0 font-mono";

const evalInlineCodePreviewClassName =
  "eval-code-preview rounded-md border border-theme-border bg-[color-mix(in_srgb,var(--theme-bg)_78%,var(--theme-bg-card)_22%)] px-2.5 py-2 text-xs text-theme-text-secondary shadow-inner overflow-x-auto max-h-48 overflow-y-auto min-w-0 font-mono";

const evalKindBadgeClassName =
  "rounded-md bg-[color-mix(in_srgb,var(--theme-bg)_60%,var(--theme-bg-card)_40%)] px-1.5 py-0.5 text-9 font-medium uppercase tracking-wide text-theme-text-tertiary";

const evalStdoutPreviewClassName =
  "eval-code-preview rounded-lg border border-dashed border-theme-border bg-theme-bg px-3 py-2.5 text-xs text-theme-text-secondary overflow-x-auto max-h-40 overflow-y-auto min-w-0 font-mono whitespace-pre";

/** 结果视图：剥掉 wire 标签，直接呈现返回值/错误/控制台输出 */
function EvalResultContent({
  result,
  variant = "panel",
}: {
  result?: string | Record<string, unknown>;
  variant?: "panel" | "inline";
}) {
  const { t } = useTranslation();
  const compact = variant === "inline";
  const parsed =
    typeof result === "string" ? parseEvalWireResult(result) : null;

  if (!parsed) {
    const rawText =
      typeof result === "string"
        ? result
        : result === undefined
          ? ""
          : JSON.stringify(result, null, 2);
    if (!rawText) return null;
    return (
      <pre
        className={
          compact
            ? evalInlineCodePreviewClassName
            : evalCodePreviewClassName
        }
      >
        <code>{rawText}</code>
      </pre>
    );
  }

  const { stdout, value, error } = parsed;

  return (
    <div className="space-y-3 min-w-0">
      {error ? (
        <div
          className={
            compact
              ? "rounded-md border border-red-200/70 bg-red-50/60 px-2.5 py-2 dark:border-red-900/50 dark:bg-red-950/20"
              : "rounded-xl border border-red-200/70 bg-red-50/60 px-3.5 py-3 dark:border-red-900/50 dark:bg-red-950/20"
          }
        >
          {error.type && (
            <span className={`${evalKindBadgeClassName} mb-1.5 inline-block bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300`}>
              {error.type}
            </span>
          )}
          <pre className="overflow-x-auto text-xs font-mono leading-relaxed text-red-700 dark:text-red-300">
            <code>{error.message}</code>
          </pre>
        </div>
      ) : (
        value !== undefined &&
        (value === "undefined" ? (
          <p className="text-xs font-mono italic text-theme-text-tertiary">
            undefined
          </p>
        ) : (
          <pre
            className={
              compact
                ? evalInlineCodePreviewClassName
                : evalCodePreviewClassName
            }
          >
            <code>{value}</code>
          </pre>
        ))
      )}

      {stdout && (
        <div className="min-w-0">
          <div className="mb-1 text-xs font-medium text-theme-text-tertiary">
            {t("chat.message.consoleOutput")}
          </div>
          <pre className={evalStdoutPreviewClassName}>
            <code>{stdout}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function EvalDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const codePreview = getEvalCodePreview(args);
  const argsJson = JSON.stringify(args, null, 2);
  const hasArgs = Object.keys(args).length > 0;
  const hasResult = result !== undefined;

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {codePreview && (
        <section className="space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs font-medium text-theme-text-tertiary">
            <span>{t("chat.message.codePreview")}</span>
            <CopyButton text={codePreview.code} size={12} />
          </div>
          <pre className={evalCodePreviewClassName}>
            <code>{codePreview.code}</code>
          </pre>
        </section>
      )}

      {hasArgs && (
        <section className="space-y-2">
          <div className="text-xs font-medium text-theme-text-tertiary">
            {t("chat.message.args")}
          </div>
          <pre className="rounded-xl border border-theme-border bg-theme-bg px-3.5 py-3 text-sm text-theme-text-secondary overflow-x-auto overflow-y-auto min-w-0 font-mono">
            {argsJson}
          </pre>
        </section>
      )}

      {hasResult && (
        <section className="space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs font-medium text-theme-text-tertiary">
            <span>{t("chat.message.result")}</span>
            <CopyButton
              text={
                typeof result === "string"
                  ? result
                  : JSON.stringify(result, null, 2)
              }
              size={12}
            />
          </div>
          <EvalResultContent result={result} variant="panel" />
        </section>
      )}
    </div>
  );
}

const EvalItem = memo(function EvalItem({
  id,
  toolName = "eval",
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  toolName?: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const codePreview = getEvalCodePreview(args);
  const argsJson = JSON.stringify(args, null, 2);
  const hasArgs = Object.keys(args).length > 0;
  const hasResult = result !== undefined;
  // 运行中（args 已到、无 result）也允许打开面板：实时等待执行结果
  const canExpand = !!codePreview || hasArgs || hasResult || isPending;
  const status = deriveStatus({ isPending, cancelled, success, hasResult });
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );
  const evalLabel = t("chat.message.toolEval");
  const title = isEvalToolName(toolName) ? evalLabel : toolName;
  const pillSummary = getEvalPillSummary(args, codePreview);
  const pillLabel = pillSummary ? `${evalLabel} ${pillSummary}` : evalLabel;

  const detailContent = canExpand && (
    <EvalDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  return (
    <CollapsiblePill
      status={status}
      icon={<Code2 size={12} className="shrink-0 opacity-60" />}
      label={pillLabel}
      suffix={
        codePreview?.language ? (
          <span className="text-9 px-1.5 py-0.5 rounded-md bg-white/35 dark:bg-black/25 opacity-75 font-medium truncate max-w-[120px] uppercase tracking-normal">
            {codePreview.language}
          </span>
        ) : undefined
      }
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title,
          icon: <Code2 size={16} />,
          status,
          subtitle: codePreview?.language,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <EvalDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {codePreview && (
            <div className="relative group">
              <pre className={evalInlineCodePreviewClassName}>
                <code>{codePreview.code}</code>
              </pre>
              <ToolHoverCopyButton
                text={codePreview.code}
                position="panelCompact"
                copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
              />
            </div>
          )}

          {hasArgs && (
            <pre className="rounded-md border border-theme-border bg-theme-bg px-2.5 py-2 text-xs text-theme-text-secondary overflow-x-auto max-h-40 overflow-y-auto min-w-0 font-mono">
              {argsJson}
            </pre>
          )}

          {hasResult && <EvalResultContent result={result} variant="inline" />}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { EvalItem };
