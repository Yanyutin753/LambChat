import { ResourceCardTags } from "../common/ResourceCardTags";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { TeamListSkeleton } from "../skeletons";
import {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
  type ChangeEvent,
} from "react";
import {
  ChevronDown,
  Copy,
  Download,
  Pencil,
  Pin,
  Plus,
  Save,
  Sparkles,
  Star,
  Tag,
  Trash2,
  Upload,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { teamApi } from "../../services/api/team";
import { subscribeTeamsChanged } from "../../hooks/teamEvents";
import {
  TeamBuilder,
  type TeamBuilderHandle,
  type TeamBuilderFooterState,
} from "./TeamBuilder";
import type { Team, TeamCreateRequest, TeamMember } from "../../types/team";
import type { LocalizedText, PersonaStarterPrompt } from "../../types";
import { EditorSidebar } from "../common/EditorSidebar";
import { Button } from "../common/ui";
import { PanelFooterActions } from "../common/PanelControls";
import { nameToGradient } from "../common/cardUtils";
import { Pagination } from "../common/Pagination";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { EmptyState } from "../common/EmptyState";
import { PersonaScopeDropdown } from "../persona/PersonaScopeDropdown";
import { PersonaTagFilterDropdown } from "../persona/PersonaTagFilterDropdown";
import type { ScopeFilter } from "../persona/usePersonaPlaza";
import { TeamAvatar } from "./TeamAvatar";
import { getTeamFallbackAvatar, getTeamFallbackTag } from "./teamAvatarUtils";
import { fetchAllTeamsForExport, toTeamExportData } from "./teamExport";

const TEAM_PAGE_SIZE = 20;

type TeamScopeFilter = Extract<ScopeFilter, "all" | "pinned" | "favorite">;
type ImportedTeamMember = NonNullable<TeamCreateRequest["members"]>[number];

const SCOPE_ICON_MAP = {
  Users,
  Pin,
  Star,
} as const;

function isLocalizedText(value: unknown): value is LocalizedText {
  if (typeof value === "string") return true;
  return (
    !!value &&
    typeof value === "object" &&
    Object.values(value as Record<string, unknown>).every(
      (item) => typeof item === "string",
    )
  );
}

function normalizeImportedStarterPrompts(
  value: unknown,
): PersonaStarterPrompt[] {
  if (!Array.isArray(value)) return [];
  const prompts: PersonaStarterPrompt[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    if (!isLocalizedText(record.text)) continue;
    prompts.push({
      icon: typeof record.icon === "string" ? record.icon : null,
      text: record.text,
    });
  }
  return prompts;
}

function normalizeImportedTeam(value: unknown): TeamCreateRequest | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const name = String(item.name ?? "").trim();
  if (!name) return null;
  return {
    name,
    description:
      typeof item.description === "string" ? item.description : undefined,
    avatar: typeof item.avatar === "string" ? item.avatar : null,
    tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
    team_instructions:
      typeof item.team_instructions === "string"
        ? item.team_instructions
        : undefined,
    starter_prompts: normalizeImportedStarterPrompts(item.starter_prompts),
    default_member_id:
      typeof item.default_member_id === "string"
        ? item.default_member_id
        : null,
    members: Array.isArray(item.members)
      ? item.members
          .map((member): ImportedTeamMember | null => {
            if (!member || typeof member !== "object") return null;
            const record = member as Record<string, unknown>;
            const personaPresetId = String(record.persona_preset_id ?? "");
            if (!personaPresetId) return null;
            return {
              member_id:
                typeof record.member_id === "string"
                  ? record.member_id
                  : undefined,
              persona_preset_id: personaPresetId,
              agent_id:
                typeof record.agent_id === "string" && record.agent_id
                  ? record.agent_id
                  : null,
              model_id:
                typeof record.model_id === "string" && record.model_id
                  ? record.model_id
                  : null,
              role_name:
                typeof record.role_name === "string"
                  ? record.role_name
                  : undefined,
              role_avatar:
                typeof record.role_avatar === "string"
                  ? record.role_avatar
                  : null,
              role_tags: Array.isArray(record.role_tags)
                ? record.role_tags.map(String)
                : [],
              role_instructions:
                typeof record.role_instructions === "string"
                  ? record.role_instructions
                  : undefined,
              position:
                typeof record.position === "number" ? record.position : 0,
              enabled:
                typeof record.enabled === "boolean" ? record.enabled : true,
            };
          })
          .filter((member): member is ImportedTeamMember => Boolean(member))
      : [],
  };
}

function timeValue(value: string | null | undefined): number {
  if (!value) return 0;
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

function compareTeamPreference(a: Team, b: Team): number {
  return (
    Number(Boolean(b.is_pinned)) - Number(Boolean(a.is_pinned)) ||
    Number(Boolean(b.is_favorite)) - Number(Boolean(a.is_favorite)) ||
    timeValue(b.updated_at) - timeValue(a.updated_at) ||
    timeValue(b.created_at) - timeValue(a.created_at) ||
    timeValue(b.last_used_at) - timeValue(a.last_used_at)
  );
}

function renderMemberAvatar(member: TeamMember) {
  return (
    <TeamAvatar
      key={member.member_id}
      avatar={member.role_avatar}
      fallbackTag={member.role_tags[0]}
      label={member.role_name}
      className="team-card__avatar-item"
      iconSize={14}
    />
  );
}

export function TeamBuilderWrapper() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [teams, setTeams] = useState<Team[]>([]);
  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<TeamScopeFilter>("all");
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const requestRef = useRef(0);
  const [isImporting, setIsImporting] = useState(false);
  const [isScopeOpen, setIsScopeOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [footerState, setFooterState] = useState<TeamBuilderFooterState>({
    saving: false,
    uploadingAvatar: false,
    existingTeamId: null,
    hasTeamName: false,
  });
  const formRef = useRef<TeamBuilderHandle>(null);
  const importInputRef = useRef<HTMLInputElement>(null);
  const scopeBtnRef = useRef<HTMLButtonElement>(null);
  const tagBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setPage(1);
  }, [activeTag, query, scopeFilter]);

  const loadTeams = useCallback(async () => {
    const request = ++requestRef.current;
    setLoading(true);
    setLoadError(false);
    try {
      const res = await teamApi.list({
        skip: (page - 1) * TEAM_PAGE_SIZE,
        limit: TEAM_PAGE_SIZE,
        q: query.trim() || undefined,
        tag: activeTag || undefined,
        pinned: scopeFilter === "pinned" ? true : undefined,
        favorite: scopeFilter === "favorite" ? true : undefined,
      });
      if (request !== requestRef.current) return;
      setTeams([...res.teams].sort(compareTeamPreference));
      setTotal(res.total);
    } catch (error) {
      if (request !== requestRef.current) return;
      console.error("Failed to load teams:", error);
      setLoadError(true);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [activeTag, page, query, scopeFilter]);

  useEffect(() => {
    void loadTeams();
    const request = requestRef.current;
    return () => {
      if (requestRef.current === request) requestRef.current = request + 1;
    };
  }, [loadTeams]);

  useEffect(
    () =>
      subscribeTeamsChanged(() => {
        void loadTeams();
      }),
    [loadTeams],
  );

  const handleCreateNew = () => {
    setEditingTeamId(null);
    setEditorOpen(true);
  };

  const handleEditTeam = (teamId: string) => {
    setEditingTeamId(teamId);
    setEditorOpen(true);
  };

  const handleCloneTeam = async (teamId: string) => {
    try {
      await teamApi.clone(teamId);
      toast.success(t("team.cloneSuccess", "团队已克隆"));
      loadTeams();
    } catch (e) {
      console.error("Failed to clone team:", e);
      toast.error(t("team.cloneFailed", "克隆失败"));
    }
  };

  const handleUseTeam = (team: Team) => {
    navigate(`/chat?agent=team&team=${encodeURIComponent(team.id)}`, {
      state: {
        agentId: "team",
        teamId: team.id,
      },
    });
    toast.success(
      t("team.useSuccess", "已切换到团队「{{name}}」", { name: team.name }),
    );
  };

  const handleTogglePreference = useCallback(
    async (
      team: Team,
      preference: { is_favorite?: boolean; is_pinned?: boolean },
    ) => {
      try {
        const updated = await teamApi.updatePreference(team.id, preference);
        setTeams((prev) =>
          prev
            .map((item) => (item.id === updated.id ? updated : item))
            .sort(compareTeamPreference),
        );
      } catch (e) {
        console.error("Failed to update team preference:", e);
      }
    },
    [],
  );

  const handleDeleteTeam = async () => {
    if (!deleteConfirmId) return;
    setIsDeleting(true);
    try {
      await teamApi.delete(deleteConfirmId);
      toast.success(t("team.deleteSuccess", "团队已删除"));
      setTeams((prev) => prev.filter((t) => t.id !== deleteConfirmId));
      setDeleteConfirmId(null);
    } catch (e) {
      console.error("Failed to delete team:", e);
      toast.error(t("team.deleteFailed", "删除失败"));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSave = (team: Team) => {
    setEditingTeamId(team.id);
    loadTeams();
    setEditorOpen(false);
  };

  const handleClose = () => {
    setEditorOpen(false);
    setEditingTeamId(null);
    loadTeams();
  };

  const allTags = useMemo(
    () => Array.from(new Set(teams.flatMap((team) => team.tags ?? []))).sort(),
    [teams],
  );
  const hasActiveFilters =
    query.trim().length > 0 || activeTag !== null || scopeFilter !== "all";
  const scopeTabs = useMemo(
    () => [
      {
        key: "all" as ScopeFilter,
        label: t("personaPresets.all", "全部"),
        icon: "Users" as const,
      },
      {
        key: "pinned" as ScopeFilter,
        label: t("personaPresets.pinned", "置顶"),
        icon: "Pin" as const,
      },
      {
        key: "favorite" as ScopeFilter,
        label: t("personaPresets.favorites", "收藏"),
        icon: "Star" as const,
      },
    ],
    [t],
  );
  const currentScope = scopeTabs.find((tab) => tab.key === scopeFilter);
  const CurrentScopeIcon =
    SCOPE_ICON_MAP[
      (currentScope?.icon ?? "Users") as keyof typeof SCOPE_ICON_MAP
    ];

  const clearFilters = useCallback(() => {
    setQuery("");
    setActiveTag(null);
    setScopeFilter("all");
  }, []);

  const toggleTag = useCallback((tag: string) => {
    setActiveTag((prev) => (prev === tag ? null : tag));
  }, []);

  const handleExport = useCallback(async () => {
    let allTeams: Team[];
    try {
      allTeams = await fetchAllTeamsForExport(teamApi.list);
    } catch {
      toast.error(t("team.exportFailed", "导出失败"));
      return;
    }

    const exportData = toTeamExportData(allTeams);
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lambchat-teams-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(
      t("team.exportSuccess", "已导出 {{count}} 个团队", {
        count: exportData.length,
      }),
    );
  }, [t]);

  const handleImport = useCallback(() => {
    importInputRef.current?.click();
  }, []);

  const handleImportFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      event.target.value = "";

      let items: TeamCreateRequest[];
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed)) throw new Error("not_array");
        items = parsed
          .map(normalizeImportedTeam)
          .filter((item): item is TeamCreateRequest => Boolean(item));
        if (items.length !== parsed.length) throw new Error("invalid_items");
      } catch {
        toast.error(t("team.importInvalidFile", "导入失败：文件格式不正确"));
        return;
      }

      setIsImporting(true);
      try {
        await Promise.all(items.map((item) => teamApi.create(item)));
        toast.success(
          t("team.importSuccess", "成功导入 {{count}} 个团队", {
            count: items.length,
          }),
        );
        loadTeams();
      } catch {
        toast.error(t("team.importFailed", "导入失败"));
      } finally {
        setIsImporting(false);
      }
    },
    [loadTeams, t],
  );

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <PanelHeader
        className="skill-panel-header"
        title={t("team.title")}
        subtitle={t("team.subtitle")}
        illustration="panel-team"
        searchValue={query}
        onSearchChange={setQuery}
        searchPlaceholder={t("team.searchPlaceholder", "搜索团队名称、描述...")}
        searchAccessory={
          <div className="flex items-center gap-2">
            <div className="shrink-0" data-scope-filter>
              <button
                ref={scopeBtnRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={isScopeOpen}
                onClick={() => {
                  setIsScopeOpen((prev) => !prev);
                  setIsFilterOpen(false);
                }}
                className={`btn-secondary h-10 px-2.5 ${
                  scopeFilter !== "all"
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                <CurrentScopeIcon size={14} />
                <span className="hidden sm:inline">
                  {currentScope?.label ?? t("personaPresets.all", "全部")}
                </span>
                <ChevronDown
                  size={14}
                  className={`transition-transform ${
                    isScopeOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
            </div>
            {allTags.length > 0 && (
              <div className="shrink-0" data-team-filter>
                <button
                  ref={tagBtnRef}
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={isFilterOpen}
                  onClick={() => {
                    setIsFilterOpen((prev) => !prev);
                    setIsScopeOpen(false);
                  }}
                  className={`btn-secondary h-10 px-2.5 ${
                    activeTag
                      ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                      : ""
                  }`}
                >
                  <Tag size={14} />
                  <span className="hidden sm:inline">
                    {t("team.tags", "标签")}
                  </span>
                  {activeTag && (
                    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-10">
                      1
                    </span>
                  )}
                  <ChevronDown
                    size={14}
                    className={`transition-transform ${
                      isFilterOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
              </div>
            )}
          </div>
        }
        actions={
          <>
            <button
              onClick={handleExport}
              disabled={teams.length === 0}
              className="btn-secondary h-10"
              title={t("team.export", "导出团队")}
            >
              <Download size={16} />
              <span className="hidden sm:inline">
                {t("personaPresets.export", "导出")}
              </span>
            </button>
            <button
              onClick={handleImport}
              disabled={isImporting}
              className="btn-secondary h-10"
              title={t("team.import", "导入团队")}
            >
              <Upload size={16} />
              <span className="hidden sm:inline">
                {isImporting
                  ? t("personaPresets.importing", "导入中...")
                  : t("personaPresets.import", "导入")}
              </span>
            </button>
            <button onClick={handleCreateNew} className="btn-primary h-10">
              <Plus size={15} />
              <span className="hidden sm:inline">{t("team.newTeam")}</span>
            </button>
          </>
        }
      />

      <div className="panel-body skill-content-area flex-1 overflow-y-auto">
        {loadError && (
          <div
            role="alert"
            className="p-4 text-center text-theme-text-secondary"
          >
            <p>{t("common.loadFailed")}</p>
            <button
              type="button"
              className="btn-secondary mt-3"
              onClick={() => void loadTeams()}
            >
              {t("common.refresh")}
            </button>
          </div>
        )}

        {loading ? (
          <TeamListSkeleton />
        ) : !loadError && teams.length === 0 ? (
          <EmptyState
            icon={<Users size={28} />}
            title={
              hasActiveFilters
                ? t("team.noMatchingTeams")
                : t("team.noTeamsYet")
            }
            description={
              hasActiveFilters
                ? t("personaPresets.tryOtherFilters", "试试其他搜索条件")
                : t("team.noTeamsDesc")
            }
            action={
              hasActiveFilters ? (
                <button onClick={clearFilters} className="btn-secondary">
                  {t("personaPresets.clearFilters", "清除筛选")}
                </button>
              ) : (
                <button
                  onClick={handleCreateNew}
                  className="btn-primary h-9 text-14"
                >
                  <Plus size={15} />
                  {t("team.createFirst")}
                </button>
              )
            }
          />
        ) : (
          <div className="grid auto-grid-cols gap-3">
            {teams.map((team) => {
              const colors = nameToGradient(team.name);
              const activeCount = team.members.filter((m) => m.enabled).length;
              return (
                <SkillBaseCard
                  key={team.id}
                  title={team.name}
                  className="team-card"
                  style={{ "--team-accent": colors[0] } as React.CSSProperties}
                  gradient={colors}
                  description={team.description || t("team.coordinatedDesc")}
                  iconClassName=""
                  icon={
                    <TeamAvatar
                      avatar={team.avatar}
                      fallbackAvatar={getTeamFallbackAvatar(team)}
                      fallbackTag={getTeamFallbackTag(team)}
                      label={team.name}
                      className="team-card__identity-avatar"
                      imgClassName="scb__avatar-img"
                      iconSize={20}
                    />
                  }
                  statusPills={
                    <div className="mt-1.5 flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
                      <span>
                        {t("team.memberCount_one", {
                          count: team.members.length,
                        })}
                      </span>
                    </div>
                  }
                  bannerLeadingOverlay={
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        className={`pps-card__icon-action ${
                          team.is_pinned
                            ? "pps-card__icon-action--active-pin"
                            : ""
                        }`}
                        title={t("personaPresets.pin", "Pin")}
                        onClick={() =>
                          handleTogglePreference(team, {
                            is_pinned: !team.is_pinned,
                          })
                        }
                      >
                        <Pin size={12} />
                      </button>
                      <button
                        type="button"
                        className={`pps-card__icon-action ${
                          team.is_favorite
                            ? "pps-card__icon-action--active-fav"
                            : ""
                        }`}
                        title={t("personaPresets.favorite", "Favorite")}
                        onClick={() =>
                          handleTogglePreference(team, {
                            is_favorite: !team.is_favorite,
                          })
                        }
                      >
                        <Star size={12} />
                      </button>
                    </div>
                  }
                  bannerOverlay={
                    <span className="scb__status-pill scb__status-pill--installed">
                      {t("team.activeStatus", { count: activeCount })}
                    </span>
                  }
                  tags={
                    (team.tags ?? []).length > 0 ? (
                      <ResourceCardTags
                        tags={team.tags ?? []}
                        activeTag={activeTag}
                        onToggle={toggleTag}
                      />
                    ) : undefined
                  }
                  extraContent={
                    <>
                      {team.members.length > 0 && (
                        <div className="team-card__avatars">
                          {team.members.slice(0, 5).map(renderMemberAvatar)}
                          {team.members.length > 5 && (
                            <span className="team-card__avatar-overflow">
                              +{team.members.length - 5}
                            </span>
                          )}
                        </div>
                      )}
                    </>
                  }
                  actions={[
                    {
                      label: t("team.use"),
                      icon: <Sparkles size={16} />,
                      onClick: () => handleUseTeam(team),
                    },
                    {
                      label: t(
                        team.is_pinned
                          ? "sidebar.unpinFromTop"
                          : "personaPresets.pin",
                      ),
                      icon: <Pin size={16} />,
                      onClick: () =>
                        handleTogglePreference(team, {
                          is_pinned: !team.is_pinned,
                        }),
                    },
                    {
                      label: t(
                        team.is_favorite
                          ? "fileLibrary.context.unfavorite"
                          : "personaPresets.favorite",
                      ),
                      icon: <Star size={16} />,
                      onClick: () =>
                        handleTogglePreference(team, {
                          is_favorite: !team.is_favorite,
                        }),
                    },
                    {
                      label: t("team.edit"),
                      icon: <Pencil size={16} />,
                      onClick: () => handleEditTeam(team.id),
                    },
                    {
                      label: t("team.clone"),
                      icon: <Copy size={16} />,
                      onClick: () => handleCloneTeam(team.id),
                    },
                    {
                      label: t("team.delete"),
                      icon: <Trash2 size={16} />,
                      danger: true,
                      onClick: () => setDeleteConfirmId(team.id),
                    },
                  ]}
                  footer={
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
                        <span className="inline-flex items-center gap-1">
                          <Users size={11} />
                          {t("team.rolesCount", { count: team.members.length })}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handleUseTeam(team)}
                          className="scb__action-btn scb__action-btn--ghost"
                          title={t("team.use", "使用")}
                        >
                          <Sparkles size={16} />
                        </button>
                      </div>
                    </div>
                  }
                />
              );
            })}
          </div>
        )}
      </div>

      <div className="panel-pagination empty:hidden">
        <Pagination
          page={page}
          pageSize={TEAM_PAGE_SIZE}
          total={total}
          onChange={setPage}
        />
      </div>
      <EditorSidebar
        open={editorOpen}
        onClose={handleClose}
        title={editingTeamId ? t("team.editTeam") : t("team.newTeam")}
        subtitle={t("team.buildRoles")}
        icon={<Users size={18} />}
        width="default"
        defaultWidthPct={30}
        widthStorageKey="team-editor-sidebar-width"
        footer={
          <PanelFooterActions>
            <Button onClick={handleClose}>{t("common.cancel")}</Button>
            <Button
              variant="primary"
              onClick={() => formRef.current?.handleSave()}
              disabled={
                footerState.saving ||
                footerState.uploadingAvatar ||
                !footerState.hasTeamName
              }
              loading={footerState.saving}
              leftIcon={<Save size={14} />}
            >
              <span role={footerState.saving ? "status" : undefined}>
                {footerState.saving ? t("team.saving") : t("team.save")}
              </span>
            </Button>
          </PanelFooterActions>
        }
      >
        <TeamBuilder
          ref={formRef}
          teamId={editingTeamId}
          onSave={handleSave}
          onClose={handleClose}
          surface="sidebar"
          onFormStateChange={setFooterState}
        />
      </EditorSidebar>

      <input
        ref={importInputRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={handleImportFile}
      />

      <PersonaScopeDropdown
        isOpen={isScopeOpen}
        scopeFilter={scopeFilter}
        scopeTabs={scopeTabs}
        scopeBtnRef={scopeBtnRef}
        onSelect={(key) => setScopeFilter(key as TeamScopeFilter)}
        onClose={() => setIsScopeOpen(false)}
      />

      <PersonaTagFilterDropdown
        isOpen={isFilterOpen}
        allTags={allTags}
        activeTag={activeTag}
        hasActiveFilters={hasActiveFilters}
        tagBtnRef={tagBtnRef}
        onToggleTag={toggleTag}
        onClearFilters={clearFilters}
        onClose={() => setIsFilterOpen(false)}
      />

      <ConfirmDialog
        isOpen={!!deleteConfirmId}
        title={t("team.confirmDelete", "确认删除")}
        message={t(
          "team.confirmDeleteMessage",
          "确定要删除该团队吗？此操作不可撤销。",
        )}
        confirmText={t("common.delete", "删除")}
        cancelText={t("common.cancel", "取消")}
        variant="danger"
        loading={isDeleting}
        onConfirm={handleDeleteTeam}
        onCancel={() => setDeleteConfirmId(null)}
      />
    </div>
  );
}
