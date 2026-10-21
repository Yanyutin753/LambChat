import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { Users, Tag, Zap } from "lucide-react";
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
import { DetailSection } from "./DetailSection";
// ── TeamDetail ──────────────────────────────────────────────────────────

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（团队/搜索结果到达即刷新） */
function TeamDetail({
  args,
  result,
  toolName,
}: ToolDetailProps & { toolName?: string }) {
  const { t } = useTranslation();

  const isSearch = toolName === "search_persona_presets";

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

  return (
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
              const name = String(
                p.name ||
                  t("chat.message.toolTeamDefaultPersona", { index: i + 1 }),
              );
              const desc = String(p.description || "");
              const av = String(p.avatar || "");
              const pTags: string[] = Array.isArray(p.tags) ? p.tags : [];
              const pSkills: string[] = Array.isArray(p.skill_names)
                ? p.skill_names
                : [];
              const pScope = String(p.scope || "");
              const pStatus = String(p.status || "");
              const pUsage = Number(p.usage_count || 0);

              return (
                <div
                  key={i}
                  className="tool-result-card border border-theme-border"
                >
                  <div className="space-y-3">
                    {/* Avatar + Name + Status */}
                    <div className="flex items-start gap-3">
                      <AgentAvatar avatar={av} seed={name} size={40} />
                      <div className="min-w-0 flex-1 pt-0.5">
                        <div className="flex items-center gap-1.5">
                          <div className="text-14 text-theme-text font-semibold font-serif truncate">
                            {name}
                          </div>
                          {pStatus && pStatus !== "published" && (
                            <TagBadge>{pStatus}</TagBadge>
                          )}
                        </div>
                        {desc && (
                          <p className="text-11 text-theme-text-secondary/80 mt-1 leading-relaxed line-clamp-2 min-h-[2.75em]">
                            {desc}
                          </p>
                        )}
                      </div>
                    </div>
                    {/* Tags + Skills */}
                    {(pTags.length > 0 || pSkills.length > 0) && (
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {pTags.map((tag, j) => (
                          <TagBadge key={j} icon={<Tag />}>
                            {tag}
                          </TagBadge>
                        ))}
                        {pSkills.length > 0 && (
                          <TagBadge icon={<Zap />}>{pSkills.length}</TagBadge>
                        )}
                      </div>
                    )}
                    {/* Meta footer */}
                    {(pScope || pUsage > 0) && (
                      <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-theme-border/60">
                        {pScope && (
                          <span className="text-10 text-theme-text-tertiary">
                            {pScope === "global"
                              ? t("personaPresets.official", "官方")
                              : t("personaPresets.mine", "我的")}
                          </span>
                        )}
                        {pScope && pUsage > 0 && (
                          <span className="inline-block h-1 w-1 rounded-full bg-theme-border" />
                        )}
                        {pUsage > 0 && (
                          <span className="text-10 text-theme-text-tertiary">
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

      {/* Team details */}
      {!isSearch && (resultTeamName || resultMembers.length > 0) && (
        <>
          {resultTeamName && (
            <section className="space-y-3">
              <div className="flex items-start gap-3 min-w-0">
                <AgentAvatar
                  avatar={resultAvatar}
                  seed={resultTeamName}
                  size={40}
                />
                <div className="min-w-0 flex-1 space-y-1">
                  <h3 className="text-16 font-serif font-semibold text-theme-text break-words">
                    {resultTeamName}
                  </h3>
                  {resultId && (
                    <div className="flex items-center gap-2 text-12 text-theme-text-tertiary">
                      <span
                        className="font-mono min-w-0 flex-1 truncate"
                        title={resultId}
                      >
                        {resultId}
                      </span>
                      <CopyButton text={resultId} />
                    </div>
                  )}
                </div>
              </div>
              {resultDescription && (
                <p className="text-12 text-theme-text-secondary whitespace-pre-wrap break-words">
                  {resultDescription}
                </p>
              )}
              {resultTags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {resultTags.map((tag, i) => (
                    <TagBadge key={i} icon={<Tag />}>
                      {tag}
                    </TagBadge>
                  ))}
                </div>
              )}
            </section>
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
                    m.role_name ||
                      m.name ||
                      t("chat.message.toolTeamDefaultMember", { index: i + 1 }),
                  );
                  const roleAvatar = String(m.role_avatar || m.avatar || "");
                  const instructions = String(m.role_instructions || "");
                  const mTags: string[] = Array.isArray(m.tags)
                    ? (m.tags as string[])
                    : [];

                  return (
                    <div
                      key={i}
                      className={clsx(
                        "group/member tool-result-card border border-theme-border",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <AgentAvatar
                          avatar={roleAvatar}
                          seed={roleName}
                          size={32}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-12 text-theme-text font-semibold font-serif truncate">
                            {roleName}
                          </div>
                          {mTags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {mTags.map((tag, j) => (
                                <TagBadge key={j} icon={<Tag />}>
                                  {tag}
                                </TagBadge>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      {instructions && (
                        <div className="pt-3">
                          <p className="text-11 text-theme-text-tertiary/80 line-clamp-3 leading-relaxed">
                            {instructions}
                          </p>
                          {instructions.length > 150 && (
                            <CopyButton
                              text={instructions}
                              size={10}
                              className="shrink-0 text-theme-text-tertiary hover:text-theme-text-secondary mt-1.5"
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

// ── TeamItem ──────────────────────────────────────────────────────────

const TeamItem = memo(function TeamItem({
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
    <TeamDetail
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
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${actionLabel}${labelSuffix ? ` ${labelSuffix}` : ""}`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={
          <Users
            size={12}
            className="shrink-0 opacity-50 text-emerald-500 dark:text-emerald-400"
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
            title: actionLabel,
            icon: <Users size={16} />,
            status: pillStatus,
            subtitle: labelSuffix
              ? labelSuffix.length > 80
                ? labelSuffix.slice(0, 77) + "…"
                : labelSuffix
              : undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <TeamDetail
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
            {isSearch && personas.length > 0 && (
              <div>
                <div className="text-12 text-theme-text-tertiary mb-1">
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
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg border border-theme-border text-10 font-serif text-theme-text-secondary hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors"
                      >
                        <AgentAvatar avatar={av} seed={name} size={14} />
                        {name}
                      </span>
                    );
                  })}
                  {personas.length > 8 && (
                    <span className="text-10 text-theme-text-tertiary px-1">
                      +{personas.length - 8}
                    </span>
                  )}
                </div>
              </div>
            )}

            {!isSearch && resultTeamName && (
              <div className="flex items-center gap-2 rounded-lg px-2.5 py-2 bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors">
                <AgentAvatar
                  avatar={resultAvatar}
                  seed={resultTeamName}
                  size={20}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-12 text-theme-text font-medium font-serif truncate">
                    {resultTeamName}
                  </div>
                </div>
                {resultMembers.length > 0 && (
                  <span className="shrink-0 text-10 text-theme-text-tertiary">
                    {t("chat.message.toolMemberCount", {
                      count: resultMembers.length,
                    })}
                  </span>
                )}
              </div>
            )}

            {result && personas.length === 0 && !resultTeamName && (
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

export { TeamItem };
