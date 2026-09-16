import { memo, useMemo } from "react";
import { FileScan, FileText, Images, Layers } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";

type ParsedImage = {
  index?: number;
  id?: string;
  url?: string;
  mime_type?: string;
  size?: number;
};

type ParsedResult = {
  markdown: string;
  images: ParsedImage[];
  provider?: string;
  pagesProcessed?: number;
  truncated?: boolean;
  error?: string;
};

function parseDocumentParseResult(
  result: string | Record<string, unknown> | undefined,
): ParsedResult {
  if (!result) return { markdown: "", images: [] };

  let data: Record<string, unknown> | null = null;
  if (typeof result === "string") {
    try {
      const parsed = JSON.parse(result);
      if (parsed && typeof parsed === "object")
        data = parsed as Record<string, unknown>;
    } catch {
      return { markdown: "", images: [] };
    }
  } else {
    data = result;
  }
  if (!data) return { markdown: "", images: [] };

  const markdown = typeof data.markdown === "string" ? data.markdown : "";
  const images = Array.isArray(data.images)
    ? (data.images as ParsedImage[]).filter(
        (image) =>
          image && typeof image === "object" && typeof image.url === "string",
      )
    : [];
  const provider =
    typeof data.provider === "string" ? data.provider : undefined;
  const pagesProcessed =
    typeof data.pages_processed === "number" ? data.pages_processed : undefined;
  const truncated = data.truncated === true;
  const error = typeof data.error === "string" ? data.error : undefined;
  return { markdown, images, provider, pagesProcessed, truncated, error };
}

function DocumentParseImages({ images }: { images: ParsedImage[] }) {
  if (!images.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {images.map((image, position) => (
        <a
          key={`${image.id || image.url || position}`}
          href={image.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-md border border-theme-border overflow-hidden bg-theme-bg-subtle"
        >
          <img
            src={image.url}
            alt={image.id || `image-${position + 1}`}
            loading="lazy"
            className="w-16 h-16 object-cover"
          />
        </a>
      ))}
    </div>
  );
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function DocumentParseDetail({ args, result }: ToolDetailProps) {
  const url = (args.url as string) || "";
  const pages = (args.pages as string) || "";
  const parsed = useMemo(() => parseDocumentParseResult(result), [result]);

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {url && (
        <ToolArgsBlock size="detail" wrap>
          <FileScan
            size={14}
            className="shrink-0 text-sky-500 dark:text-sky-400"
          />
          <span className="truncate">{url}</span>
        </ToolArgsBlock>
      )}

      <div className="flex flex-wrap gap-1.5">
        {parsed.provider && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-12 font-mono">
            <FileText size={10} className="opacity-60" />
            {parsed.provider}
          </span>
        )}
        {pages && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-12 font-mono">
            <Layers size={10} className="opacity-60" />
            {pages}
          </span>
        )}
        {typeof parsed.pagesProcessed === "number" &&
          parsed.pagesProcessed > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-12">
              <Layers size={10} className="opacity-60" />
              {parsed.pagesProcessed}
            </span>
          )}
        {parsed.images.length > 0 && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-12">
            <Images size={10} className="opacity-60" />
            {parsed.images.length}
          </span>
        )}
      </div>

      {parsed.markdown && (
        <div className="relative group rounded-lg tool-code-block">
          <div
            className="prose prose-stone dark:prose-invert max-w-none text-14 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
            style={{ color: "var(--theme-text)" }}
          >
            <MarkdownContent content={parsed.markdown} />
          </div>
          <ToolHoverCopyButton
            text={parsed.markdown}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}

      <DocumentParseImages images={parsed.images} />
    </div>
  );
}

const DocumentParseItem = memo(function DocumentParseItem({
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

  const url = (args.url as string) || "";
  const pages = (args.pages as string) || "";
  const parsed = useMemo(() => parseDocumentParseResult(result), [result]);
  const filename = url.split("/").pop() || url;

  // 参数生成中（无解析结果）也允许打开面板：实时等待解析结果
  const canExpand = !!url || !!parsed.markdown || !!isPending;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <DocumentParseDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolDocumentParse")} ${
      filename.length > 50 ? filename.slice(0, 47) + "…" : filename
    }`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<FileScan size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolDocumentParse"),
            icon: <FileScan size={16} />,
            status,
            subtitle:
              url.length > 100 ? url.slice(0, 97) + "…" : url || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <DocumentParseDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <ToolArgsBlock size="compact" wrap>
              <FileScan
                size={12}
                className="shrink-0 text-sky-500 dark:text-sky-400"
              />
              <span className="truncate">
                {url.length > 100 ? url.slice(0, 97) + "…" : url}
              </span>
            </ToolArgsBlock>

            <div className="flex flex-wrap gap-1">
              {pages && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-10 font-mono">
                  <Layers size={8} className="opacity-60" />
                  {pages}
                </span>
              )}
              {typeof parsed.pagesProcessed === "number" &&
                parsed.pagesProcessed > 0 && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-10">
                    <Layers size={8} className="opacity-60" />
                    {parsed.pagesProcessed}
                  </span>
                )}
              {parsed.images.length > 0 && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-10">
                  <Images size={8} className="opacity-60" />
                  {parsed.images.length}
                </span>
              )}
            </div>

            {parsed.markdown && (
              <div className="relative group rounded-md tool-code-block">
                <div
                  className="prose prose-stone dark:prose-invert max-w-none text-12 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-2.5"
                  style={{ color: "var(--theme-text)" }}
                >
                  <MarkdownContent
                    content={
                      parsed.markdown.length > 2000
                        ? parsed.markdown.slice(0, 2000) + "\n..."
                        : parsed.markdown
                    }
                  />
                </div>
                <ToolHoverCopyButton
                  text={parsed.markdown}
                  position="panelCompact"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
              </div>
            )}

            <DocumentParseImages images={parsed.images.slice(0, 6)} />
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { DocumentParseItem };
