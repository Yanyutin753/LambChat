import { memo } from "react";
import { Download, FileInput, LinkIcon } from "lucide-react";
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

const UploadUrlToSandboxItem = memo(function UploadUrlToSandboxItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
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
  const url = (args.url as string) || "";
  const filePath = (args.file_path as string) || "";
  const hasResult = result !== undefined;
  const canExpand = !!url || !!filePath || hasResult;
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

  const detailContent = canExpand && (
    <div className="space-y-3 max-h-full overflow-y-auto p-2 sm:p-4">
      {url && (
        <ToolArgsBlock size="detail" wrap>
          <LinkIcon
            size={14}
            className="shrink-0 text-cyan-500 dark:text-cyan-400"
          />
          <span className="break-all">{url}</span>
        </ToolArgsBlock>
      )}
      {filePath && (
        <ToolArgsBlock size="detail" wrap>
          <FileInput
            size={14}
            className="shrink-0 text-emerald-500 dark:text-emerald-400"
          />
          <span className="break-all">{filePath}</span>
        </ToolArgsBlock>
      )}
      {resultPreview}
    </div>
  );

  return (
    <CollapsiblePill
      status={status}
      icon={<Download size={12} className="shrink-0 opacity-50" />}
      label={`${t("chat.message.toolUploadUrlToSandbox")} ${
        filePath ? truncate(filePath, 56) : truncate(url, 56)
      }`}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openPersistentToolPanel({
          title: t("chat.message.toolUploadUrlToSandbox"),
          icon: <Download size={16} />,
          status,
          subtitle: filePath || url || undefined,
          children: detailContent,
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {url && (
            <ToolArgsBlock size="compact" wrap>
              <LinkIcon
                size={12}
                className="shrink-0 text-cyan-500 dark:text-cyan-400"
              />
              <span className="break-all">{truncate(url, 120)}</span>
            </ToolArgsBlock>
          )}
          {filePath && (
            <ToolArgsBlock size="compact" wrap>
              <FileInput
                size={12}
                className="shrink-0 text-emerald-500 dark:text-emerald-400"
              />
              <span className="break-all">{truncate(filePath, 120)}</span>
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

export { UploadUrlToSandboxItem };
