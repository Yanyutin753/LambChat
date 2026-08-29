import { memo } from "react";
import { FilePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { DeferredCodeMirrorViewer } from "../../../common/DeferredCodeMirrorViewer";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function WriteFileDetail({ args, result }: ToolDetailProps) {
  const filePath = (args.file_path as string) || "";
  const content = (args.content as string) || "";

  return (
    <div className="p-4 sm:p-5 space-y-3 tool-panel-content">
      <ToolArgsBlock size="detail">
        <span className="truncate">{filePath}</span>
      </ToolArgsBlock>
      {content && (
        <div className="relative group rounded-lg tool-code-block">
          <DeferredCodeMirrorViewer
            value={content}
            filePath={filePath}
            lineNumbers={true}
            fontSize="0.8rem"
          />
          <ToolHoverCopyButton
            text={content}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}
      {result &&
        (() => {
          const text = extractText(result);
          return text ? (
            <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
              {text}
              <ToolHoverCopyButton
                text={text}
                position="result"
                copyButtonClassName="!bg-theme-bg-card/80 !rounded-md"
              />
            </pre>
          ) : null;
        })()}
    </div>
  );
}

const WriteFileItem = memo(function WriteFileItem({
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
  const filePath = (args.file_path as string) || "";
  const fileName = filePath.split("/").pop() || filePath;
  const content = (args.content as string) || "";

  // 参数生成中（无 result）也允许打开面板：实时等待写入结果
  const canExpand = !!content || !!result || isPending || !!filePath;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <WriteFileDetail
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
        icon={<FilePlus size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolWrite")} ${filePath || ""}`}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: `${t("chat.message.toolWrite")} ${fileName || filePath}`,
            icon: <FilePlus size={16} />,
            status,
            subtitle: filePath,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <WriteFileDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <ToolArgsBlock size="compact">
              <span className="truncate">{filePath}</span>
            </ToolArgsBlock>
            {content && (
              <div className="relative group rounded-md tool-code-block">
                <DeferredCodeMirrorViewer
                  value={content}
                  filePath={filePath}
                  lineNumbers={true}
                  fontSize="0.75rem"
                />
                <ToolHoverCopyButton
                  text={content}
                  position="panelCompact"
                  copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
                />
              </div>
            )}
            {result &&
              (() => {
                const text = extractText(result);
                return text ? (
                  <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words mt-1 overflow-y-auto min-w-0">
                    {text}
                    <ToolHoverCopyButton text={text} position="resultCompact" />
                  </pre>
                ) : null;
              })()}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { WriteFileItem };
