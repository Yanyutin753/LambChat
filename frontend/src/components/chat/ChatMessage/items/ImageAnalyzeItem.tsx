import { memo, useMemo } from "react";
import { Eye, ImageIcon, MessageSquareText, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { extractText } from "./toolUtils";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
}

function getImageUrls(args: Record<string, unknown>): string[] {
  const rawUrls = args.image_urls;
  if (Array.isArray(rawUrls)) {
    return rawUrls.filter((url): url is string => typeof url === "string");
  }
  return typeof rawUrls === "string" ? [rawUrls] : [];
}

function getAnalysisText(result: string | Record<string, unknown> | undefined) {
  const text = extractText(result);
  if (!text) return "";
  try {
    const parsed = JSON.parse(text) as { analysis?: unknown; error?: unknown };
    if (typeof parsed.analysis === "string") return parsed.analysis;
    if (typeof parsed.error === "string") return parsed.error;
  } catch {
    // Plain-text tool output.
  }
  return text;
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function ImageAnalyzeDetail({ args, result }: ToolDetailProps) {
  const imageUrls = getImageUrls(args);
  const prompt = (args.prompt as string) || "";
  const analysis = useMemo(() => getAnalysisText(result), [result]);

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {prompt && (
        <ToolArgsBlock size="detail" wrap>
          <MessageSquareText
            size={14}
            className="shrink-0 text-amber-500 dark:text-amber-400"
          />
          <span className="break-words">{prompt}</span>
        </ToolArgsBlock>
      )}
      {imageUrls.length > 0 && (
        <div className="space-y-2">
          {imageUrls.map((url, index) => (
            <ToolArgsBlock key={`${url}-${index}`} size="detail" wrap>
              <ImageIcon
                size={14}
                className="shrink-0 text-teal-500 dark:text-teal-400"
              />
              <span className="break-all">{url}</span>
            </ToolArgsBlock>
          ))}
        </div>
      )}
      {analysis && (
        <div className="relative group rounded-lg tool-code-block">
          <div
            className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
            style={{ color: "var(--theme-text)" }}
          >
            <MarkdownContent content={analysis} />
          </div>
          <ToolHoverCopyButton
            text={analysis}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}
    </div>
  );
}

const ImageAnalyzeItem = memo(function ImageAnalyzeItem({
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
  const imageUrls = getImageUrls(args);
  const prompt = (args.prompt as string) || "";
  const analysis = useMemo(() => getAnalysisText(result), [result]);
  // 参数生成中（无结果）也允许打开面板：实时等待分析结果
  const canExpand =
    imageUrls.length > 0 || !!prompt || !!analysis || !!isPending;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const analysisBlock = analysis ? (
    <div className="relative group rounded-lg tool-code-block">
      <div
        className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
        style={{ color: "var(--theme-text)" }}
      >
        <MarkdownContent content={analysis} />
      </div>
      <ToolHoverCopyButton
        text={analysis}
        size={14}
        position="panel"
        copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
      />
    </div>
  ) : null;

  const detailContent = canExpand && (
    <ImageAnalyzeDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  const imageSummary =
    imageUrls.length > 1
      ? t("chat.message.toolImageAnalyzeCount", { count: imageUrls.length })
      : imageUrls[0] || "";

  return (
    <CollapsiblePill
      status={status}
      icon={<ScanSearch size={12} className="shrink-0 opacity-50" />}
      label={`${t("chat.message.toolImageAnalyze")} ${
        prompt ? truncate(prompt, 56) : truncate(imageSummary, 56)
      }`}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title: t("chat.message.toolImageAnalyze"),
          icon: <Eye size={16} />,
          status,
          subtitle: imageSummary || prompt || undefined,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <ImageAnalyzeDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {prompt && (
            <ToolArgsBlock size="compact" wrap>
              <MessageSquareText
                size={12}
                className="shrink-0 text-amber-500 dark:text-amber-400"
              />
              <span className="break-words">{truncate(prompt, 160)}</span>
            </ToolArgsBlock>
          )}
          {imageUrls.slice(0, 3).map((url, index) => (
            <ToolArgsBlock key={`${url}-${index}`} size="compact" wrap>
              <ImageIcon
                size={12}
                className="shrink-0 text-teal-500 dark:text-teal-400"
              />
              <span className="break-all">{truncate(url, 140)}</span>
            </ToolArgsBlock>
          ))}
          {imageUrls.length > 3 && (
            <div className="text-[11px] text-theme-text-tertiary">
              {t("chat.message.toolMoreFiles", { count: imageUrls.length - 3 })}
            </div>
          )}
          {analysisBlock}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { ImageAnalyzeItem };
