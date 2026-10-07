import { memo, useMemo } from "react";
import { MousePointerClick } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";

import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 权限类错误：给出「到系统设置授权一次」的提示行 */
const PERMISSION_ERRORS = [
  "ax_not_trusted",
  "screen_recording_denied",
];

function resultText(result?: string | Record<string, unknown>): string {
  if (result === undefined || result === null) return "";
  return typeof result === "string" ? result : JSON.stringify(result, null, 2);
}

/** 面板详情：AX 树/应用列表等观察文本为主视图 */
function ComputerUseDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const action = (args.action as string) || "";
  const text = resultText(result);
  const needsPermission = PERMISSION_ERRORS.some((code) => text.includes(code));

  return (
    <div className="flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {action && (
        <ToolArgsBlock size="detail">
          <MousePointerClick
            size={14}
            className="shrink-0 text-indigo-500 dark:text-indigo-400"
          />
          <span className="text-indigo-600 dark:text-indigo-400 font-mono font-semibold">
            {action}
          </span>
        </ToolArgsBlock>
      )}

      {needsPermission && (
        <div className="rounded-lg bg-theme-bg border border-theme-border px-3 py-2 text-12 text-theme-text-secondary">
          {t("chat.message.computerUsePermissionHint")}
        </div>
      )}

      {text && (
        <div className="group/result relative flex-1 min-h-0 text-12 text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolHoverCopyButton
            text={text}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <ToolResultContent result={result} hideCopyButton />
        </div>
      )}
    </div>
  );
}

const ComputerUseItem = memo(function ComputerUseItem({
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
  const action = (args.action as string) || "";
  const text = useMemo(() => resultText(result), [result]);
  const hasResult = result !== undefined;
  const canExpand = !!action || hasResult || isPending;
  const needsPermission = PERMISSION_ERRORS.some((code) => text.includes(code));

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const titleLabel = t("chat.message.computerUseTitle");
  const pillLabel = `${titleLabel}${action ? ` ${action}` : ""}`.trim();
  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });

  // 观察结果首行（window: … / pid=…）做行内预览
  const firstLine = text ? text.split("\n").find((line) => line.trim()) : "";

  const detailContent = canExpand && (
    <ComputerUseDetail
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
          subtitle: action || undefined,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <ComputerUseDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {action && (
            <ToolArgsBlock size="compact">
              <MousePointerClick
                size={12}
                className="shrink-0 text-indigo-500 dark:text-indigo-400"
              />
              <span className="text-indigo-600 dark:text-indigo-400 font-mono font-medium min-w-0 truncate">
                {truncate(action, 40)}
              </span>
            </ToolArgsBlock>
          )}

          {needsPermission && (
            <div className="text-11 text-theme-text-secondary px-1">
              {truncate(t("chat.message.computerUsePermissionHint"), 80)}
            </div>
          )}

          {firstLine && !needsPermission && (
            <div className="text-11 text-theme-text-tertiary font-mono px-1 truncate">
              {truncate(firstLine, 72)}
            </div>
          )}

          {hasResult && !firstLine && !needsPermission && (
            <div className="group/result relative text-12 text-theme-text-secondary overflow-y-auto min-w-0">
              <ToolHoverCopyButton
                text={text}
                position="resultCompact"
                className="z-20 pointer-events-auto"
                copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
              />
              <ToolResultContent result={result} hideCopyButton />
            </div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { ComputerUseItem };
