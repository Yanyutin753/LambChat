import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import { Mic, Volume2, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";

function transcriptionText(
  result: string | Record<string, unknown> | undefined,
) {
  if (result && typeof result === "object" && typeof result.text === "string") {
    return result.text;
  }
  const text = extractText(result);
  try {
    const data: unknown = JSON.parse(text);
    if (
      data &&
      typeof data === "object" &&
      "success" in data &&
      data.success === true &&
      "text" in data &&
      typeof data.text === "string"
    ) {
      return data.text;
    }
  } catch {
    // Plain transcripts remain valid tool results.
  }
  return text;
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function AudioTranscribeDetail({ args, result }: ToolDetailProps) {
  const url = (args.url as string) || "";
  const language = (args.language as string) || "";
  const model = (args.model as string) || "";
  const transcription = useMemo(() => transcriptionText(result), [result]);

  return (
    <div className="p-4 sm:p-5 tool-panel-content">
      {url && (
        <ToolArgsBlock size="detail" copyText={url} wrap>
          <Mic
            size={14}
            className="shrink-0 text-violet-500 dark:text-violet-400"
          />
          <span className="truncate">{url}</span>
        </ToolArgsBlock>
      )}

      {(language || model) && (
        <div className="flex flex-wrap gap-1.5">
          {language && (
            <TagBadge icon={<Languages />}>{language.toUpperCase()}</TagBadge>
          )}
          {model && (
            <TagBadge icon={<Volume2 />} className="font-mono">
              {model}
            </TagBadge>
          )}
        </div>
      )}

      {transcription && (
        <div className="relative group rounded-lg tool-code-block">
          <div
            className="prose prose-stone dark:prose-invert max-w-none text-14 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
            style={{ color: "var(--theme-text)" }}
          >
            <MarkdownContent content={transcription} />
          </div>
          <ToolHoverCopyButton
            text={transcription}
            size={14}
            position="panel"
          />
        </div>
      )}
    </div>
  );
}

const AudioTranscribeItem = memo(function AudioTranscribeItem({
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
  const language = (args.language as string) || "";
  const model = (args.model as string) || "";

  const transcription = useMemo(() => transcriptionText(result), [result]);

  // 参数生成中（无转写文本）也允许打开面板：实时等待转写结果
  const canExpand = !!url || !!transcription || !!isPending;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <AudioTranscribeDetail
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
    `${t("chat.message.toolAudioTranscribe")} ${url}`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Mic size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolAudioTranscribe"),
            icon: <Mic size={16} />,
            status,
            subtitle: url || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <AudioTranscribeDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <ToolArgsBlock size="compact" copyText={url} wrap>
              <Mic
                size={12}
                className="shrink-0 text-violet-500 dark:text-violet-400"
              />
              <span className="truncate">
                {url.length > 100 ? url.slice(0, 97) + "…" : url}
              </span>
            </ToolArgsBlock>

            <div className="flex flex-wrap gap-1">
              {language && (
                <TagBadge icon={<Languages />}>
                  {language.toUpperCase()}
                </TagBadge>
              )}
              {model && <TagBadge className="font-mono">{model}</TagBadge>}
            </div>

            {transcription && (
              <div className="relative group rounded-md tool-code-block">
                <div
                  className="prose prose-stone dark:prose-invert max-w-none text-12 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-2.5"
                  style={{ color: "var(--theme-text)" }}
                >
                  <MarkdownContent
                    content={
                      transcription.length > 2000
                        ? transcription.slice(0, 2000) + "\n..."
                        : transcription
                    }
                  />
                </div>
                <ToolHoverCopyButton
                  text={transcription}
                  position="panelCompact"
                />
              </div>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { AudioTranscribeItem };
