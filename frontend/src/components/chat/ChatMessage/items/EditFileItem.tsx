import { memo } from "react";
import { Pencil } from "lucide-react";
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
function EditFileDetail({
  args,
  result,
  success,
  isPending,
  cancelled,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const filePath = (args.file_path as string) || "";
  const oldString = (args.old_string as string) || "";
  const newString = (args.new_string as string) || "";
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  return (
    <div className="p-4 sm:p-5 space-y-3 tool-panel-content">
      <div className="ai-file-diff" data-state={status}>
        <ToolArgsBlock size="detail" className="ai-file-diff__header">
          <Pencil size={14} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate font-mono">{filePath}</span>
        </ToolArgsBlock>
        {oldString && (
          <div className="ai-file-diff__section" data-kind="removed">
            <div className="ai-file-diff__label">
              <span aria-hidden="true">−</span>
              {t("chat.message.toolEditRemoved")}
            </div>
            <div className="ai-file-diff__body relative group tool-diff-removed">
              <DeferredCodeMirrorViewer
                value={oldString}
                filePath={filePath}
                lineNumbers={false}
                fontSize="0.8rem"
                className="[&_.cm-editor]:bg-transparent dark:[&_.cm-editor]:bg-transparent"
              />
              <ToolHoverCopyButton
                text={oldString}
                size={14}
                position="panel"
                copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-red-200 dark:!border-red-800"
              />
            </div>
          </div>
        )}
        {newString && (
          <div className="ai-file-diff__section" data-kind="added">
            <div className="ai-file-diff__label">
              <span aria-hidden="true">+</span>
              {t("chat.message.toolEditAdded")}
            </div>
            <div className="ai-file-diff__body relative group tool-diff-added">
              <DeferredCodeMirrorViewer
                value={newString}
                filePath={filePath}
                lineNumbers={false}
                fontSize="0.8rem"
                className="[&_.cm-editor]:bg-transparent dark:[&_.cm-editor]:bg-transparent"
              />
              <ToolHoverCopyButton
                text={newString}
                size={14}
                position="panel"
                copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-emerald-200 dark:!border-emerald-800"
              />
            </div>
          </div>
        )}
      </div>
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

const EditFileItem = memo(function EditFileItem({
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
  const oldString = (args.old_string as string) || "";
  const newString = (args.new_string as string) || "";

  // 参数生成中（无 result）也允许打开面板：实时等待编辑结果
  const canExpand =
    !!oldString || !!newString || !!result || isPending || !!filePath;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const detailContent = canExpand && (
    <EditFileDetail
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
        icon={<Pencil size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolEdit")} ${filePath || ""}`}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: `${t("chat.message.toolEdit")} ${fileName || filePath}`,
            icon: <Pencil size={16} />,
            status,
            subtitle: filePath,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <EditFileDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            <div
              className="ai-file-diff ai-file-diff--compact"
              data-state={status}
            >
              <ToolArgsBlock size="compact" className="ai-file-diff__header">
                <Pencil size={12} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-mono">
                  {filePath}
                </span>
              </ToolArgsBlock>
              {oldString && (
                <div className="ai-file-diff__section" data-kind="removed">
                  <div className="ai-file-diff__label">
                    <span aria-hidden="true">−</span>
                    {t("chat.message.toolEditRemoved")}
                  </div>
                  <div className="ai-file-diff__body relative group overflow-y-auto tool-diff-removed">
                    <DeferredCodeMirrorViewer
                      value={oldString}
                      filePath={filePath}
                      lineNumbers={false}
                      fontSize="0.75rem"
                      className="[&_.cm-editor]:bg-transparent dark:[&_.cm-editor]:bg-transparent"
                    />
                    <ToolHoverCopyButton
                      text={oldString}
                      position="panelCompact"
                      copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-red-200 dark:!border-red-800"
                    />
                  </div>
                </div>
              )}
              {newString && (
                <div className="ai-file-diff__section" data-kind="added">
                  <div className="ai-file-diff__label">
                    <span aria-hidden="true">+</span>
                    {t("chat.message.toolEditAdded")}
                  </div>
                  <div className="ai-file-diff__body relative group overflow-y-auto tool-diff-added">
                    <DeferredCodeMirrorViewer
                      value={newString}
                      filePath={filePath}
                      lineNumbers={false}
                      fontSize="0.75rem"
                      className="[&_.cm-editor]:bg-transparent dark:[&_.cm-editor]:bg-transparent"
                    />
                    <ToolHoverCopyButton
                      text={newString}
                      position="panelCompact"
                      copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-emerald-200 dark:!border-emerald-800"
                    />
                  </div>
                </div>
              )}
            </div>
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

export { EditFileItem };
