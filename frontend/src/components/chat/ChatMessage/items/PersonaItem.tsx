import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { UserRound, Tag, Sparkles, Zap, MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { nameToGradient } from "../../../common/cardUtils";
import { MarkdownContent } from "../MarkdownContent";
import { DetailSection } from "./DetailSection";
import {
  isPersonaImageAvatar,
  isEmojiAvatar,
  getEmojiAvatarUrl,
} from "../../../persona/personaAvatar";
import { getFullUrl } from "../../../../services/api";

// ── Tiny avatar renderer for tool-result cards ──
function ToolAvatarImg({
  src,
  className,
}: {
  src: string;
  className?: string;
}) {
  return (
    <ImageWithSkeleton
      src={src}
      alt=""
      skipUrlResolve
      inline
      className={className}
    />
  );
}

/** Render an avatar value as <img> if it's a URL/emoji, otherwise render fallback. */
function RenderAvatar({
  avatar,
  sizeClass,
  fallback,
}: {
  avatar: string;
  sizeClass?: string;
  fallback: React.ReactNode;
}) {
  if (isEmojiAvatar(avatar)) {
    return (
      <ToolAvatarImg
        src={getEmojiAvatarUrl(avatar)}
        className={clsx("object-cover", sizeClass)}
      />
    );
  }
  if (isPersonaImageAvatar(avatar)) {
    return (
      <ToolAvatarImg
        src={getFullUrl(avatar) ?? avatar}
        className={clsx("object-cover", sizeClass)}
      />
    );
  }
  return <>{fallback}</>;
}

// ── PersonaItem ──────────────────────────────────────────────────────

const PersonaItem = memo(function PersonaItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
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
  const systemPrompt = parsed?.system_prompt || "";
  const starterPrompts: Array<{
    icon?: string | null;
    text: string | Record<string, string>;
  }> = parsed?.starter_prompts || [];
  const skillNames: string[] = parsed?.skill_names || [];
  const statusVal = parsed?.status || "";

  const gradient = useMemo(
    () => (displayName ? nameToGradient(displayName) : null),
    [displayName],
  );

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
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {/* Hero card */}
      {displayName && (
        <div
          className={clsx(
            "rounded-2xl overflow-hidden relative",
            gradient && "shadow-md",
          )}
          style={
            gradient
              ? {
                  boxShadow: `0 2px 16px -4px ${gradient[0]}30, 0 1px 3px rgb(0 0 0 / 0.06)`,
                }
              : undefined
          }
        >
          {/* Gradient border ring */}
          {gradient && (
            <div
              className="absolute inset-0 rounded-2xl p-px"
              style={{
                background: `linear-gradient(135deg, ${gradient[0]}40, ${gradient[1]}20, ${gradient[2]}40)`,
              }}
            >
              <div className="w-full h-full rounded-[calc(1rem-1px)] bg-theme-bg-card" />
            </div>
          )}

          <div className="relative z-10 rounded-2xl overflow-hidden">
            {gradient && (
              <div className="h-20 sm:h-24 relative overflow-hidden">
                {/* Base gradient */}
                <div
                  className="absolute inset-0"
                  style={{
                    background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                  }}
                />
                {/* Decorative mesh pattern */}
                <div
                  className="absolute inset-0 opacity-30"
                  style={{
                    backgroundImage: `radial-gradient(circle at 20% 80%, ${gradient[0]}60 0%, transparent 50%), radial-gradient(circle at 80% 20%, ${gradient[2]}60 0%, transparent 50%)`,
                  }}
                />
                {/* Shimmer sweep */}
                <div
                  className="absolute inset-0 animate-[shimmer_3s_ease-in-out_infinite]"
                  style={{
                    background: `linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.15) 45%, rgba(255,255,255,0.25) 50%, rgba(255,255,255,0.15) 55%, transparent 60%)`,
                    backgroundSize: "200% 100%",
                  }}
                />
                {/* Bottom fade into card */}
                <div className="absolute bottom-0 inset-x-0 h-8 bg-gradient-to-t from-theme-bg-card to-transparent" />
              </div>
            )}
            <div
              className={clsx(
                "relative px-4 sm:px-5 pt-4 pb-4",
                "bg-theme-bg-card",
                !gradient && "pt-5",
              )}
            >
              {/* Avatar + Name row */}
              <div
                className={clsx(
                  "flex items-start gap-3.5",
                  gradient ? "-mt-9 sm:-mt-12" : "",
                )}
              >
                <div
                  className={clsx(
                    "rounded-2xl flex items-center justify-center text-2xl sm:text-3xl leading-none shrink-0 overflow-hidden relative",
                    gradient ? "w-14 h-14 sm:w-16 sm:h-16" : "w-11 h-11",
                  )}
                  style={
                    gradient
                      ? {
                          boxShadow: `0 4px 14px -3px ${gradient[0]}40, 0 2px 6px -1px rgb(0 0 0 / 0.1)`,
                        }
                      : undefined
                  }
                >
                  {/* Gradient ring effect */}
                  {gradient && (
                    <div
                      className="absolute inset-0 rounded-2xl p-[2px]"
                      style={{
                        background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                      }}
                    >
                      <div className="w-full h-full rounded-[calc(1rem-2px)] bg-theme-bg-card" />
                    </div>
                  )}
                  <div
                    className={clsx(
                      "relative z-10 w-full h-full rounded-2xl flex items-center justify-center overflow-hidden",
                      "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]",
                    )}
                  >
                    <RenderAvatar
                      avatar={avatar}
                      sizeClass="w-full h-full"
                      fallback={
                        <UserRound
                          size={gradient ? 28 : 22}
                          className="text-[var(--theme-primary)]"
                        />
                      }
                    />
                  </div>
                </div>
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base sm:text-lg font-bold text-theme-text truncate tracking-tight">
                      {displayName}
                    </h3>
                    {statusVal && statusVal !== "published" && (
                      <span
                        className={clsx(
                          "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase",
                          statusVal === "draft"
                            ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 ring-1 ring-amber-200/50 dark:ring-amber-800/30"
                            : statusVal === "archived"
                              ? "bg-theme-bg-subtle text-theme-text-tertiary ring-1 ring-theme-border"
                              : "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-1 ring-emerald-200/50 dark:ring-emerald-800/30",
                        )}
                      >
                        {statusVal}
                      </span>
                    )}
                  </div>
                  {description && (
                    <p className="text-xs sm:text-[13px] text-theme-text-secondary/80 mt-1 leading-relaxed line-clamp-2">
                      {description}
                    </p>
                  )}
                </div>
              </div>

              {/* Tags + Skills */}
              {(tags.length > 0 || skillNames.length > 0) && (
                <div className="mt-4 space-y-2.5">
                  {tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {tags.map((tag, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all duration-200 bg-theme-bg text-theme-text-secondary ring-1 ring-theme-border hover:ring-theme-border-hover"
                        >
                          <Tag size={9} className="opacity-40" />
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {skillNames.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {skillNames.map((skill, i) => (
                        <span
                          key={i}
                          className={clsx(
                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium",
                            "bg-emerald-100/80 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-1 ring-emerald-200/50 dark:ring-emerald-700/30",
                          )}
                        >
                          <Zap size={9} className="opacity-50" />
                          {skill}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* System Prompt */}
      {systemPrompt && (
        <DetailSection
          title={t("chat.message.systemPrompt", "System Prompt")}
          icon={<Sparkles size={12} />}
          defaultExpanded={false}
          badge={
            <span className="text-[10px] text-theme-text-tertiary tabular-nums">
              {systemPrompt.length > 1000
                ? `${Math.round(systemPrompt.length / 100) / 10}k`
                : `${systemPrompt.length}`}
            </span>
          }
        >
          <div className="rounded-lg overflow-hidden border border-theme-border bg-theme-bg p-3 sm:p-4 [&_.markdown-content]:text-xs sm:[&_.markdown-content]:text-sm [&_.markdown-content_p:first-child]:mt-0 [&_.markdown-content_p:last-child]:mb-0">
            <MarkdownContent content={systemPrompt} />
          </div>
          <div className="flex justify-end mt-2">
            <ToolHoverCopyButton
              text={systemPrompt}
              position="result"
              copyButtonClassName="!bg-theme-bg !rounded-lg !border !border-theme-border"
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
            <span className="text-[10px] text-theme-text-tertiary tabular-nums">
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
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center text-lg shrink-0 bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]">
                    {sp.icon || (
                      <MessageSquare
                        size={14}
                        className="text-[var(--theme-primary)]"
                      />
                    )}
                  </div>
                  <span className="text-sm text-theme-text leading-relaxed line-clamp-2">
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
        status={status}
        icon={<UserRound size={12} className="shrink-0 opacity-50" />}
        label={`${t("chat.message.toolPersonaPreset")} ${displayName || ""}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: t("chat.message.toolPersonaPreset"),
            icon: <UserRound size={16} />,
            status,
            subtitle: displayName || undefined,
            children: detailContent,
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
                    "w-6 h-6 rounded-md flex items-center justify-center text-sm leading-none shrink-0 overflow-hidden",
                    "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]",
                  )}
                >
                  <RenderAvatar
                    avatar={avatar}
                    sizeClass="w-full h-full"
                    fallback={
                      <UserRound
                        size={12}
                        className="text-[var(--theme-primary)]"
                      />
                    }
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-theme-text font-medium truncate">
                    {displayName}
                  </div>
                  {description && (
                    <div className="text-[10px] text-theme-text-tertiary truncate">
                      {description}
                    </div>
                  )}
                </div>
                {skillNames.length > 0 && (
                  <span className="shrink-0 text-[10px] text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-1.5 py-0.5 rounded-md">
                    {skillNames.length} skills
                  </span>
                )}
              </div>
            )}
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {tags.slice(0, 8).map((tag, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))] text-[10px]"
                  >
                    <Tag size={7} className="opacity-50" />
                    {tag}
                  </span>
                ))}
              </div>
            )}
            {result && !displayName && (
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

export { PersonaItem };
