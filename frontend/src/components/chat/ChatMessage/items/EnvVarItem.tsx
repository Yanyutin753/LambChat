import { memo, useMemo } from "react";
import { AlertCircle, CheckCircle2, KeyRound, ShieldCheck } from "lucide-react";
import { CopyButton } from "../../../common/CopyButton";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolArgsBlock } from "./ToolArgsBlock";

function parseEnvVarResult(result: ToolDetailProps["result"]) {
  const empty = { keys: [] as string[], message: "", error: false };
  try {
    const parsed = JSON.parse(extractText(result));
    const values = Array.isArray(parsed)
      ? parsed
      : parsed?.variables || parsed?.keys || (parsed?.key ? [parsed.key] : []);
    const keys = Array.isArray(values)
      ? values
          .map((value) => (typeof value === "string" ? value : value?.key))
          .filter((key): key is string => typeof key === "string" && !!key)
      : [];
    const error = typeof parsed?.error === "string" ? parsed.error : "";
    return {
      keys,
      message:
        error || (typeof parsed?.message === "string" ? parsed.message : ""),
      error: !!error || parsed?.success === false,
    };
  } catch {
    return empty;
  }
}

function getActionLabel(
  toolName: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const map: Record<string, string> = {
    env_var_list: "chat.message.toolEnvVarList",
    env_var_set: "chat.message.toolEnvVarSet",
    env_var_delete: "chat.message.toolEnvVarDelete",
    env_var_delete_all: "chat.message.toolEnvVarDeleteAll",
  };
  return t(map[toolName] || "chat.message.toolEnvVar");
}

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（变量列表到达即刷新） */
function EnvVarDetail({
  toolName,
  args,
  result,
  success,
  compact = false,
}: ToolDetailProps & { toolName: string; compact?: boolean }) {
  const { t } = useTranslation();
  const key = (args.key as string) || "";

  const parsed = useMemo(() => parseEnvVarResult(result), [result]);
  const keys = parsed.keys;
  const deleting =
    toolName === "env_var_delete" || toolName === "env_var_delete_all";
  const failed = parsed.error || success === false;

  const allKeys = useMemo(() => {
    const set = new Set<string>();
    if (key) set.add(key);
    keys.forEach((k) => set.add(k));
    return [...set];
  }, [key, keys]);

  return (
    <div
      className={
        compact ? "space-y-2" : "p-4 sm:p-5 space-y-4 tool-panel-content"
      }
    >
      {deleting && key && (
        <ToolArgsBlock size={compact ? "compact" : "detail"} copyText={key}>
          <KeyRound size={13} className="shrink-0 text-theme-text-tertiary" />
          <span className="min-w-0 flex-1 whitespace-normal [overflow-wrap:anywhere]">
            {key}
          </span>
        </ToolArgsBlock>
      )}
      {allKeys.length > 0 && !deleting && !failed && (
        <div className="rounded-xl border border-theme-border overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2 px-3 py-2.5 bg-theme-bg-card border-b border-theme-border">
            <ShieldCheck
              size={13}
              className="text-theme-text-tertiary shrink-0"
            />
            <span className="text-12 font-medium text-theme-text-secondary">
              {t("chat.message.toolVarCount", { count: allKeys.length })}
            </span>
            <span className="text-10 text-theme-text-tertiary ml-auto">
              {t("chat.message.envMasked", "Values masked")}
            </span>
          </div>
          {/* Key list */}
          <div className="divide-y divide-theme-border/40 bg-theme-bg">
            {allKeys.map((k, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 px-3 py-2.5 tool-file-row"
              >
                <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 bg-theme-bg-card">
                  <KeyRound size={11} className="text-theme-text-tertiary" />
                </div>
                <span className="text-14 font-mono text-theme-text min-w-0 [overflow-wrap:anywhere] flex-1">
                  {k}
                </span>
                <span className="text-11 text-theme-text-tertiary font-mono shrink-0 tracking-widest">
                  ••••••••
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {parsed.message && (
        <div
          role={failed ? "alert" : "status"}
          className="flex items-start gap-2 text-14"
        >
          {failed ? (
            <AlertCircle
              size={14}
              className="mt-2.5 shrink-0 text-theme-error"
            />
          ) : (
            <CheckCircle2
              size={14}
              className="mt-2.5 shrink-0 text-theme-success"
            />
          )}
          <span className="min-w-0 flex-1 py-1.5 text-theme-text-secondary leading-relaxed [overflow-wrap:anywhere]">
            {parsed.message}
          </span>
          <CopyButton text={extractText(result)} size={12} />
        </div>
      )}
      {result && allKeys.length === 0 && !parsed.message && (
        <pre className="group/result relative text-12 text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {(() => {
            const text = extractText(result);
            return text;
          })()}
          <ToolHoverCopyButton text={extractText(result)} position="result" />
        </pre>
      )}
    </div>
  );
}

const EnvVarItem = memo(function EnvVarItem({
  id,
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  toolName: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const actionLabel = getActionLabel(toolName, t);
  const key = (args.key as string) || "";

  const keys = useMemo(() => parseEnvVarResult(result).keys, [result]);

  const allKeys = useMemo(() => {
    const set = new Set<string>();
    if (key) set.add(key);
    keys.forEach((k) => set.add(k));
    return [...set];
  }, [key, keys]);

  const canExpand = allKeys.length > 0 || !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const labelSuffix = key || allKeys.join(", ");

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <EnvVarDetail
      toolName={toolName}
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // ── Inline (compact) view ──

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${actionLabel}${labelSuffix ? ` ${labelSuffix}` : ""}`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={<KeyRound size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: actionLabel,
            icon: <KeyRound size={16} />,
            status: pillStatus,
            subtitle: allKeys.join(", ") || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <EnvVarDetail
                toolName={toolName}
                {...toolDetailPropsFromPanelData(data)}
              />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <EnvVarDetail
              toolName={toolName}
              args={args}
              result={result}
              success={success}
              compact
            />
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { EnvVarItem };
