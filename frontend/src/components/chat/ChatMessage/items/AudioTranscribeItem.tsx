import { memo, useMemo } from "react";
import { Mic, Volume2, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
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

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function AudioTranscribeDetail({ args, result }: ToolDetailProps) {
  const url = (args.url as string) || "";
  const language = (args.language as string) || "";
  const model = (args.model as string) || "";
  const transcription = useMemo(() => extractText(result), [result]);

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {url && (
        <ToolArgsBlock size="detail" wrap>
          <Mic
            size={14}
            className="shrink-0 text-violet-500 dark:text-violet-400"
          />
          <span className="truncate">{url}</span>
        </ToolArgsBlock>
      )}

      <div className="flex flex-wrap gap-1.5">
        {language && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs">
            <Languages size={10} className="opacity-60" />
            {language.toUpperCase()}
          </span>
        )}
        {model && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs font-mono">
            <Volume2 size={10} className="opacity-60" />
            {model}
          </span>
        )}
      </div>

      {transcription && (
        <div className="relative group rounded-lg tool-code-block">
          <div
            className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
            style={{ color: "var(--theme-text)" }}
          >
            <MarkdownContent content={transcription} />
          </div>
          <ToolHoverCopyButton
            text={transcription}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
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

  const transcription = useMemo(() => extractText(result), [result]);

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

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Mic size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolAudioTranscribe")} ${
          url.length > 50 ? url.slice(0, 47) + "…" : url
        }`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolAudioTranscribe"),
            icon: <Mic size={16} />,
            status,
            subtitle:
              url.length > 100 ? url.slice(0, 97) + "…" : url || undefined,
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
            <ToolArgsBlock size="compact" wrap>
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
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-10">
                  <Languages size={8} className="opacity-60" />
                  {language.toUpperCase()}
                </span>
              )}
              {model && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-10 font-mono">
                  {model}
                </span>
              )}
            </div>

            {transcription && (
              <div className="relative group rounded-md tool-code-block">
                <div
                  className="prose prose-stone dark:prose-invert max-w-none text-xs leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-2.5"
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

export { AudioTranscribeItem };
