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

  return (
    <CollapsiblePill
      status={
        isPending
          ? "loading"
          : cancelled
            ? "cancelled"
            : success
              ? "success"
              : "error"
      }
      icon={<FileText size={12} className="shrink-0 opacity-50" />}
      label={`${t("chat.message.toolRead")} ${fileName || ""}`}
      variant="tool"
      expandable={hasContent}
    >
      {hasContent && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 max-h-80 overflow-hidden min-w-0">
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
            <div className="max-h-64 overflow-y-auto rounded-md border border-stone-200/60 dark:border-stone-700/50">
              <CodeMirrorViewer
                value={displayContent}
                filePath={filePath}
                lineNumbers={false}
                maxHeight="16rem"
                fontSize="0.75rem"
              />
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
});

export { ReadFileItem };
