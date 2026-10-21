import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { UserRound, Tag, Sparkles, Zap, MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton } from "../../../common";
import { AgentAvatar } from "../../../common/AgentAvatar";
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
import { MarkdownContent } from "../MarkdownContent";
import { DetailSection } from "./DetailSection";
// ── PersonaDetail ─────────────────────────────────────────────────────

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（人设数据到达即刷新） */
function PersonaDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const personaName = (args.name as string) || "";

  // Backend returns {success, action, preset: {...PersonaPreset}, message}
  const parsed = useMemo(() => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      if (raw?.preset && typeof raw.preset === "object") return raw.preset;
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const displayName = parsed?.name || personaName;
  const description = parsed?.description || "";
  const avatar = parsed?.avatar || (args.avatar as string) || "";
  const tags: string[] = parsed?.tags || (args.tags as string[]) || [];
  const systemPrompt = parsed?.system_prompt || "";
  const starterPrompts: Array<{
    icon?: string | null;
    text: string | Record<string, string>;
  }> = parsed?.starter_prompts || [];
  const skillNames: string[] = parsed?.skill_names || [];
  const statusVal = parsed?.status || "";

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {displayName && (
        <section className="space-y-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="size-10 shrink-0 overflow-hidden rounded-[var(--radius-sm)] bg-theme-bg-subtle flex items-center justify-center">
              <AgentAvatar
                avatar={avatar}
                seed={displayName}
                size={40}
                iconSize={20}
              />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <h3 className="text-16 font-serif font-semibold text-theme-text break-words">
                {displayName}
              </h3>
              {description && (
                <p className="text-14 text-theme-text-secondary leading-relaxed break-words">
                  {description}
                </p>
              )}
              {statusVal && statusVal !== "published" && (
                <span className="text-12 text-theme-text-tertiary">
                  {statusVal}
                </span>
              )}
            </div>
          </div>
          {(tags.length > 0 || skillNames.length > 0) && (
            <div className="flex flex-wrap items-center gap-1.5 text-12 text-theme-text-secondary">
              {tags.map((tag, i) => (
                <TagBadge key={`tag-${i}`} icon={<Tag />}>
                  {tag}
                </TagBadge>
              ))}
              {skillNames.map((skill, i) => (
                <TagBadge key={`skill-${i}`} icon={<Zap />}>
                  {skill}
                </TagBadge>
              ))}
            </div>
          )}
        </section>
      )}

      {/* System Prompt */}
      {systemPrompt && (
        <DetailSection
          title={t("chat.message.systemPrompt", "System Prompt")}
          icon={<Sparkles size={12} />}
          defaultExpanded={false}
          badge={
            <span className="text-10 text-theme-text-tertiary tabular-nums">
              {systemPrompt.length > 1000
                ? `${Math.round(systemPrompt.length / 100) / 10}k`
                : `${systemPrompt.length}`}
            </span>
          }
        >
          <div className="rounded-lg overflow-hidden border border-theme-border bg-theme-bg p-3 sm:p-4 [&_.markdown-content]:text-12 sm:[&_.markdown-content]:text-14 [&_.markdown-content_p:first-child]:mt-0 [&_.markdown-content_p:last-child]:mb-0">
            <MarkdownContent content={systemPrompt} />
          </div>
          <div className="flex justify-end mt-2">
            <CopyButton
              text={systemPrompt}
              size={10}
              className="shrink-0 text-theme-text-tertiary hover:text-theme-text-secondary"
            />
          </div>
        </DetailSection>
      )}

      {/* Starter Prompts */}
      {starterPrompts.length > 0 && (
        <DetailSection
          title={t("chat.message.starterPrompts", "Starter Prompts")}
          icon={<MessageSquare size={12} />}
          defaultExpanded={true}
          badge={
            <span className="text-10 text-theme-text-tertiary tabular-nums">
              {starterPrompts.length}
            </span>
          }
        >
          <div className="space-y-2">
            {starterPrompts.map((sp, i) => {
              const text =
                typeof sp.text === "string"
                  ? sp.text
                  : sp.text?.zh ||
                    sp.text?.en ||
                    Object.values(sp.text)[0] ||
                    "";
              return (
                <div
                  key={i}
                  className={clsx(
                    "flex items-center gap-3 px-3.5 py-2.5 rounded-xl",
                    "bg-theme-bg border border-theme-border",
                    "hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))]",
                    "hover:bg-[color-mix(in_srgb,var(--theme-primary)_5%,var(--theme-bg-card))]",
                    "transition-all duration-200",
                  )}
                >
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-18 shrink-0 bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]">
                    {sp.icon || (
                      <MessageSquare
                        size={14}
                        className="text-[var(--theme-primary)]"
                      />
                    )}
                  </div>
                  <span className="text-14 text-theme-text leading-relaxed line-clamp-2">
                    {text}
                  </span>
                </div>
              );
            })}
          </div>
        </DetailSection>
      )}

      {/* Raw result fallback */}
      {result && !displayName && (
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

// ── PersonaItem ──────────────────────────────────────────────────────

const PersonaItem = memo(function PersonaItem({
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

  const personaName = (args.name as string) || "";

  // Backend returns {success, action, preset: {...PersonaPreset}, message}
  const parsed = useMemo(() => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      if (raw?.preset && typeof raw.preset === "object") return raw.preset;
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const displayName = parsed?.name || personaName;
  const description = parsed?.description || "";
  const avatar = parsed?.avatar || (args.avatar as string) || "";
  const tags: string[] = parsed?.tags || (args.tags as string[]) || [];
  const skillNames: string[] = parsed?.skill_names || [];

  const canExpand =
    !!displayName || !!description || tags.length > 0 || !!result;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <PersonaDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // ── Inline (compact) view ──

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolPersonaPreset")} ${displayName || ""}`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={
          <UserRound
            size={12}
            className="shrink-0 opacity-50 text-amber-500 dark:text-amber-400"
          />
        }
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolPersonaPreset"),
            icon: <UserRound size={16} />,
            status,
            subtitle: displayName || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <PersonaDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {(displayName || avatar) && (
              <div
                className={clsx(
                  "flex items-center gap-2 rounded-lg px-2.5 py-2",
                  "bg-theme-bg border border-theme-border",
                  "hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors",
                )}
              >
                <div
                  className={clsx(
                    "w-6 h-6 rounded-md flex items-center justify-center text-14 leading-none shrink-0 overflow-hidden",
                    "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]",
                  )}
                >
                  <AgentAvatar
                    avatar={avatar}
                    seed={displayName}
                    size={24}
                    iconSize={14}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-12 text-theme-text font-medium truncate">
                    {displayName}
                  </div>
                  {description && (
                    <div className="text-10 text-theme-text-tertiary truncate">
                      {description}
                    </div>
                  )}
                </div>
                {skillNames.length > 0 && (
                  <span className="shrink-0 text-10 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-1.5 py-0.5 rounded-md">
                    {t("chat.message.toolPersonaSkillCount", {
                      count: skillNames.length,
                    })}
                  </span>
                )}
              </div>
            )}
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {tags.slice(0, 8).map((tag, i) => (
                  <TagBadge key={i} icon={<Tag />}>
                    {tag}
                  </TagBadge>
                ))}
              </div>
            )}
            {result && !displayName && (
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

export { PersonaItem };
