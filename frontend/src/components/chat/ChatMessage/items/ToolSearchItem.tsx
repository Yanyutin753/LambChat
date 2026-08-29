import { memo } from "react";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";

import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（搜索结果到达即刷新） */
function ToolSearchDetail({ args, result }: ToolDetailProps) {
  const query = (args.query as string) || "";
  const hasResult = result !== undefined;
  const resultText = hasResult
    ? typeof result === "string"
      ? result
      : JSON.stringify(result, null, 2)
    : "";

  return (
    <div className="space-y-3 max-h-full overflow-y-auto p-2 sm:p-4">
      {query && (
        <ToolArgsBlock size="detail">
          <Search
            size={14}
            className="shrink-0 text-sky-500 dark:text-sky-400"
          />
          <span className="text-sky-600 dark:text-sky-400 font-mono font-semibold">
            {query}
          </span>
        </ToolArgsBlock>
      )}
      {hasResult && (
        <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolHoverCopyButton
            text={resultText}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <div>
            <ToolResultContent result={result} hideCopyButton />
          </div>
        </div>
      )}
    </div>
  );
}

const ToolSearchItem = memo(function ToolSearchItem({
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
  const query = (args.query as string) || "";
  const hasResult = result !== undefined;
  // 参数生成中（无 result）也允许打开面板：实时等待搜索结果
  const canExpand = !!query || hasResult || isPending;

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const resultText = hasResult
    ? typeof result === "string"
      ? result
      : JSON.stringify(result, null, 2)
    : "";

  const resultPreview = hasResult ? (
    <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto min-w-0">
      <ToolHoverCopyButton
        text={resultText}
        position="resultCompact"
        className="z-20 pointer-events-auto"
        copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
      />
      <div>
        <ToolResultContent result={result} hideCopyButton />
      </div>
    </div>
  ) : null;

  const detailContent = canExpand && (
    <ToolSearchDetail
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
        icon={<Search size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolSearchTools")} ${query || ""}`}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolSearchTools"),
            icon: <Search size={16} />,
            status,
            subtitle: query || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ToolSearchDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {query && (
              <ToolArgsBlock size="compact">
                <Search
                  size={12}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-sky-600 dark:text-sky-400 font-mono font-medium">
                  {query}
                </span>
              </ToolArgsBlock>
            )}
            {hasResult && (
              <div className="max-h-72 overflow-y-auto">{resultPreview}</div>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ToolSearchItem };
