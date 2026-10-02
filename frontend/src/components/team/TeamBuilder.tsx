import {
  useState,
  useEffect,
  useCallback,
  useRef,
  useId,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  MessageSquareText,
  Plus,
  Search,
  Tag,
  Users,
} from "lucide-react";
import type { PersonaPreset } from "../../types";
import type { Team, TeamCreateRequest, TeamMember } from "../../types/team";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { TeamMemberCard } from "./TeamMemberCard";
import { teamApi } from "../../services/api/team";
import { agentApi } from "../../services/api/agent";
import { modelApi } from "../../services/api/model";
import type { ModelOption } from "../../services/api/model";
import type { AgentInfo } from "../../types/agent";
import { personaPresetApi } from "../../services/api/personaPreset";
import toast from "react-hot-toast";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { Button } from "../common/ui";
import { Pagination } from "../common/Pagination";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import {
  draftRowsToStarterPrompts,
  starterPromptsToDraftRows,
  type StarterPromptDraftRow,
} from "../persona/personaPresetEditor";
import { AvatarSection } from "../persona/PersonaEditorAvatarSection";
import { StarterPromptsEditor } from "../persona/PersonaEditorStarterPrompts";
import { useOptionalSettingsContext } from "../../contexts/SettingsContext";

export interface TeamBuilderHandle {
  handleSave: () => void;
  handleClone: () => void;
  handleDelete: () => void;
}

export interface TeamBuilderFooterState {
  saving: boolean;
  uploadingAvatar: boolean;
  existingTeamId: string | null;
  hasTeamName: boolean;
  canSave: boolean;
  saveError: boolean;
}

interface TeamBuilderProps {
  teamId?: string | null;
  onSave?: (team: Team) => void;
  onClose?: () => void;
  surface?: "page" | "sidebar";
  onFormStateChange?: (state: TeamBuilderFooterState) => void;
}

function generateMemberId(): string {
  return `m-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function tagsToInput(tags: string[] | undefined): string {
  return (tags ?? []).join(", ");
}

function inputToTags(value: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of value.split(/[,，\n]/)) {
    const tag = raw.trim();
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    result.push(tag);
  }
  return result;
}

const ROLE_PAGE_SIZE = 20;

export const TeamBuilder = forwardRef<TeamBuilderHandle, TeamBuilderProps>(
  function TeamBuilder(
    { teamId, onSave, onClose, surface = "page", onFormStateChange },
    ref,
  ) {
    const { t } = useTranslation();
    const fieldId = useId();
    const rolePickerId = useId();
    const settingsContext = useOptionalSettingsContext();
    const [presets, setPresets] = useState<PersonaPreset[]>([]);
    const [presetsLoading, setPresetsLoading] = useState(true);
    const [presetsError, setPresetsError] = useState(false);
    const [presetsTotal, setPresetsTotal] = useState(0);
    const [presetsPage, setPresetsPage] = useState(1);
    const [presetsAttempt, setPresetsAttempt] = useState(0);
    const roleListRef = useRef<HTMLDivElement>(null);
    const roleSearchRef = useRef<HTMLInputElement>(null);
    const [fallbackModels, setFallbackModels] = useState<ModelOption[] | null>(
      null,
    );
    const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);
    const [searchQuery, setSearchQuery] = useState("");

    const [teamName, setTeamName] = useState("");
    const [teamDescription, setTeamDescription] = useState("");
    const [teamAvatar, setTeamAvatar] = useState<string | null>(null);
    const [teamTagsInput, setTeamTagsInput] = useState("");
    const [teamInstructions, setTeamInstructions] = useState("");
    const [starterPromptRows, setStarterPromptRows] = useState<
      StarterPromptDraftRow[]
    >([]);
    const [members, setMembers] = useState<TeamMember[]>([]);
    const [defaultMemberId, setDefaultMemberId] = useState<string | null>(null);
    const requestedTeamId = teamId ?? null;
    const [loadedTeamId, setLoadedTeamId] = useState<string | null | undefined>(
      requestedTeamId ? undefined : null,
    );
    const [loading, setLoading] = useState(!!requestedTeamId);
    const [loadError, setLoadError] = useState(false);
    const [loadAttempt, setLoadAttempt] = useState(0);
    const [saveError, setSaveError] = useState(false);
    const [mutation, setMutation] = useState<
      "save" | "clone" | "delete" | null
    >(null);
    const session = useRef(0);
    const pendingMutation = useRef(false);
    const formRef = useRef<HTMLFormElement>(null);
    const saving = mutation === "save";
    const isDeleting = mutation === "delete";
    const ready = loadedTeamId === requestedTeamId && !loading && !loadError;
    const busy = !ready || mutation !== null;
    const [existingTeamId, setExistingTeamId] = useState<string | null>(null);
    const [uploadingAvatar, setUploadingAvatar] = useState(false);
    const [rolePickerOpen, setRolePickerOpen] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const avatarUploadingRef = useRef(false);
    const handleAvatarUploadingChange = useCallback((uploading: boolean) => {
      avatarUploadingRef.current = uploading;
      setUploadingAvatar(uploading);
    }, []);
    const rolePickerTriggerRef = useRef<HTMLButtonElement>(null);
    const rolePickerRef = useRef<HTMLDivElement>(null);
    const availableModels = settingsContext?.availableModels ?? fallbackModels;

    useImperativeHandle(ref, () => ({
      handleSave,
      handleClone,
      handleDelete: () => {
        if (ready && !pendingMutation.current && existingTeamId)
          setShowDeleteConfirm(true);
      },
    }));

    const hasTeamName = teamName.trim().length > 0;
    const canSave = !busy && !uploadingAvatar && hasTeamName;

    useEffect(() => {
      onFormStateChange?.({
        saving,
        uploadingAvatar,
        existingTeamId,
        hasTeamName,
        canSave,
        saveError,
      });
    }, [
      saving,
      uploadingAvatar,
      existingTeamId,
      hasTeamName,
      canSave,
      saveError,
      onFormStateChange,
    ]);

    useEffect(() => {
      if (!rolePickerOpen) return;
      let cancelled = false;
      setPresetsLoading(true);
      setPresetsError(false);
      const timer = window.setTimeout(
        () => {
          void personaPresetApi
            .list({
              skip: (presetsPage - 1) * ROLE_PAGE_SIZE,
              limit: ROLE_PAGE_SIZE,
              q: searchQuery.trim() || undefined,
            })
            .then((res) => {
              if (cancelled) return;
              setPresets(res.presets);
              setPresetsTotal(res.total);
              roleListRef.current?.scrollTo?.({ top: 0 });
            })
            .catch(() => {
              if (!cancelled) setPresetsError(true);
            })
            .finally(() => {
              if (!cancelled) setPresetsLoading(false);
            });
        },
        searchQuery.trim() ? 200 : 0,
      );
      return () => {
        cancelled = true;
        window.clearTimeout(timer);
      };
    }, [rolePickerOpen, searchQuery, presetsPage, presetsAttempt]);

    useEffect(() => {
      if (settingsContext?.availableModels) {
        setFallbackModels(null);
        return;
      }
      let cancelled = false;
      modelApi
        .listAvailable()
        .then((res) => {
          if (!cancelled) setFallbackModels(res.models ?? []);
        })
        .catch(() => {
          if (!cancelled) setFallbackModels([]);
        });
      return () => {
        cancelled = true;
      };
    }, [settingsContext?.availableModels]);

    useEffect(() => {
      let cancelled = false;
      agentApi
        .list()
        .then((res) => {
          if (!cancelled) {
            setAvailableAgents(
              (res.agents ?? []).filter((agent) => agent.id !== "team"),
            );
          }
        })
        .catch(() => {
          if (!cancelled) setAvailableAgents([]);
        });
      return () => {
        cancelled = true;
      };
    }, []);

    useEffect(() => {
      if (!rolePickerOpen) return;
      const handleClick = (e: MouseEvent) => {
        if (
          rolePickerRef.current &&
          !rolePickerRef.current.contains(e.target as Node)
        ) {
          setRolePickerOpen(false);
        }
      };
      document.addEventListener("mousedown", handleClick);
      return () => document.removeEventListener("mousedown", handleClick);
    }, [rolePickerOpen]);

    useEffect(() => {
      const owner = ++session.current;
      pendingMutation.current = false;
      setMutation(null);
      setSaveError(false);
      setLoadError(false);
      setLoading(!!requestedTeamId);
      setLoadedTeamId(requestedTeamId ? undefined : null);
      setRolePickerOpen(false);
      setShowDeleteConfirm(false);
      setExistingTeamId(null);
      setTeamName("");
      setTeamDescription("");
      setTeamAvatar(null);
      setTeamTagsInput("");
      setTeamInstructions("");
      setStarterPromptRows([]);
      setMembers([]);
      setDefaultMemberId(null);
      if (requestedTeamId) {
        void teamApi
          .get(requestedTeamId)
          .then((team) => {
            if (owner !== session.current) return;
            setExistingTeamId(team.id);
            setTeamName(team.name);
            setTeamDescription(team.description);
            setTeamAvatar(team.avatar ?? null);
            setTeamTagsInput(tagsToInput(team.tags));
            setTeamInstructions(team.team_instructions);
            setStarterPromptRows(
              starterPromptsToDraftRows(team.starter_prompts),
            );
            setMembers(team.members);
            setDefaultMemberId(team.default_member_id ?? null);
            setLoadedTeamId(requestedTeamId);
            setLoading(false);
          })
          .catch(() => {
            if (owner !== session.current) return;
            setLoadError(true);
            setLoading(false);
          });
      }
      return () => {
        session.current = owner + 1;
      };
    }, [requestedTeamId, loadAttempt]);

    const handleAddRole = useCallback(
      (preset: PersonaPreset) => {
        const newMember: TeamMember = {
          member_id: generateMemberId(),
          persona_preset_id: preset.id,
          agent_id: null,
          model_id: null,
          role_name: preset.name,
          role_avatar: preset.avatar,
          role_tags: preset.tags,
          role_instructions: "",
          position: members.length,
          enabled: true,
        };
        setMembers((prev) => [...prev, newMember]);
        if (!defaultMemberId) setDefaultMemberId(newMember.member_id);
      },
      [members.length, defaultMemberId],
    );

    const handleRemoveMember = useCallback(
      (memberId: string) => {
        const nextMembers = members.filter((m) => m.member_id !== memberId);
        setMembers(nextMembers);
        setDefaultMemberId((current) =>
          current === memberId ? (nextMembers[0]?.member_id ?? null) : current,
        );
      },
      [members],
    );

    const handleInstructionsChange = useCallback(
      (memberId: string, text: string) => {
        setMembers((prev) =>
          prev.map((m) =>
            m.member_id === memberId ? { ...m, role_instructions: text } : m,
          ),
        );
      },
      [],
    );

    const handleToggleEnabled = useCallback((memberId: string) => {
      setMembers((prev) =>
        prev.map((m) =>
          m.member_id === memberId ? { ...m, enabled: !m.enabled } : m,
        ),
      );
    }, []);

    const handleModelChange = useCallback(
      (memberId: string, modelId: string | null) => {
        setMembers((prev) =>
          prev.map((m) =>
            m.member_id === memberId ? { ...m, model_id: modelId || null } : m,
          ),
        );
      },
      [],
    );

    const handleAgentChange = useCallback(
      (memberId: string, agentId: string | null) => {
        setMembers((prev) =>
          prev.map((m) =>
            m.member_id === memberId ? { ...m, agent_id: agentId || null } : m,
          ),
        );
      },
      [],
    );

    const handleSave = async () => {
      if (
        !ready ||
        !teamName.trim() ||
        pendingMutation.current ||
        avatarUploadingRef.current
      )
        return;
      const owner = session.current;
      pendingMutation.current = true;
      formRef.current?.focus({ preventScroll: true });
      setMutation("save");
      setSaveError(false);
      setRolePickerOpen(false);
      try {
        const payload: TeamCreateRequest = {
          name: teamName.trim(),
          description: teamDescription,
          avatar: teamAvatar,
          tags: inputToTags(teamTagsInput),
          team_instructions: teamInstructions,
          starter_prompts: draftRowsToStarterPrompts(starterPromptRows),
          default_member_id: defaultMemberId,
          members: members.map((m, idx) => ({
            member_id: m.member_id,
            persona_preset_id: m.persona_preset_id,
            agent_id: m.agent_id ?? null,
            model_id: m.model_id ?? null,
            role_name: m.role_name,
            role_avatar: m.role_avatar ?? null,
            role_tags: m.role_tags,
            role_instructions: m.role_instructions,
            position: idx,
            enabled: m.enabled,
          })),
        };
        const team = existingTeamId
          ? await teamApi.update(existingTeamId, payload)
          : await teamApi.create(payload);
        if (owner !== session.current) return;
        setExistingTeamId(team.id);
        toast.success(
          existingTeamId
            ? t("team.updateSuccess", "团队已更新")
            : t("team.createSuccess", "团队已创建"),
        );
        onSave?.(team);
      } catch {
        if (owner === session.current) setSaveError(true);
      } finally {
        if (owner === session.current) {
          pendingMutation.current = false;
          setMutation(null);
        }
      }
    };

    const handleClone = async () => {
      if (
        !ready ||
        !existingTeamId ||
        pendingMutation.current ||
        avatarUploadingRef.current
      )
        return;
      const owner = session.current;
      pendingMutation.current = true;
      formRef.current?.focus({ preventScroll: true });
      setMutation("clone");
      setSaveError(false);
      setRolePickerOpen(false);
      try {
        const cloned = await teamApi.clone(existingTeamId);
        if (owner !== session.current) return;
        setExistingTeamId(cloned.id);
        setTeamName(cloned.name);
        setTeamDescription(cloned.description);
        setTeamAvatar(cloned.avatar ?? null);
        setTeamTagsInput(tagsToInput(cloned.tags));
        setTeamInstructions(cloned.team_instructions);
        setStarterPromptRows(starterPromptsToDraftRows(cloned.starter_prompts));
        setMembers(cloned.members);
        setDefaultMemberId(cloned.default_member_id ?? null);
        toast.success(t("team.cloneSuccess", "团队已克隆"));
      } catch {
        if (owner === session.current)
          toast.error(t("team.cloneFailed", "克隆失败"));
      } finally {
        if (owner === session.current) {
          pendingMutation.current = false;
          setMutation(null);
        }
      }
    };

    const handleDelete = async () => {
      if (
        !ready ||
        !existingTeamId ||
        pendingMutation.current ||
        avatarUploadingRef.current
      )
        return;
      const owner = session.current;
      pendingMutation.current = true;
      setMutation("delete");
      try {
        await teamApi.delete(existingTeamId);
        if (owner !== session.current) return;
        toast.success(t("team.deleteSuccess", "团队已删除"));
        setShowDeleteConfirm(false);
        onClose?.();
      } catch {
        if (owner === session.current)
          toast.error(t("team.deleteFailed", "删除失败"));
      } finally {
        if (owner === session.current) {
          pendingMutation.current = false;
          setMutation(null);
        }
      }
    };

    const activeMemberCount = members.filter((member) => member.enabled).length;
    const configuredMemberCount = members.filter((member) =>
      member.role_instructions.trim(),
    ).length;
    const defaultMember = members.find(
      (member) => member.member_id === defaultMemberId,
    );
    return (
      <div
        className={`team-editor-shell ${
          surface === "sidebar" ? "team-editor-shell--sidebar" : ""
        }`}
      >
        <form
          ref={formRef}
          tabIndex={-1}
          aria-busy={(!ready && !loadError) || mutation !== null}
          className="es-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSave();
          }}
        >
          {!ready &&
            (loadError ? (
              <div className="flex flex-col gap-3">
                <ConfigPanelErrorCallout message={t("common.loadFailed")} />
                <Button
                  className="self-start"
                  onClick={() => {
                    formRef.current?.focus({ preventScroll: true });
                    setLoadAttempt((attempt) => attempt + 1);
                  }}
                >
                  {t("common.retry")}
                </Button>
              </div>
            ) : (
              <div
                role="status"
                className="flex items-center justify-center gap-2 py-6 text-13 text-theme-text-secondary"
              >
                <LoadingSpinner size="sm" />
                <span>{t("team.loading")}</span>
              </div>
            ))}
          {ready && (
            <fieldset disabled={busy} className="contents">
              {/* Profile: Avatar + Name + Description */}
              <div className="ppe-profile-section">
                <AvatarSection
                  key={existingTeamId ?? "new"}
                  avatar={teamAvatar ?? ""}
                  onAvatarChange={(avatar) => setTeamAvatar(avatar || null)}
                  onUploadingChange={handleAvatarUploadingChange}
                />

                <div className="ppe-profile-fields">
                  <div className="ppe-field">
                    <label className="ppe-label" htmlFor={`${fieldId}-name`}>
                      {t("team.teamName")}{" "}
                      <span className="ppe-required" aria-hidden="true">
                        *
                      </span>
                    </label>
                    <input
                      id={`${fieldId}-name`}
                      required
                      type="text"
                      value={teamName}
                      onChange={(e) => setTeamName(e.target.value)}
                      placeholder={t("team.teamNamePlaceholder")}
                      className="ppe-input"
                    />
                  </div>
                  <div className="ppe-field">
                    <label
                      className="ppe-label"
                      htmlFor={`${fieldId}-description`}
                    >
                      {t("team.description")}
                    </label>
                    <input
                      type="text"
                      id={`${fieldId}-description`}
                      value={teamDescription}
                      onChange={(e) => setTeamDescription(e.target.value)}
                      placeholder={t("team.descriptionPlaceholder")}
                      className="ppe-input"
                    />
                  </div>
                  <div className="ppe-field">
                    <label className="ppe-label" htmlFor={`${fieldId}-tags`}>
                      <Tag size={13} className="ppe-label-icon" />
                      {t("team.tags", "标签")}
                    </label>
                    <input
                      type="text"
                      id={`${fieldId}-tags`}
                      value={teamTagsInput}
                      onChange={(e) => setTeamTagsInput(e.target.value)}
                      placeholder={t(
                        "team.tagsPlaceholder",
                        "例如：研究, 写作",
                      )}
                      className="ppe-input"
                    />
                  </div>
                </div>
              </div>

              {/* Team instructions */}
              <div className="ppe-field">
                <label
                  className="ppe-label"
                  htmlFor={`${fieldId}-instructions`}
                >
                  <MessageSquareText size={13} className="ppe-label-icon" />
                  {t("team.instructions")}
                </label>
                <div className="ppe-textarea-wrap">
                  <textarea
                    id={`${fieldId}-instructions`}
                    aria-describedby={`${fieldId}-instructions-hint`}
                    value={teamInstructions}
                    onChange={(e) => setTeamInstructions(e.target.value)}
                    placeholder={t("team.instructionsPlaceholder")}
                    className="ppe-textarea"
                    rows={4}
                  />
                </div>
                <span
                  id={`${fieldId}-instructions-hint`}
                  className="text-12 leading-relaxed text-theme-text-secondary"
                >
                  {t("team.instructionsHint")}
                </span>
              </div>

              <StarterPromptsEditor
                prompts={starterPromptRows}
                onChange={setStarterPromptRows}
              />

              {/* Team members */}
              <div className="ppe-field" style={{ gap: "0.75rem" }}>
                <div className="tmb-header">
                  <div className="tmb-header__row">
                    <label className="ppe-label">
                      <Users size={13} className="ppe-label-icon" />
                      {t("team.teamMembers")}
                    </label>
                    <span className="tmb-default">
                      <Users size={11} />
                      <span>
                        {defaultMember?.role_name || t("team.notSet")}
                      </span>
                    </span>
                  </div>
                  <div className="tmb-stats">
                    <span className="tmb-stat">
                      <span className="tmb-stat__dot" />
                      {t("team.selected", { count: members.length })}
                    </span>
                    <span className="tmb-stat tmb-stat--active">
                      <span className="tmb-stat__dot" />
                      {t("team.active", { count: activeMemberCount })}
                    </span>
                    <span className="tmb-stat tmb-stat--configured">
                      <span className="tmb-stat__dot" />
                      {t("team.configured", { count: configuredMemberCount })}
                    </span>
                  </div>
                </div>

                <div ref={rolePickerRef}>
                  <button
                    ref={rolePickerTriggerRef}
                    type="button"
                    aria-expanded={rolePickerOpen}
                    aria-controls={rolePickerOpen ? rolePickerId : undefined}
                    onClick={() => {
                      setRolePickerOpen((v) => !v);
                      setSearchQuery("");
                      setPresetsPage(1);
                    }}
                    className={`team-role-picker-trigger ${
                      rolePickerOpen ? "team-role-picker-trigger--open" : ""
                    }`}
                  >
                    <Plus size={14} />
                    <span>
                      {members.length === 0
                        ? t("team.addRoles")
                        : t("team.addAnotherRole")}
                    </span>
                    <ChevronDown
                      size={14}
                      className={`team-role-picker-trigger__chevron ${
                        rolePickerOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {rolePickerOpen && (
                    <div
                      id={rolePickerId}
                      className="team-role-picker-dropdown"
                      role="group"
                      aria-label={t("team.addRoles")}
                      onKeyDown={(event) => {
                        if (event.key !== "Escape") return;
                        event.stopPropagation();
                        if (
                          event.nativeEvent.isComposing ||
                          event.keyCode === 229
                        )
                          return;
                        event.preventDefault();
                        setRolePickerOpen(false);
                        rolePickerTriggerRef.current?.focus();
                      }}
                    >
                      <div className="team-role-picker-dropdown__search">
                        <Search
                          size={14}
                          className="team-role-picker-dropdown__search-icon"
                        />
                        <PanelSearchInput
                          ref={roleSearchRef}
                          type="text"
                          value={searchQuery}
                          onValueChange={(query) => {
                            setSearchQuery(query);
                            setPresetsPage(1);
                          }}
                          aria-label={t("team.searchRoles")}
                          placeholder={t("team.searchRoles")}
                          className="ppe-input"
                          style={{ paddingLeft: "2.25rem" }}
                          autoFocus
                        />
                      </div>
                      <div
                        ref={roleListRef}
                        aria-busy={presetsLoading}
                        className="team-role-picker-dropdown__list"
                      >
                        {presetsLoading && (
                          <div
                            role="status"
                            className="team-form-empty flex items-center justify-center gap-2"
                          >
                            <LoadingSpinner size="sm" />
                            {t("team.loadingRoles")}
                          </div>
                        )}
                        {!presetsLoading && presetsError && (
                          <div className="flex flex-col gap-2">
                            <ConfigPanelErrorCallout
                              message={t("common.loadFailed")}
                            />
                            <Button
                              className="self-start"
                              onClick={() => {
                                roleSearchRef.current?.focus();
                                setPresetsAttempt((attempt) => attempt + 1);
                              }}
                            >
                              {t("common.retry")}
                            </Button>
                          </div>
                        )}
                        {!presetsLoading &&
                          !presetsError &&
                          presets.length === 0 && (
                            <div className="team-form-empty">
                              {t("team.noRolesFound")}
                            </div>
                          )}
                        {!presetsLoading &&
                          !presetsError &&
                          presets.map((preset) => (
                            <button
                              key={preset.id}
                              type="button"
                              className="team-form-role-option"
                              onClick={() => handleAddRole(preset)}
                            >
                              <span className="team-form-role-option__name font-serif">
                                {preset.name}
                              </span>
                              {preset.description && (
                                <span className="team-form-role-option__desc">
                                  {preset.description}
                                </span>
                              )}
                            </button>
                          ))}
                      </div>
                      {!presetsLoading && !presetsError && (
                        <Pagination
                          page={presetsPage}
                          pageSize={ROLE_PAGE_SIZE}
                          total={presetsTotal}
                          onChange={(page) => {
                            roleSearchRef.current?.focus();
                            setPresetsPage(page);
                          }}
                        />
                      )}
                    </div>
                  )}
                </div>

                {members.length > 0 && (
                  <div className="team-form-selected__list">
                    {members.map((member) => (
                      <TeamMemberCard
                        disabled={busy}
                        key={member.member_id}
                        member={member}
                        isDefault={member.member_id === defaultMemberId}
                        onRemove={() => handleRemoveMember(member.member_id)}
                        onSetDefault={() =>
                          setDefaultMemberId(member.member_id)
                        }
                        onToggleEnabled={() =>
                          handleToggleEnabled(member.member_id)
                        }
                        onInstructionsChange={(text) =>
                          handleInstructionsChange(member.member_id, text)
                        }
                        availableModels={availableModels ?? []}
                        onModelChange={(modelId) =>
                          handleModelChange(member.member_id, modelId)
                        }
                        availableAgents={availableAgents}
                        onAgentChange={(agentId) =>
                          handleAgentChange(member.member_id, agentId)
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
            </fieldset>
          )}
        </form>

        <ConfirmDialog
          isOpen={showDeleteConfirm}
          title={t("team.confirmDelete", "确认删除")}
          message={t(
            "team.confirmDeleteMessage",
            "确定要删除该团队吗？此操作不可撤销。",
          )}
          confirmText={t("common.delete", "删除")}
          cancelText={t("common.cancel", "取消")}
          variant="danger"
          loading={isDeleting}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      </div>
    );
  },
);
