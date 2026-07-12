import { memo, useMemo } from "react";
import { clsx } from "clsx";
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
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { DetailSection } from "./DetailSection";
import { TYPE_STYLES, TYPE_DOTS } from "../../../panels/MemoryPanel/constants";

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

const MemoryStoreItem = memo(function MemoryStoreItem({
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
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
  const errorMessage = parsed?.error || "";

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
    if (action === "delete") {
      return t("chat.message.toolMemoryDelete");
    }
    if (title) {
      const truncated = title.length > 28 ? title.slice(0, 25) + "…" : title;
      return `${t("chat.message.toolMemoryStore")} ${truncated}`;
    }
    return t("chat.message.toolMemoryStore");
  }, [action, title, t]);

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {/* Status banner */}
      {isSuccess && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-[color-mix(in_srgb,var(--theme-success)_7%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-success)_16%,var(--theme-border))]">
          <CheckCircle2
            size={14}
            className="text-[var(--theme-success)] shrink-0"
          />
          <span className="text-xs sm:text-sm text-theme-text flex-1">
            {action === "delete"
              ? t("chat.message.toolMemoryDeleteSuccess")
              : isUpdate
                ? t("chat.message.toolMemoryStoreUpdated")
                : t("chat.message.toolMemoryStoreNew")}
          </span>
          {resultMessage && (
            <span className="text-[10px] text-theme-text-tertiary truncate max-w-[200px]">
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
          <span className="text-xs sm:text-sm text-theme-text flex-1">
            {action === "delete"
              ? t("chat.message.toolMemoryDeleteFailed")
              : t("chat.message.toolMemoryStoreRejected")}
          </span>
          <span className="text-[10px] text-theme-text-tertiary truncate max-w-[200px]">
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
            <span className="text-[10px] text-theme-text-tertiary tabular-nums">
              {content.length > 1000
                ? `${Math.round(content.length / 100) / 10}k`
                : `${content.length}`}
            </span>
          }
        >
          <div className="rounded-xl overflow-hidden border border-theme-border bg-theme-bg shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
            {/* Title */}
            {title && (
              <div className="px-3.5 pt-3 pb-1.5">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-theme-text truncate leading-snug">
                    {title}
                  </h4>
                  {memoryType && (
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 px-2 py-[3px] rounded-md text-[10px] font-medium shrink-0",
                        TYPE_STYLES[memoryType] || TYPE_STYLES.user,
                      )}
                    >
                      <span
                        className={clsx(
                          "w-1.5 h-1.5 rounded-full",
                          TYPE_DOTS[memoryType] || TYPE_DOTS.user,
                        )}
                      />
                      {(() => {
                        const Icon = getTypeIcon(memoryType);
                        return <Icon size={10} className="opacity-60" />;
                      })()}
                      {t(`memory.type.${memoryType}`, memoryType)}
                    </span>
                  )}
                  {isUpdate && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-[2px] rounded-md text-[9px] font-medium bg-amber-100/70 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
                      <RefreshCw size={8} className="opacity-60" />
                      {t("chat.message.toolMemoryStoreUpdated")}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Summary */}
            {summary && (
              <div className="px-3.5 pb-2">
                <p className="text-[11px] sm:text-xs text-theme-text-secondary/80 leading-relaxed">
                  {summary}
                </p>
              </div>
            )}

            {/* Content body */}
            <pre className="px-3.5 pb-3 text-[11px] sm:text-xs text-theme-text-secondary leading-relaxed whitespace-pre-wrap break-words overflow-y-auto max-h-60">
              {content.length > 500 ? content.slice(0, 497) + "…" : content}
            </pre>

            {/* Tags + Context footer */}
            {(tags.length > 0 || context) && (
              <div className="px-3.5 pb-3 flex items-center gap-2 flex-wrap">
                {tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {tags.slice(0, 6).map((tag, i) => (
                      <span
                        key={i}
                        className={clsx(
                          "inline-flex items-center gap-1 px-2 py-[2px] rounded-lg text-[10px] font-medium",
                          i === 0
                            ? "bg-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-bg-card))] text-theme-text ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_20%,var(--theme-border))]"
                            : "bg-theme-bg text-theme-text-secondary ring-1 ring-theme-border",
                        )}
                      >
                        <Tag
                          size={7}
                          className={clsx(
                            i === 0 ? "opacity-60" : "opacity-40",
                          )}
                        />
                        {tag}
                      </span>
                    ))}
                    {tags.length > 6 && (
                      <span className="text-[10px] text-theme-text-tertiary px-1">
                        +{tags.length - 6}
                      </span>
                    )}
                  </div>
                )}
                {context && (
                  <span className="inline-flex items-center gap-1 px-2 py-[2px] rounded-lg text-[10px] font-medium bg-theme-bg text-theme-text-secondary ring-1 ring-theme-border">
                    {context}
                  </span>
                )}
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
            <div className="text-[10px] text-theme-text-tertiary">
              {t("chat.message.toolMemoryDeleteTarget")}
            </div>
            <div className="text-xs font-mono text-theme-text-secondary truncate mt-0.5">
              {memoryIdArg}
            </div>
          </div>
        </div>
      )}

      {/* Memory ID (result) */}
      {(resultMemoryId || existingMemoryId) && (
        <div className="flex items-center gap-2 px-3.5">
          <span className="text-[10px] text-theme-text-tertiary">ID</span>
          <span className="text-[10px] font-mono text-theme-text-secondary truncate flex-1">
            {resultMemoryId || existingMemoryId}
          </span>
          <ToolHoverCopyButton
            text={resultMemoryId || existingMemoryId}
            position="result"
            size={10}
            copyButtonClassName="!bg-theme-bg/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}

      {/* Raw result fallback */}
      {result && !parsed && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {(() => {
            const text = extractText(result);
            return text.length > 600 ? text.slice(0, 597) + "…" : text;
          })()}
          <ToolHoverCopyButton
            text={extractText(result)}
            position="result"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </pre>
      )}
    </div>
  );

  // ── Inline (compact) view ──

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
        label={pillLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title:
              action === "delete"
                ? t("chat.message.toolMemoryDelete")
                : t("chat.message.toolMemoryStore"),
            icon:
              action === "delete" ? <Trash2 size={16} /> : <Brain size={16} />,
            status: pillStatus,
            subtitle: title
              ? title.length > 80
                ? title.slice(0, 77) + "…"
                : title
              : undefined,
            children: detailContent,
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
                  <div className="text-xs text-theme-text font-medium truncate">
                    {title}
                  </div>
                )}
                <div className="text-[10px] text-theme-text-tertiary truncate mt-0.5">
                  {summary || content.slice(0, 60)}
                </div>
                {(tags.length > 0 || memoryType) && (
                  <div className="flex items-center gap-1 mt-1.5">
                    {memoryType && (
                      <span
                        className={clsx(
                          "inline-flex items-center px-1.5 py-[1px] rounded text-[9px] font-medium",
                          TYPE_STYLES[memoryType] || TYPE_STYLES.user,
                        )}
                      >
                        {t(`memory.type.${memoryType}`, memoryType)}
                      </span>
                    )}
                    {tags.length > 0 && (
                      <span className="text-[9px] text-theme-text-tertiary">
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
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border text-[10px] font-mono text-theme-text-secondary truncate">
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
                <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
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
