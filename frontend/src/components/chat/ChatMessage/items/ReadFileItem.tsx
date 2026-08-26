import { memo, useMemo } from "react";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { DeferredCodeMirrorViewer } from "../../../common/DeferredCodeMirrorViewer";
import {
  stripLineNumbers,
  readFileStartLine,
  extractText,
  type McpMultiModalResult,
  type McpContentBlock,
} from "./toolUtils";
import { McpBlockPreview } from "./McpBlockPreview";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";

const ReadFileItem = memo(function ReadFileItem({
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
  const filePath = (args.file_path as string) || "";
  const fileName = filePath.split("/").pop() || filePath;
  const offset = args.offset as number | undefined;
  const limit = args.limit as number | undefined;
  const startLine = readFileStartLine(offset);
  const endLine = limit ? startLine + limit - 1 : undefined;

  const displayContent = useMemo(() => {
    const raw = extractText(result);
    return raw ? stripLineNumbers(raw) : "";
  }, [result]);

  // Detect image blocks in McpMultiModalResult format ({text, blocks})
  const imageBlocks = useMemo(() => {
    if (
      typeof result === "object" &&
      result !== null &&
      "blocks" in result &&
      Array.isArray((result as McpMultiModalResult).blocks)
    ) {
      return (result as McpMultiModalResult).blocks!.filter(
        (b: McpContentBlock) => b.type === "image",
      );
    }
    // LangChain content blocks array
    if (
      Array.isArray(result) &&
      result.length > 0 &&
      typeof result[0] === "object" &&
      result[0] !== null &&
      "type" in result[0]
    ) {
      return (result as McpContentBlock[]).filter((b) => b.type === "image");
    }
    return [];
  }, [result]);

  const hasContent = !!displayContent || imageBlocks.length > 0;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = hasContent && (
    <div className="p-4 sm:p-5 space-y-3 tool-panel-content">
      <ToolArgsBlock size="detail">
        <span className="truncate">{filePath}</span>
        {(offset !== undefined || limit !== undefined) && (
          <span className="shrink-0 text-theme-text-tertiary">
            :L{startLine}
            {endLine ? `-${endLine}` : ""}
          </span>
        )}
      </ToolArgsBlock>
      {imageBlocks.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {imageBlocks.map((block, i) => (
            <McpBlockPreview key={i} block={block} />
          ))}
        </div>
      )}
      {displayContent && (
        <div className="relative group rounded-lg tool-code-block">
          <DeferredCodeMirrorViewer
            value={displayContent}
            filePath={filePath}
            lineNumbers={true}
            fontSize="0.8rem"
            startLine={startLine}
            highlightLineRange={
              offset !== undefined || limit !== undefined
                ? { from: startLine, to: endLine ?? startLine }
                : undefined
            }
          />
          <ToolHoverCopyButton
            text={displayContent}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}
    </div>
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<FileText size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolRead")} ${filePath || ""}`}
        variant="tool"
        formatLabel={false}
        expandable={hasContent}
        onPanelOpen={() => {
          if (!hasContent) return;
          openPersistentToolPanel({
            title: `${t("chat.message.toolRead")} ${fileName || filePath}`,
            icon: <FileText size={16} />,
            status,
            subtitle: filePath,
            children: detailContent,
            footer: durationFooter,
          });
        }}
      >
        {hasContent && (
          <ToolInlineDetails>
            {filePath && (
              <ToolArgsBlock size="compact">
                <span className="truncate">{filePath}</span>
                {(offset !== undefined || limit !== undefined) && (
                  <span className="shrink-0 text-theme-text-tertiary">
                    :L{startLine}
                    {endLine ? `-${endLine}` : ""}
                  </span>
                )}
              </ToolArgsBlock>
            )}
            {imageBlocks.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {imageBlocks.map((block, i) => (
                  <McpBlockPreview key={i} block={block} />
                ))}
              </div>
            )}
            {displayContent && (
              <div className="relative group rounded-md tool-code-block">
                <DeferredCodeMirrorViewer
                  value={displayContent}
                  filePath={filePath}
                  lineNumbers={true}
                  fontSize="0.75rem"
                  startLine={startLine}
                  highlightLineRange={
                    offset !== undefined || limit !== undefined
                      ? { from: startLine, to: endLine ?? startLine }
                      : undefined
                  }
                />
                <ToolHoverCopyButton
                  text={displayContent}
                  position="panelCompact"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
              </div>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ReadFileItem };
