import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { Users, Tag, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { nameToGradient } from "../../../common/cardUtils";
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

// ── TeamItem ──────────────────────────────────────────────────────────

const TeamItem = memo(function TeamItem({
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

  const isSearch = toolName === "search_persona_presets";
  const actionLabel = isSearch
    ? t("chat.message.toolSearchPersonas")
    : t("chat.message.toolCreateTeam");

  const query = (args.query as string) || "";
  const teamName = (args.name as string) || "";
  const teamAvatar = (args.avatar as string) || "";
  const members: Array<Record<string, unknown>> =
    (args.members as Array<Record<string, unknown>>) || [];

  const parsed = useMemo(() => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      if (raw?.team && typeof raw.team === "object") return raw.team;
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const personas: Array<Record<string, unknown>> = useMemo(() => {
    if (!isSearch || !parsed) return [];
    if (Array.isArray(parsed)) return parsed as Array<Record<string, unknown>>;
    if (Array.isArray(parsed.items))
      return parsed.items as Array<Record<string, unknown>>;
    if (Array.isArray(parsed.presets))
      return parsed.presets as Array<Record<string, unknown>>;
    return [];
  }, [isSearch, parsed]);

  const resultTeamName = parsed?.name || teamName;
  const resultAvatar = parsed?.avatar || teamAvatar;
  const resultMembers: Array<Record<string, unknown>> =
    parsed?.members || members || [];
  const resultId = parsed?.id || "";
  const resultTags: string[] = parsed?.tags || [];
  const resultDescription = parsed?.description || "";

  const teamGradient = useMemo(
    () => (resultTeamName ? nameToGradient(resultTeamName) : null),
    [resultTeamName],
  );

  const canExpand =
    !!query ||
    !!teamName ||
    personas.length > 0 ||
    resultMembers.length > 0 ||
    !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const labelSuffix = isSearch ? query : resultTeamName || teamName || "";

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {/* Search: persona list */}
      {isSearch && personas.length > 0 && (
        <DetailSection
          title={t("chat.message.toolPersonaCount", {
            count: personas.length,
          })}
          icon={<Users size={12} />}
          defaultExpanded={true}
        >
          <div className="grid auto-grid-cols gap-3">
            {personas.slice(0, 20).map((p, i) => {
              const name = String(p.name || `Persona ${i + 1}`);
              const desc = String(p.description || "");
              const av = String(p.avatar || "");
              const pTags: string[] = Array.isArray(p.tags) ? p.tags : [];
              const pSkills: string[] = Array.isArray(p.skill_names)
                ? p.skill_names
                : [];
              const pScope = String(p.scope || "");
              const pStatus = String(p.status || "");
              const pUsage = Number(p.usage_count || 0);
              const pGradient = nameToGradient(name);

              return (
                <div
                  key={i}
                  className="rounded-xl overflow-hidden border border-theme-border bg-theme-bg-card hover:shadow-md transition-all duration-200"
                  style={{ boxShadow: `0 1px 8px -2px ${pGradient[0]}15` }}
                >
                  {/* Gradient banner */}
                  <div
                    className="h-11 relative overflow-hidden"
                    style={{
                      background: `linear-gradient(135deg, ${pGradient[0]}, ${pGradient[1]}, ${pGradient[2]})`,
                    }}
                  >
                    <div
                      className="absolute inset-0 opacity-40"
                      style={{
                        backgroundImage: `radial-gradient(circle at 80% 20%, ${pGradient[2]}50 0%, transparent 60%)`,
                      }}
                    />
                    <div className="absolute bottom-0 inset-x-0 h-4 bg-gradient-to-t from-theme-bg-card to-transparent" />
                  </div>
                  {/* Card body */}
                  <div className="px-4 pt-4 pb-3.5 bg-theme-bg-card -mt-5 relative">
                    {/* Avatar + Name + Status */}
                    <div className="flex items-start gap-3">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center text-lg leading-none shrink-0 overflow-hidden relative"
                        style={{
                          boxShadow: `0 3px 10px -2px ${pGradient[0]}35`,
                        }}
                      >
                        <div
                          className="absolute inset-0 rounded-xl p-[1px]"
                          style={{
                            background: `linear-gradient(135deg, ${pGradient[0]}60, ${pGradient[1]}35)`,
                          }}
                        >
                          <div className="w-full h-full rounded-[calc(0.75rem-1px)] bg-theme-bg-card" />
                        </div>
                        <div className="relative z-10 w-full h-full rounded-xl flex items-center justify-center overflow-hidden bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]">
                          <RenderAvatar
                            avatar={av}
                            sizeClass="w-full h-full"
                            fallback={
                              <Users
                                size={16}
                                className="text-[var(--theme-primary)]"
                              />
                            }
                          />
                        </div>
                      </div>
                      <div className="min-w-0 flex-1 pt-0.5">
                        <div className="flex items-center gap-1.5">
                          <div className="text-sm text-theme-text font-semibold truncate">
                            {name}
                          </div>
                          {pStatus && pStatus !== "published" && (
                            <span
                              className={clsx(
                                "shrink-0 inline-flex items-center px-1.5 py-[2px] rounded-full text-[9px] font-semibold tracking-wide uppercase",
                                pStatus === "draft"
                                  ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 ring-1 ring-amber-200/50 dark:ring-amber-800/30"
                                  : "bg-theme-bg-subtle text-theme-text-tertiary ring-1 ring-theme-border",
                              )}
                            >
                              {pStatus}
                            </span>
                          )}
                        </div>
                        {desc && (
                          <p className="text-[11px] text-theme-text-secondary/80 mt-1 leading-relaxed line-clamp-2 min-h-[2.75em]">
                            {desc}
                          </p>
                        )}
                      </div>
                    </div>
                    {/* Tags + Skills */}
                    {(pTags.length > 0 || pSkills.length > 0) && (
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {pTags.slice(0, 3).map((tag, j) => (
                          <span
                            key={j}
                            className={clsx(
                              "inline-flex items-center gap-1 px-2 py-[2px] rounded-lg text-[10px] font-medium",
                              j === 0
                                ? "bg-[color-mix(in_srgb,var(--theme-primary)_10%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_18%,var(--theme-border))]"
                                : "bg-theme-bg text-theme-text-secondary ring-1 ring-theme-border",
                            )}
                          >
                            <Tag size={8} className="opacity-50" />
                            {tag}
                          </span>
                        ))}
                        {pSkills.length > 0 && (
                          <span className="inline-flex items-center gap-1 px-2 py-[2px] rounded-lg text-[10px] font-medium bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-200/50 dark:ring-emerald-700/30">
                            <Zap size={8} className="opacity-60" />
                            {pSkills.length}
                          </span>
                        )}
                      </div>
                    )}
                    {/* Meta footer */}
                    {(pScope || pUsage > 0) && (
                      <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-theme-border/60">
                        {pScope && (
                          <span className="text-[10px] text-theme-text-tertiary">
                            {pScope === "global"
                              ? t("personaPresets.official", "官方")
                              : t("personaPresets.mine", "我的")}
                          </span>
                        )}
                        {pScope && pUsage > 0 && (
                          <span className="inline-block h-1 w-1 rounded-full bg-theme-border" />
                        )}
                        {pUsage > 0 && (
                          <span className="text-[10px] text-theme-text-tertiary">
                            {pUsage}
                            {t("personaPresets.usageCount", "次使用")}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </DetailSection>
      )}

      {/* Team: hero card */}
      {!isSearch && (resultTeamName || resultMembers.length > 0) && (
        <>
          {resultTeamName && (
            <div
              className={clsx(
                "rounded-2xl overflow-hidden relative",
                teamGradient && "shadow-md",
              )}
              style={
                teamGradient
                  ? {
                      boxShadow: `0 2px 16px -4px ${teamGradient[0]}30, 0 1px 3px rgb(0 0 0 / 0.06)`,
                    }
                  : undefined
              }
            >
              {/* Gradient border ring */}
              {teamGradient && (
                <div
                  className="absolute inset-0 rounded-2xl p-px"
                  style={{
                    background: `linear-gradient(135deg, ${teamGradient[0]}40, ${teamGradient[1]}20, ${teamGradient[2]}40)`,
                  }}
                >
                  <div className="w-full h-full rounded-[calc(1rem-1px)] bg-theme-bg-card" />
                </div>
              )}

              <div className="relative z-10 rounded-2xl overflow-hidden">
                {teamGradient && (
                  <div className="h-16 sm:h-20 relative overflow-hidden">
                    {/* Base gradient */}
                    <div
                      className="absolute inset-0"
                      style={{
                        background: `linear-gradient(135deg, ${teamGradient[0]}, ${teamGradient[1]}, ${teamGradient[2]})`,
                      }}
                    />
                    {/* Decorative mesh pattern */}
                    <div
                      className="absolute inset-0 opacity-30"
                      style={{
                        backgroundImage: `radial-gradient(circle at 20% 80%, ${teamGradient[0]}60 0%, transparent 50%), radial-gradient(circle at 80% 20%, ${teamGradient[2]}60 0%, transparent 50%)`,
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
                    "relative px-4 sm:px-5 py-3.5",
                    "bg-theme-bg-card",
                    !teamGradient && "pt-4",
                  )}
                >
                  <div
                    className={clsx(
                      "flex items-end gap-3.5",
                      teamGradient ? "-mt-7 sm:-mt-9" : "",
                    )}
                  >
                    <div
                      className="w-11 h-11 sm:w-14 sm:h-14 rounded-2xl flex items-center justify-center text-xl sm:text-2xl leading-none shrink-0 overflow-hidden relative"
                      style={
                        teamGradient
                          ? {
                              boxShadow: `0 4px 14px -3px ${teamGradient[0]}40, 0 2px 6px -1px rgb(0 0 0 / 0.1)`,
                            }
                          : undefined
                      }
                    >
                      {/* Gradient ring effect */}
                      {teamGradient && (
                        <div
                          className="absolute inset-0 rounded-2xl p-[2px]"
                          style={{
                            background: `linear-gradient(135deg, ${teamGradient[0]}, ${teamGradient[1]}, ${teamGradient[2]})`,
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
                          avatar={resultAvatar}
                          sizeClass="w-full h-full"
                          fallback={
                            <Users
                              size={teamGradient ? 24 : 18}
                              className="text-[var(--theme-primary)]"
                            />
                          }
                        />
                      </div>
                    </div>
                    <div className="min-w-0 flex-1 pb-0.5">
                      <h3 className="text-sm sm:text-base font-bold text-theme-text truncate tracking-tight">
                        {resultTeamName}
                      </h3>
                      {resultId && (
                        <div className="text-[10px] sm:text-xs text-theme-text-tertiary/70 font-mono truncate mt-0.5 flex items-center gap-1">
                          <span className="truncate">
                            {resultId.slice(0, 12)}…
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {resultDescription && (
                    <p className="text-xs sm:text-[13px] text-theme-text-secondary/80 mt-3 line-clamp-2 leading-relaxed">
                      {resultDescription}
                    </p>
                  )}

                  {resultTags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {resultTags.map((tag, i) => (
                        <span
                          key={i}
                          className={clsx(
                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium",
                            "transition-all duration-200",
                            i === 0
                              ? "bg-[color-mix(in_srgb,var(--theme-primary)_10%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_18%,var(--theme-border))]"
                              : "bg-theme-bg text-theme-text-secondary ring-1 ring-theme-border hover:ring-theme-border-hover",
                          )}
                        >
                          <Tag
                            size={9}
                            className={clsx(
                              i === 0 ? "opacity-60" : "opacity-40",
                            )}
                          />
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Members */}
          {resultMembers.length > 0 && (
            <DetailSection
              title={t("chat.message.toolMemberCount", {
                count: resultMembers.length,
              })}
              icon={<Users size={12} />}
              defaultExpanded={true}
            >
              <div className="space-y-2">
                {resultMembers.map((m, i) => {
                  const roleName = String(
                    m.role_name || m.name || `Member ${i + 1}`,
                  );
                  const roleAvatar = String(m.role_avatar || m.avatar || "");
                  const instructions = String(m.role_instructions || "");
                  const mTags: string[] = Array.isArray(m.tags)
                    ? (m.tags as string[])
                    : [];
                  const accentColor = teamGradient
                    ? teamGradient[i % teamGradient.length]
                    : "#38bdf8";

                  return (
                    <div
                      key={i}
                      className={clsx(
                        "group/member rounded-xl border border-theme-border bg-theme-bg-card overflow-hidden",
                        "hover:shadow-sm transition-all duration-200",
                      )}
                    >
                      {/* Top accent line */}
                      <div
                        className="h-[2px]"
                        style={{
                          background: `linear-gradient(90deg, ${accentColor}, transparent)`,
                        }}
                      />
                      <div className="flex items-center gap-3 px-3.5 py-2.5">
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center text-sm leading-none shrink-0 overflow-hidden relative"
                          style={{
                            boxShadow: `0 1px 4px -1px ${accentColor}30`,
                          }}
                        >
                          <div
                            className="absolute inset-0 rounded-lg p-[1px]"
                            style={{
                              background: `linear-gradient(135deg, ${accentColor}40, transparent)`,
                            }}
                          >
                            <div className="w-full h-full rounded-[calc(0.5rem-1px)] bg-theme-bg-card" />
                          </div>
                          <div className="relative z-10 w-full h-full rounded-lg flex items-center justify-center overflow-hidden bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))]">
                            <RenderAvatar
                              avatar={roleAvatar}
                              sizeClass="w-full h-full"
                              fallback={
                                <span className="text-xs text-theme-text-tertiary">
                                  ?
                                </span>
                              }
                            />
                          </div>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs text-theme-text font-semibold truncate">
                            {roleName}
                          </div>
                          {mTags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {mTags.slice(0, 3).map((tag, j) => (
                                <span
                                  key={j}
                                  className="inline-flex items-center px-1.5 py-[1px] rounded-md text-[10px] font-medium bg-theme-bg ring-1 ring-theme-border text-theme-text-secondary"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      {instructions && (
                        <div className="px-3.5 pb-3 pt-0">
                          <p className="text-[11px] text-theme-text-tertiary/80 line-clamp-3 leading-relaxed">
                            {instructions}
                          </p>
                          {instructions.length > 150 && (
                            <ToolHoverCopyButton
                              text={instructions}
                              position="result"
                              copyButtonClassName="!bg-theme-bg !rounded-md !border !border-theme-border mt-1.5"
                            />
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </DetailSection>
          )}
        </>
      )}

      {/* Raw result fallback */}
      {result &&
        personas.length === 0 &&
        !resultTeamName &&
        !resultMembers.length && (
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
        icon={<Users size={12} className="shrink-0 opacity-50" />}
        label={`${actionLabel}${
          labelSuffix
            ? ` ${
                labelSuffix.length > 40
                  ? labelSuffix.slice(0, 37) + "…"
                  : labelSuffix
              }`
            : ""
        }`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: actionLabel,
            icon: <Users size={16} />,
            status: pillStatus,
            subtitle: labelSuffix
              ? labelSuffix.length > 80
                ? labelSuffix.slice(0, 77) + "…"
                : labelSuffix
              : undefined,
            children: detailContent,
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {isSearch && personas.length > 0 && (
              <div>
                <div className="text-xs text-theme-text-tertiary mb-1">
                  {t("chat.message.toolPersonaCount", {
                    count: personas.length,
                  })}
                </div>
                <div className="flex flex-wrap gap-1">
                  {personas.slice(0, 8).map((p, i) => {
                    const name = String(p.name || `#${i + 1}`);
                    const av = String(p.avatar || "");
                    return (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg border border-theme-border text-[10px] text-theme-text-secondary hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors"
                      >
                        <span className="inline-flex w-3.5 h-3.5 items-center justify-center overflow-hidden rounded shrink-0">
                          <RenderAvatar
                            avatar={av}
                            sizeClass="w-full h-full"
                            fallback={
                              <Users
                                size={8}
                                className="text-[var(--theme-primary)] opacity-60"
                              />
                            }
                          />
                        </span>
                        {name}
                      </span>
                    );
                  })}
                  {personas.length > 8 && (
                    <span className="text-[10px] text-theme-text-tertiary px-1">
                      +{personas.length - 8}
                    </span>
                  )}
                </div>
              </div>
            )}

            {!isSearch && resultTeamName && (
              <div className="flex items-center gap-2 rounded-lg px-2.5 py-2 bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors">
                <div className="w-5 h-5 rounded flex items-center justify-center text-xs leading-none shrink-0 bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] overflow-hidden">
                  <RenderAvatar
                    avatar={resultAvatar}
                    sizeClass="w-full h-full"
                    fallback={
                      <Users
                        size={10}
                        className="text-[var(--theme-primary)]"
                      />
                    }
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-theme-text font-medium truncate">
                    {resultTeamName}
                  </div>
                </div>
                {resultMembers.length > 0 && (
                  <span className="shrink-0 text-[10px] text-theme-text-tertiary">
                    {t("chat.message.toolMemberCount", {
                      count: resultMembers.length,
                    })}
                  </span>
                )}
              </div>
            )}

            {result && personas.length === 0 && !resultTeamName && (
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

export { TeamItem };
