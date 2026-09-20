import { memo, useMemo } from "react";
import { FileText, ImageIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, formatFileSize } from "../../../common";
import { DeferredCodeMirrorViewer } from "../../../common/DeferredCodeMirrorViewer";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import {
  stripLineNumbers,
  readFileStartLine,
  readLineRangeLabel,
  extractText,
  type McpMultiModalResult,
  type McpContentBlock,
} from "./toolUtils";
import { McpBlockPreview } from "./McpBlockPreview";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { useImagePreviewFallback } from "./imagePreviewFallback";
import { extractReadFileImageResult } from "./readFileImageResult";
import { buildChatThumbUrl } from "../../../../utils/chatThumbs";

/**
 * 二进制 read_file 拦截结果（图片）：面板内大图 + 文件名/大小落款，
 * 点击进查看器；替代原先的裸 JSON 文本。
 */
function ReadFileImagePreview({
  imageResult,
  eager,
  compact,
  onOpen,
}: {
  imageResult: { url: string; name: string; size?: number };
  eager?: boolean;
  compact?: boolean;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  return (
    <figure className="overflow-hidden rounded-lg border border-theme-border bg-theme-bg">
      <button
        type="button"
        className="block w-full bg-theme-bg-elevated cursor-zoom-in"
        onClick={onOpen}
        aria-label={t("chat.message.openImage", "Open image")}
      >
        <ImageWithSkeleton
          src={imageResult.url}
          thumbSrc={buildChatThumbUrl(imageResult.url)}
          alt={imageResult.name}
          skipUrlResolve
          loading={eager ? "eager" : "lazy"}
          className={`mx-auto w-full object-contain ${compact ? "max-h-72" : "max-h-[70dvh]"}`}
          wrapperClassName="!my-0 !shadow-none"
        />
      </button>
      <figcaption className="flex items-center gap-2 border-t border-theme-border px-3 py-2 text-12 text-theme-text-secondary">
        <ImageIcon size={14} className="shrink-0 text-theme-text-tertiary" />
        <span className="min-w-0 flex-1 truncate">{imageResult.name}</span>
        {imageResult.size != null && (
          <span className="shrink-0 text-theme-text-tertiary">
            {formatFileSize(imageResult.size)}
          </span>
        )}
      </figcaption>
    </figure>
  );
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function ReadFileDetail({ args, result }: ToolDetailProps) {
  const { openImage, viewer } = useImagePreviewFallback();
  const filePath = (args.file_path as string) || "";
  const offset = args.offset as number | undefined;
  const limit = args.limit as number | undefined;
  const startLine = readFileStartLine(offset);
  const endLine = limit ? startLine + limit - 1 : undefined;
  const lineRange = readLineRangeLabel(offset, limit);

  const imageResult = useMemo(
    () => extractReadFileImageResult(result),
    [result],
  );

  const displayContent = useMemo(() => {
    if (imageResult) return "";
    const raw = extractText(result);
    return raw ? stripLineNumbers(raw) : "";
  }, [result, imageResult]);

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

  return (
    <div className="p-4 sm:p-5 space-y-3 tool-panel-content">
      <ToolArgsBlock size="detail">
        <span className="truncate">{filePath}</span>
        {lineRange && (
          <span className="shrink-0 text-theme-text-tertiary">{lineRange}</span>
        )}
      </ToolArgsBlock>
      {imageResult && (
        <ReadFileImagePreview
          imageResult={imageResult}
          eager
          onOpen={() => openImage(imageResult.url, imageResult.name)}
        />
      )}
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
      {viewer}
    </div>
  );
}

const ReadFileItem = memo(function ReadFileItem({
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
  const { openImage, viewer } = useImagePreviewFallback();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );
  const filePath = (args.file_path as string) || "";
  const fileName = filePath.split("/").pop() || filePath;
  const offset = args.offset as number | undefined;
  const limit = args.limit as number | undefined;
  const startLine = readFileStartLine(offset);
  const endLine = limit ? startLine + limit - 1 : undefined;
  const lineRange = readLineRangeLabel(offset, limit);

  const imageResult = useMemo(
    () => extractReadFileImageResult(result),
    [result],
  );

  const displayContent = useMemo(() => {
    if (imageResult) return "";
    const raw = extractText(result);
    return raw ? stripLineNumbers(raw) : "";
  }, [result, imageResult]);

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

  const hasContent =
    !!displayContent || imageBlocks.length > 0 || !!imageResult;
  // 参数生成中（无 result）也允许打开面板：实时等待读取结果
  const canOpenPanel = hasContent || isPending || !!filePath;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolRead")} ${filePath || ""}`,
    args,
    { isPending, result },
  );

  const detailContent = canOpenPanel && (
    <ReadFileDetail
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
        icon={<FileText size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        suffix={
          lineRange ? (
            <span className="shrink-0 font-mono font-medium opacity-60 leading-none">
              {lineRange}
            </span>
          ) : undefined
        }
        variant="tool"
        formatLabel={false}
        expandable={canOpenPanel}
        onPanelOpen={() => {
          if (!canOpenPanel) return;
          openToolLivePanel({
            id,
            title: `${t("chat.message.toolRead")} ${
              fileName || filePath
            }${lineRange}`,
            icon: <FileText size={16} />,
            status,
            subtitle: filePath,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ReadFileDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {hasContent && (
          <ToolInlineDetails>
            {filePath && (
              <ToolArgsBlock size="compact">
                <span className="truncate">{filePath}</span>
                {lineRange && (
                  <span className="shrink-0 text-theme-text-tertiary">
                    {lineRange}
                  </span>
                )}
              </ToolArgsBlock>
            )}
            {imageResult && (
              <ReadFileImagePreview
                imageResult={imageResult}
                compact
                onOpen={() => openImage(imageResult.url, imageResult.name)}
              />
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
      {viewer}
    </>
  );
});

export { ReadFileItem };
