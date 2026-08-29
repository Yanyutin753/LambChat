import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { FolderSearch, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractPaths } from "./toolUtils";
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
function GlobDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const pattern = (args.pattern as string) || "";
  const searchPath = (args.path as string) || "";

  const paths = useMemo(() => {
    return extractPaths(result);
  }, [result]);

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      <ToolArgsBlock size="detail" wrap>
        <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
          {pattern}
        </span>
        {searchPath && (
          <span className="text-theme-text-tertiary">
            {t("chat.message.toolInPath", { path: searchPath })}
          </span>
        )}
      </ToolArgsBlock>
      {paths.length > 0 && (
        <div className="relative group rounded-lg border border-theme-border bg-theme-bg overflow-auto max-h-[60dvh]">
          <ToolHoverCopyButton
            text={paths.join("\n")}
            size={14}
            position="panelRaised"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
          {paths.map((p, i) => {
            const isDir = p.endsWith("/") || p.endsWith("\\");
            const name = isDir
              ? p.slice(0, -1).split("/").filter(Boolean).pop() ||
                p.slice(0, -1)
              : p.split("/").filter(Boolean).pop() || p;
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
                  <FolderSearch
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
      )}
    </div>
  );
}

const GlobItem = memo(function GlobItem({
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
  const pattern = (args.pattern as string) || "";
  const searchPath = (args.path as string) || "";

  const paths = useMemo(() => {
    return extractPaths(result);
  }, [result]);

  // 运行中（pattern 已到、无 result）也允许打开面板：实时等待匹配结果
  const canExpand = !!pattern || paths.length > 0 || isPending;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <GlobDetail
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
        icon={<FolderSearch size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolGlob")} ${pattern || ""}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: `${t("chat.message.toolGlob")} ${pattern}`,
            icon: <FolderSearch size={16} />,
            status,
            subtitle: searchPath || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <GlobDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <ToolArgsBlock size="compact" wrap>
              <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                {pattern}
              </span>
              {searchPath && (
                <span className="text-theme-text-tertiary">
                  {t("chat.message.toolInPath", { path: searchPath })}
                </span>
              )}
            </ToolArgsBlock>
            {paths.length > 0 && (
              <div className="relative group max-h-48 overflow-y-auto rounded-md border border-theme-border bg-theme-bg">
                <ToolHoverCopyButton
                  text={paths.join("\n")}
                  position="panelCompactRaised"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
                {paths.map((p, i) => {
                  const isDir = p.endsWith("/") || p.endsWith("\\");
                  const name = isDir
                    ? p.slice(0, -1).split("/").filter(Boolean).pop() ||
                      p.slice(0, -1)
                    : p.split("/").filter(Boolean).pop() || p;
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
                        <FolderSearch
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
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { GlobItem };
