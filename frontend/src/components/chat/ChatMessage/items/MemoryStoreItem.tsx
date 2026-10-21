import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import {
  Brain,
  Save,
  Trash2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Tag,
  User,
  MessageSquare,
  FolderGit2,
  BookOpen,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton } from "../../../common";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { DetailSection } from "./DetailSection";
import { buildPanelSummary } from "../panelSummary";

// ── Types ────────────────────────────────────────────────────────────────

type StoreAction = "retain" | "delete";

interface MemoryStoreResult {
  success: boolean;
  memory_id?: string;
  memory_type?: string;
  message?: string;
  updated_existing?: boolean;
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function getTypeIcon(type: string): LucideIcon {
  switch (type) {
    case "user":
      return User;
    case "feedback":
      return MessageSquare;
    case "project":
      return FolderGit2;
    case "reference":
      return BookOpen;
    default:
      return Tag;
  }
}

// ── MemoryStoreItem ─────────────────────────────────────────────────────

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（存储结果到达即刷新） */
function MemoryStoreDetail({
  args,
  result,
  success,
  toolName,
}: ToolDetailProps & { toolName?: string }) {
  const { t } = useTranslation();

  const action: StoreAction =
    toolName === "memory_delete" ? "delete" : "retain";

  // Args
  const content = (args.content as string) || "";
  const title = (args.title as string) || "";
  const summary = (args.summary as string) || "";
  const context = (args.context as string) || "";
  const tags: string[] = (args.tags as string[]) || [];
  const memoryIdArg = (args.memory_id as string) || "";
  const existingMemoryId = (args.existing_memory_id as string) || "";

  // Parsed result
  const parsed = useMemo((): MemoryStoreResult | null => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const isSuccess = parsed ? parsed.success : success;
  const isError = parsed
    ? !parsed.success && !!parsed.error
    : !success && !!result;
  const isUpdate = !!parsed?.updated_existing;
  const resultMemoryId = parsed?.memory_id || "";
  const memoryType = parsed?.memory_type || "";
  const resultMessage = parsed?.message || "";
  const TypeIcon = getTypeIcon(memoryType);
  const errorMessage = parsed?.error || "";

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {/* Status banner */}
      {isSuccess && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-[color-mix(in_srgb,var(--theme-success)_7%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-success)_16%,var(--theme-border))]">
          <CheckCircle2
            size={14}
            className="text-[var(--theme-success)] shrink-0"
          />
          <span className="text-12 sm:text-14 text-theme-text flex-1">
            {action === "delete"
              ? t("chat.message.toolMemoryDeleteSuccess")
              : isUpdate
                ? t("chat.message.toolMemoryStoreUpdated")
                : t("chat.message.toolMemoryStoreNew")}
          </span>
          {resultMessage && (
            <span className="text-10 text-theme-text-tertiary truncate max-w-[200px]">
              {resultMessage}
            </span>
          )}
        </div>
      )}

      {isError && errorMessage && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-[color-mix(in_srgb,var(--theme-error)_7%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-error)_16%,var(--theme-border))]">
          <AlertCircle
            size={14}
            className="text-[var(--theme-error)] shrink-0"
          />
          <span className="text-12 sm:text-14 text-theme-text flex-1">
            {action === "delete"
              ? t("chat.message.toolMemoryDeleteFailed")
              : t("chat.message.toolMemoryStoreRejected")}
          </span>
          <span className="text-10 text-theme-text-tertiary truncate max-w-[200px]">
            {errorMessage}
          </span>
        </div>
      )}

      {/* Retain: content card */}
      {action === "retain" && content && (
        <DetailSection
          title={t("chat.message.toolMemoryContent")}
          icon={<Save size={12} />}
          defaultExpanded={true}
          badge={
            <span className="text-10 text-theme-text-tertiary tabular-nums">
              {content.length > 1000
                ? `${Math.round(content.length / 100) / 10}k`
                : `${content.length}`}
            </span>
          }
        >
          <div className="space-y-3">
            {/* Title */}
            {title && (
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-14 font-serif font-semibold text-theme-text break-words min-w-0 leading-snug">
                    {title}
                  </h4>
                  {memoryType && (
                    <TagBadge icon={<TypeIcon />}>
                      {t(`memory.type.${memoryType}`, memoryType)}
                    </TagBadge>
                  )}
                  {isUpdate && (
                    <TagBadge icon={<RefreshCw />}>
                      {t("chat.message.toolMemoryStoreUpdated")}
                    </TagBadge>
                  )}
                </div>
              </div>
            )}

            {/* Summary */}
            {summary && (
              <div className="min-w-0">
                <p className="text-11 sm:text-12 text-theme-text-secondary/80 leading-relaxed">
                  {summary}
                </p>
              </div>
            )}

            {/* Content body */}
            <div className="text-12 text-theme-text-secondary leading-relaxed whitespace-pre-wrap break-words">
              {content}
            </div>

            {/* Tags + Context footer */}
            {(tags.length > 0 || context) && (
              <div className="flex items-center gap-1.5 flex-wrap">
                {tags.map((tag, i) => (
                  <TagBadge key={i} icon={<Tag />}>
                    {tag}
                  </TagBadge>
                ))}
                {context && <TagBadge>{context}</TagBadge>}
              </div>
            )}
          </div>
        </DetailSection>
      )}

      {/* Delete: memory ID info */}
      {action === "delete" && memoryIdArg && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-theme-bg border border-theme-border">
          <Trash2 size={13} className="text-theme-text-tertiary shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-10 text-theme-text-tertiary">
              {t("chat.message.toolMemoryDeleteTarget")}
            </div>
            <div className="text-12 font-mono text-theme-text-secondary truncate mt-0.5">
              {memoryIdArg}
            </div>
          </div>
        </div>
      )}

      {/* Memory ID (result) */}
      {(resultMemoryId || existingMemoryId) && (
        <div className="flex items-center gap-2">
          <span className="text-10 text-theme-text-tertiary">ID</span>
          <span className="text-10 font-mono text-theme-text-secondary min-w-0 truncate flex-1">
            {resultMemoryId || existingMemoryId}
          </span>
          <CopyButton
            text={resultMemoryId || existingMemoryId}
            size={10}
            className="shrink-0 text-theme-text-tertiary hover:text-theme-text-secondary"
          />
        </div>
      )}

      {/* Raw result fallback */}
      {result && !parsed && (
        <pre className="group/result relative text-12 text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {(() => {
            const text = extractText(result);
            return text;
          })()}
          <ToolHoverCopyButton text={extractText(result)} position="result" />
        </pre>
      )}
    </div>
  );
}

const MemoryStoreItem = memo(function MemoryStoreItem({
  id,
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  toolName: string;
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

  const action: StoreAction =
    toolName === "memory_delete" ? "delete" : "retain";

  // Args
  const content = (args.content as string) || "";
  const title = (args.title as string) || "";
  const summary = (args.summary as string) || "";
  const tags: string[] = (args.tags as string[]) || [];
  const memoryIdArg = (args.memory_id as string) || "";

  // Parsed result
  const parsed = useMemo((): MemoryStoreResult | null => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const isSuccess = parsed ? parsed.success : success;
  const isError = parsed
    ? !parsed.success && !!parsed.error
    : !success && !!result;
  const memoryType = parsed?.memory_type || "";

  const canExpand =
    (action === "retain" && content.length > 0) ||
    (action === "delete" && memoryIdArg.length > 0) ||
    !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : isSuccess
        ? "success"
        : isError
          ? "error"
          : "idle";

  // ── Pill labels ──

  const pillLabel = useMemo(() => {
    const subject =
      action === "delete"
        ? memoryIdArg
        : title || summary || content.split("\n")[0];
    const actionLabel = t(
      action === "delete"
        ? "chat.message.toolMemoryDelete"
        : "chat.message.toolMemoryStore",
    );
    return subject ? `${actionLabel} ${subject}` : actionLabel;
  }, [action, memoryIdArg, title, summary, content, t]);

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <MemoryStoreDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
      toolName={toolName}
    />
  );

  // ── Inline (compact) view ──

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={
          action === "delete" ? (
            <Trash2 size={12} className="shrink-0 opacity-50" />
          ) : (
            <Brain size={12} className="shrink-0 opacity-50" />
          )
        }
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title:
              action === "delete"
                ? t("chat.message.toolMemoryDelete")
                : t("chat.message.toolMemoryStore"),
            icon:
              action === "delete" ? <Trash2 size={16} /> : <Brain size={16} />,
            status: pillStatus,
            subtitle: buildPanelSummary(
              title || summary || content || memoryIdArg,
            ),
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <MemoryStoreDetail
                {...toolDetailPropsFromPanelData(data)}
                toolName={toolName}
              />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {/* Retain compact */}
            {action === "retain" && content && (
              <div className="rounded-lg px-2.5 py-2 bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors">
                {title && (
                  <div className="text-12 text-theme-text font-medium truncate">
                    {title}
                  </div>
                )}
                <div className="text-10 text-theme-text-tertiary truncate mt-0.5">
                  {summary || content.slice(0, 60)}
                </div>
                {(tags.length > 0 || memoryType) && (
                  <div className="flex items-center gap-1 mt-1.5">
                    {memoryType && (
                      <TagBadge>
                        {t(`memory.type.${memoryType}`, memoryType)}
                      </TagBadge>
                    )}
                    {tags.length > 0 && (
                      <span className="text-9 text-theme-text-tertiary">
                        {tags.slice(0, 3).join(", ")}
                        {tags.length > 3 && "…"}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Delete compact */}
            {action === "delete" && memoryIdArg && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border text-10 font-mono text-theme-text-secondary truncate">
                <Trash2
                  size={10}
                  className="text-theme-text-tertiary shrink-0"
                />
                {memoryIdArg}
              </div>
            )}

            {/* Fallback */}
            {result &&
              !parsed &&
              !(action === "retain" && content) &&
              !(action === "delete" && memoryIdArg) && (
                <pre className="group/result relative text-12 text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
                  {(() => {
                    const text = extractText(result);
                    return text.length > 300 ? text.slice(0, 297) + "…" : text;
                  })()}
                  <ToolHoverCopyButton
                    text={extractText(result)}
                    position="resultCompact"
                  />
                </pre>
              )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { MemoryStoreItem };
