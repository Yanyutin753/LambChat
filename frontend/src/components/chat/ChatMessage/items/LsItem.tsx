import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { FolderOpen, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractPaths, extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function LsDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const dirPath = (args.path as string) || "/";

  const rawText = extractText(result);
  const entries = useMemo(() => {
    return extractPaths(result);
  }, [result]);
  const hasEntries = entries.length > 0;

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      <ToolArgsBlock size="detail">
        <FolderOpen size={14} className="shrink-0 opacity-60" />
        <span className="truncate">{dirPath}</span>
        {hasEntries && (
          <span className="shrink-0 text-theme-text-tertiary">
            {t("chat.message.toolItemCount", { count: entries.length })}
          </span>
        )}
      </ToolArgsBlock>
      {hasEntries ? (
        <div className="relative group rounded-lg border border-theme-border bg-theme-bg overflow-auto max-h-[60dvh]">
          <ToolHoverCopyButton
            text={entries.join("\n")}
            size={14}
            position="panelRaised"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
          {entries.map((entry, i) => {
            const isDir = entry.endsWith("/") || entry.endsWith("\\");
            const name = isDir
              ? entry.slice(0, -1).split("/").filter(Boolean).pop() ||
                entry.slice(0, -1)
              : entry.split("/").filter(Boolean).pop() || entry;
            return (
              <div
                key={i}
                className={clsx(
                  "flex items-center gap-2.5 px-4 py-2 text-sm font-mono tool-file-row",
                  "border-b border-theme-border-faint last:border-b-0",
                  "hover:bg-theme-bg-subtle transition-colors",
                )}
              >
                {isDir ? (
                  <FolderOpen
                    size={14}
                    className="shrink-0 text-amber-500 dark:text-amber-400"
                  />
                ) : (
                  <FileText
                    size={14}
                    className="shrink-0 text-theme-text-tertiary"
                  />
                )}
                <span
                  className={clsx(
                    "min-w-0 flex-1 truncate",
                    isDir
                      ? "text-theme-text font-medium"
                      : "text-theme-text-secondary",
                  )}
                >
                  {name}
                </span>
              </div>
            );
          })}
        </div>
      ) : rawText.trim().length > 0 ? (
        <pre className="group/result relative max-h-[60dvh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-theme-border bg-theme-bg p-3 text-xs text-theme-text-secondary">
          <ToolHoverCopyButton
            text={rawText}
            size={14}
            position="result"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
          {rawText}
        </pre>
      ) : null}
    </div>
  );
}

const LsItem = memo(function LsItem({
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
  const dirPath = (args.path as string) || "/";

  const rawText = extractText(result);
  const entries = useMemo(() => {
    return extractPaths(result);
  }, [result]);

  // 参数生成中（无 result）也允许打开面板：实时等待目录列表
  const canExpand =
    rawText.trim().length > 0 || isPending || !!(args.path as string);
  const hasEntries = entries.length > 0;
  const displayLabel =
    dirPath === "/" ? "/" : dirPath.split("/").filter(Boolean).pop() || dirPath;
  const pillCount = hasEntries
    ? ` ${t("chat.message.toolItemCount", { count: entries.length })}`
    : "";
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <LsDetail
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
        icon={<FolderOpen size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolLs")} ${dirPath}${pillCount}`}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: `${t("chat.message.toolLs")} ${displayLabel}`,
            icon: <FolderOpen size={16} />,
            status,
            subtitle: dirPath,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <LsDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <ToolArgsBlock size="compact">
              <FolderOpen size={12} className="shrink-0 opacity-60" />
              <span className="truncate">{dirPath}</span>
              {hasEntries && (
                <span className="shrink-0 text-theme-text-tertiary">
                  {t("chat.message.toolItemCount", { count: entries.length })}
                </span>
              )}
            </ToolArgsBlock>
            {hasEntries ? (
              <div className="relative group max-h-48 overflow-y-auto rounded-md border border-theme-border bg-theme-bg">
                <ToolHoverCopyButton
                  text={entries.join("\n")}
                  position="panelCompactRaised"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
                {entries.map((entry, i) => {
                  const isDir = entry.endsWith("/") || entry.endsWith("\\");
                  const name = isDir
                    ? entry.slice(0, -1).split("/").filter(Boolean).pop() ||
                      entry.slice(0, -1)
                    : entry.split("/").filter(Boolean).pop() || entry;
                  return (
                    <div
                      key={i}
                      className={clsx(
                        "flex items-center gap-2 px-3 py-1 text-xs font-mono tool-file-row",
                        "border-b border-theme-border-faint last:border-b-0",
                        "hover:bg-theme-bg-subtle transition-colors",
                      )}
                    >
                      {isDir ? (
                        <FolderOpen
                          size={12}
                          className="shrink-0 text-amber-500 dark:text-amber-400"
                        />
                      ) : (
                        <FileText
                          size={12}
                          className="shrink-0 text-theme-text-tertiary"
                        />
                      )}
                      <span
                        className={clsx(
                          "min-w-0 flex-1 truncate",
                          isDir
                            ? "text-theme-text font-medium"
                            : "text-theme-text-secondary",
                        )}
                      >
                        {name}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <pre className="group/result relative max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-theme-border bg-theme-bg p-2 text-xs text-theme-text-secondary">
                <ToolHoverCopyButton
                  text={rawText}
                  position="resultCompact"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
                {rawText}
              </pre>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { LsItem };
