import { memo } from "react";
import { ArrowRight, FolderInput, FolderOutput, Repeat2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolResultContent } from "./McpBlockPreview";

function stringifyResult(result: string | Record<string, unknown> | undefined) {
  if (result === undefined) return "";
  return typeof result === "string" ? result : JSON.stringify(result, null, 2);
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
}

const TransferItem = memo(function TransferItem({
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
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
  const isPathTransfer = toolName === "transfer_path";
  const source = isPathTransfer
    ? (args.source_dir as string) || ""
    : (args.source_path as string) || "";
  const target = isPathTransfer
    ? (args.target_prefix as string) || ""
    : (args.target_path as string) || "";
  const title = isPathTransfer
    ? t("chat.message.toolTransferPath")
    : t("chat.message.toolTransferFile");
  const hasResult = result !== undefined;
  const canExpand = !!source || !!target || hasResult;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";
  const resultText = stringifyResult(result);

  const resultPreview = hasResult ? (
    <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto min-w-0">
      <ToolHoverCopyButton
        text={resultText}
        position="resultCompact"
        className="z-20 pointer-events-auto"
        copyButtonClassName="bg-white/90 shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
      />
      <ToolResultContent result={result} hideCopyButton />
    </div>
  ) : null;

  const pathRows = (
    <>
      {source && (
        <ToolArgsBlock size="detail" wrap>
          <FolderOutput
            size={14}
            className="shrink-0 text-blue-500 dark:text-blue-400"
          />
          <span className="break-all">{source}</span>
        </ToolArgsBlock>
      )}
      {target && (
        <ToolArgsBlock size="detail" wrap>
          <FolderInput
            size={14}
            className="shrink-0 text-emerald-500 dark:text-emerald-400"
          />
          <span className="break-all">{target}</span>
        </ToolArgsBlock>
      )}
    </>
  );

  const detailContent = canExpand && (
    <div className="space-y-3 max-h-full overflow-y-auto p-2 sm:p-4">
      {pathRows}
      {resultPreview}
    </div>
  );

  return (
    <CollapsiblePill
      status={status}
      icon={<Repeat2 size={12} className="shrink-0 opacity-50" />}
      label={`${title} ${truncate(source || target, 56)}`}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openPersistentToolPanel({
          title,
          icon: <Repeat2 size={16} />,
          status,
          subtitle:
            source && target
              ? `${source} -> ${target}`
              : source || target || undefined,
          children: detailContent,
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {source && (
            <ToolArgsBlock size="compact" wrap>
              <FolderOutput
                size={12}
                className="shrink-0 text-blue-500 dark:text-blue-400"
              />
              <span className="break-all">{truncate(source, 120)}</span>
            </ToolArgsBlock>
          )}
          {target && (
            <ToolArgsBlock size="compact" wrap>
              <ArrowRight size={12} className="shrink-0 opacity-50" />
              <span className="break-all">{truncate(target, 120)}</span>
            </ToolArgsBlock>
          )}
          {hasResult && (
            <div className="max-h-72 overflow-y-auto">{resultPreview}</div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { TransferItem };
