import { memo, useMemo } from "react";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { CodeMirrorViewer } from "../../../common/CodeMirrorViewer";
import {
  stripLineNumbers,
  extractText,
  type McpMultiModalResult,
  type McpContentBlock,
} from "./toolUtils";
import { McpBlockPreview } from "./McpBlockPreview";
import { openPersistentToolPanel } from "./persistentToolPanelState";

const ReadFileItem = memo(function ReadFileItem({
  args,
  result,
  success,
  isPending,
  cancelled,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
}) {
  const { t } = useTranslation();
  const filePath = (args.file_path as string) || "";
  const fileName = filePath.split("/").pop() || filePath;
  const offset = args.offset as number | undefined;
  const limit = args.limit as number | undefined;

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
    <div className="p-4 sm:p-5 space-y-3">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-sm text-stone-500 dark:text-stone-400 font-mono">
        <span className="truncate">{filePath}</span>
        {(offset !== undefined || limit !== undefined) && (
          <span className="shrink-0 text-stone-400 dark:text-stone-500">
            :L{offset ?? 1}
            {limit ? `-${(offset ?? 1) + limit}` : ""}
          </span>
        )}
      </div>
      {imageBlocks.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {imageBlocks.map((block, i) => (
            <McpBlockPreview key={i} block={block} />
          ))}
        </div>
      )}
      {displayContent && (
        <div className="rounded-lg border border-stone-200/60 dark:border-stone-700/50 overflow-hidden">
          <CodeMirrorViewer
            value={displayContent}
            filePath={filePath}
            lineNumbers={true}
            fontSize="0.8rem"
            startLine={Math.max(1, offset ?? 1)}
            highlightLineRange={
              offset !== undefined || limit !== undefined
                ? {
                    from: Math.max(1, offset ?? 1),
                    to: Math.max(1, offset ?? 1) + (limit ?? 0),
                  }
                : undefined
            }
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
        label={`${t("chat.message.toolRead")} ${fileName || ""}`}
        variant="tool"
        expandable={hasContent}
        onPanelOpen={() => {
          if (!hasContent) return;
          openPersistentToolPanel({
            title: `${t("chat.message.toolRead")} ${fileName || filePath}`,
            icon: <FileText size={16} />,
            status,
            subtitle: filePath,
            children: detailContent,
          });
        }}
      >
        {hasContent && (
          <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 max-h-80 overflow-y-auto min-w-0">
            {filePath && (
              <div className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-md bg-stone-100 dark:bg-stone-800 text-xs text-stone-500 dark:text-stone-400 font-mono">
                <span className="truncate">{filePath}</span>
                {(offset !== undefined || limit !== undefined) && (
                  <span className="shrink-0 text-stone-400 dark:text-stone-500">
                    :L{offset ?? 1}
                    {limit ? `-${(offset ?? 1) + limit}` : ""}
                  </span>
                )}
              </div>
            )}
            {imageBlocks.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {imageBlocks.map((block, i) => (
                  <McpBlockPreview key={i} block={block} />
                ))}
              </div>
            )}
            {displayContent && (
              <div className="rounded-md border border-stone-200/60 dark:border-stone-700/50">
                <CodeMirrorViewer
                  value={displayContent}
                  filePath={filePath}
                  lineNumbers={true}
                  fontSize="0.75rem"
                  startLine={offset ?? 1}
                  highlightLineRange={
                    offset !== undefined || limit !== undefined
                      ? { from: offset ?? 1, to: (offset ?? 1) + (limit ?? 0) }
                      : undefined
                  }
                />
              </div>
            )}
          </div>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ReadFileItem };
