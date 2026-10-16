import { memo, useMemo } from "react";
import { clsx } from "clsx";
import {
  Terminal,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Ban,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { deriveExecuteStatus, parseExecuteResult } from "./executeResult";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";

function ExecuteStatusLine({
  status,
  exitCode,
  truncated,
}: {
  status: CollapsibleStatus;
  exitCode: number | null;
  truncated: boolean;
}) {
  const { t } = useTranslation();
  if (status === "idle") return null;
  const Icon =
    status === "success"
      ? CheckCircle2
      : status === "cancelled"
        ? Ban
        : XCircle;
  return (
    <div
      className="flex min-h-9 items-center gap-2 text-13 text-theme-text-secondary"
      role="status"
    >
      {status === "loading" ? (
        <LoadingSpinner size="xs" />
      ) : (
        <Icon
          size={14}
          className={
            status === "error"
              ? "text-theme-error"
              : status === "success"
                ? "text-theme-success"
                : "text-theme-text-secondary"
          }
        />
      )}
      <span>
        {status === "loading" || status === "cancelled"
          ? t(`chat.eventStatus.${status}`)
          : t(
              status === "success"
                ? "chat.message.toolSuccess"
                : "chat.message.toolFailed",
            )}
      </span>
      {exitCode !== null && status !== "loading" && status !== "cancelled" && (
        <span>{t("chat.message.toolExitCode", { code: exitCode })}</span>
      )}
      {truncated && <AlertTriangle size={14} className="text-theme-warning" />}
    </div>
  );
}

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（执行输出到达即刷新） */
function ExecuteDetail({
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt: _startedAt,
  completedAt: _completedAt,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const command = (args.command as string) || "";
  const timeout = args.timeout as number | undefined;
  const parsed = useMemo(() => parseExecuteResult(result), [result]);
  const status = deriveExecuteStatus({ isPending, cancelled, success, result });

  return (
    <div className="p-4 sm:p-5 tool-panel-content tool-panel-content--fill">
      <div className="group/args relative px-3.5 py-3 rounded-xl bg-theme-bg-subtle text-14 font-mono flex items-center gap-2.5 border border-theme-border-subtle transition-colors duration-200">
        <Terminal size={13} className="shrink-0 text-theme-text-tertiary" />
        <span className="shrink-0 text-theme-text-secondary font-semibold">
          $
        </span>
        <span className="text-theme-text break-words [overflow-wrap:anywhere] min-w-0 flex-1">
          {command}
        </span>
        {timeout && (
          <span className="shrink-0 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-12 ring-1 ring-theme-border/50">
            {t("chat.message.toolTimeSeconds", { count: timeout })}
          </span>
        )}
      </div>

      {parsed.output && (
        <div className="relative group tool-panel-output">
          <pre
            tabIndex={0}
            aria-label={t("chat.message.toolOutput")}
            className={clsx(
              "text-14 rounded-xl p-4 min-w-0 h-full tool-code-block",
              "bg-theme-bg border border-theme-border",
              "text-theme-text-secondary whitespace-pre-wrap break-words font-mono",
            )}
          >
            {parsed.output}
          </pre>
          <ToolHoverCopyButton
            text={parsed.output}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-lg !border !border-theme-border"
          />
        </div>
      )}

      <ExecuteStatusLine
        status={status}
        exitCode={parsed.exitCode}
        truncated={parsed.truncated}
      />
    </div>
  );
}

const ExecuteItem = memo(function ExecuteItem({
  id,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
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
  const command = (args.command as string) || "";
  const timeout = args.timeout as number | undefined;

  const parsed = useMemo(() => parseExecuteResult(result), [result]);

  const canExpand = !!command || !!parsed.output;
  const status = deriveExecuteStatus({ isPending, cancelled, success, result });

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    command
      ? `${t("chat.message.toolExecute")} ${command}`
      : t("chat.message.toolExecute"),
    args,
    { isPending, result },
  );

  const detailContent = canExpand && (
    <ExecuteDetail
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
    <>
      <CollapsiblePill
        status={status}
        icon={<Terminal size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolExecute"),
            icon: <Terminal size={16} />,
            status,
            subtitle:
              command.length > 120 ? command.slice(0, 117) + "…" : command,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ExecuteDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <div className="group/args relative px-2 py-1.5 rounded-md bg-theme-bg-subtle text-12 text-theme-text-tertiary font-mono flex items-baseline gap-2">
              <span className="shrink-0 text-theme-text">$</span>
              <span className="text-theme-text-secondary break-all min-w-0 flex-1">
                {command}
              </span>
              {timeout && (
                <span className="shrink-0 px-1 py-0.5 rounded bg-theme-bg-subtle text-theme-text-secondary">
                  {t("chat.message.toolTimeSeconds", { count: timeout })}
                </span>
              )}
            </div>

            {parsed.output && (
              <div className="relative group">
                <pre
                  className={clsx(
                    "text-12 rounded-md p-2.5 min-w-0",
                    "bg-theme-bg border border-theme-border",
                    "text-theme-text-secondary whitespace-pre-wrap break-words font-mono",
                  )}
                >
                  {parsed.output}
                </pre>
                <ToolHoverCopyButton
                  text={parsed.output}
                  position="panelCompact"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
              </div>
            )}

            <ExecuteStatusLine
              status={status}
              exitCode={parsed.exitCode}
              truncated={parsed.truncated}
            />
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ExecuteItem };
