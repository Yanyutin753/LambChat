import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useLocation, useSearchParams } from "react-router-dom";
import { BlockPreviewPortal } from "../../chat/ChatMessage/items/McpBlockPreview";
import { SessionSidebar } from "../../panels/SessionSidebar";
import type { SessionSidebarHandle } from "../../panels/SessionSidebar";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { useAgent } from "../../../hooks/useAgent";
import { useApprovals } from "../../../hooks/useApprovals";
import { useAuth } from "../../../hooks/useAuth";
import { useTools } from "../../../hooks/useTools";
import { useSkills } from "../../../hooks/useSkills";
import { personaPresetApi, sessionApi } from "../../../services/api";
import { usePersonaPresets } from "../../../hooks/usePersonaPresets";
import { useProjectManager } from "../../../hooks/useProjectManager";
import { appNotificationService } from "../../../services/notifications/appNotificationService";
import { useSessionConfig } from "../../../hooks/useSessionConfig";
import {
  buildSessionOptionContributions,
  hasAgentCatalogEntryContribution,
} from "../../../extensions/coreContributions";
import {
  Permission,
  type ToolCategory,
  type SkillSource,
  type PersonaPreset,
  type PersonaPresetSnapshot,
} from "../../../types";
import { useDragAndDrop } from "./useDragAndDrop";
import { useWebSocketNotifications } from "./useWebSocketNotifications";
import { useAgentOptions } from "./useAgentOptions";
import { useSessionSync } from "./useSessionSync";
import {
  getExternalNavigationPreviewRequest,
  getExternalNavigationTargetFile,
  shouldScrollToBottomAfterExternalNavigation,
} from "./externalNavigationState";
import {
  reconcileCurrentModelSelection,
  resolveDefaultModelSelection,
} from "./modelSelection";
import { getRestoredModelSelection } from "./sessionState";
import { getTeamRouteRequest } from "./teamRouteState";
import { resolvePersonaAgentId } from "../../../hooks/useAgent/agentSelection";
import { firstEffectivePluginOptionPath } from "../../../extensions/pluginOptions";
import { AppShell } from "./AppShell";
import { ChatView } from "./ChatView";
import { shouldShowMessageOutline } from "./messageOutline";
import { buildEffectiveSkills, countEnabledSkills } from "./skillAvailability";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";

const SCHEDULED_TASK_DEFAULTS_KEY = "lambchat_scheduled_task_defaults";
const CHAT_SKILL_LIST_PARAMS = { limit: 100 };

export interface ChatAppContentProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: import("../../../types").VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function ChatAppContent({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  sidebarCollapsed,
  setSidebarCollapsed,
  mobileSidebarOpen,
  setMobileSidebarOpen,
  onShowProfile,
  runtimePlugins,
}: ChatAppContentProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { enableSkills, availableModels, defaultModel } = useSettingsContext();
  const { hasPermission, isAuthenticated } = useAuth();

  const { isPageDragging, pageDragAttachments, setPageDragAttachments } =
    useDragAndDrop();

  const {
    approvals,
    respondToApproval,
    addApproval,
    clearApprovals,
    isLoading: approvalLoading,
  } = useApprovals({ sessionId: null });

  const {
    tools,
    isLoading: toolsLoading,
    totalCount: totalToolsCount,
    getDisabledToolNames,
    refreshToolsForAgent,
  } = useTools();

  const {
    skills,
    isLoading: skillsLoading,
    pendingSkillNames,
    isMutating: skillsMutating,
    fetchSkills,
  } = useSkills({ enabled: enableSkills, listParams: CHAT_SKILL_LIST_PARAMS });

  const canReadPersonaPresets = hasPermission(Permission.PERSONA_PRESET_READ);
  const canManagePersonaPresets =
    hasPermission(Permission.PERSONA_PRESET_WRITE) ||
    hasPermission(Permission.PERSONA_PRESET_ADMIN);
  const [personaPresetPage, setPersonaPresetPage] = useState(1);
  const [personaPresetQuery, setPersonaPresetQuery] = useState("");
  const [personaPresetTag, setPersonaPresetTag] = useState<string | null>(null);
  const personaPresetPageSize = 12;
  const personaPresetListParams = useMemo(
    () => ({
      skip: (personaPresetPage - 1) * personaPresetPageSize,
      limit: personaPresetPageSize,
      q: personaPresetQuery.trim() || undefined,
      tag: personaPresetTag || undefined,
    }),
    [personaPresetPage, personaPresetQuery, personaPresetTag],
  );
  const {
    presets: personaPresets,
    total: personaPresetsTotal,
    isLoading: personaPresetsLoading,
    isLoadingMore: personaPresetsLoadingMore,
    isMutating: personaPresetsMutating,
    usePreset: activatePersonaPreset,
    updatePreference: updatePersonaPreference,
    copyPreset: copyPersonaPreset,
    createPreset: createPersonaPreset,
    updatePreset: updatePersonaPreset,
    loadMore: loadMorePersonaPresets,
  } = usePersonaPresets({
    enabled: canReadPersonaPresets,
    listParams: personaPresetListParams,
  });

  const handlePersonaPresetSearchChange = useCallback((query: string) => {
    setPersonaPresetQuery(query);
  }, []);
  const handlePersonaPresetTagChange = useCallback((tag: string | null) => {
    setPersonaPresetTag(tag);
  }, []);

  const hasMorePersonaPresets = personaPresets.length < personaPresetsTotal;
  const handleLoadMorePersonaPresets = useCallback(() => {
    if (!hasMorePersonaPresets || personaPresetsLoadingMore) return;
    loadMorePersonaPresets(personaPresetListParams);
  }, [
    hasMorePersonaPresets,
    personaPresetsLoadingMore,
    loadMorePersonaPresets,
    personaPresetListParams,
  ]);

  const projectManager = useProjectManager();

  const sessionConfigRef = useRef({
    disabledSkills: [] as string[],
    enabledSkills: undefined as string[] | undefined,
    personaPresetId: null as string | null,
    disabledMcpTools: [] as string[],
    agentOptions: {} as Record<string, boolean | string | number>,
  });

  const {
    messages,
    sessionId,
    currentRunId,
    isLoading,
    isLoadingHistory,
    agents,
    currentAgent,
    allowedModelIds: agentAllowedModelIds,
    connectionStatus,
    newlyCreatedSession,
    activeGoal,
    goalsByRunId,
    sendMessage,
    clearActiveGoal,
    stopGeneration,
    clearMessages,
    switchAgent,
    selectedTeamId,
    sessionPluginOptions,
    setSessionPluginOption,
    loadHistory,
    setPendingProjectId,
    autoExpandProjectId,
    clearAutoExpandProjectId,
    currentProjectId,
  } = useAgent({
    runtimePlugins,
    onApprovalRequired: (approval) => {
      void appNotificationService.notify({
        type: "approval",
        title: t("approvals.needsConfirmation"),
        body: approval.message,
        route: sessionId ? `/chat/${sessionId}` : "/chat",
        dedupeKey: `approval:${approval.id}`,
        importance: "high",
      });
      addApproval({
        id: approval.id,
        message: approval.message,
        type: "form",
        fields: approval.fields || [],
        status: "pending",
        session_id: sessionId,
        metadata: approval.metadata,
      });
    },
    onClearApprovals: () => {
      clearApprovals();
    },
    getEnabledTools: getDisabledToolNames,
    getDisabledSkills: () => sessionConfigRef.current.disabledSkills,
    getEnabledSkills: () => sessionConfigRef.current.enabledSkills,
    getPersonaPresetId: () => sessionConfigRef.current.personaPresetId,
    getDisabledMcpTools: () => sessionConfigRef.current.disabledMcpTools,
    getAgentOptions: () => sessionConfigRef.current.agentOptions,
    onSkillAdded: (
      skillName: string,
      _description: string,
      filesCount: number,
    ) => {
      console.log(
        `[AppContent] Skill added: ${skillName} (${filesCount} files), refreshing skills list`,
      );
      setTimeout(() => fetchSkills(), 500);
    },
  });

  const sessionOptionContributions = useMemo(
    () =>
      buildSessionOptionContributions(runtimePlugins, {
        agentId: currentAgent,
      }),
    [currentAgent, runtimePlugins],
  );

  const isDeclaredEffectiveSessionPluginOption = useCallback(
    (pluginId: string, key: string) =>
      sessionOptionContributions.some(
        (option) =>
          option.pluginId === pluginId && option.key === key && option.effective,
      ),
    [sessionOptionContributions],
  );

  const persistSessionPluginOption = useCallback(
    (pluginId: string, key: string, value: unknown) => {
      if (!sessionId) return;
      sessionApi
        .updatePluginOption(
          sessionId,
          pluginId,
          key,
          value === "" ? null : value,
        )
        .catch((error) => {
          console.warn("[AppContent] Failed to persist plugin session option:", error);
          toast.error(t("plugins.sessionOptionSaveFailed", "Failed to save plugin option"));
        });
    },
    [sessionId, t],
  );

  const handlePluginOptionChange = useCallback(
    (pluginId: string, key: string, value: unknown) => {
      setSessionPluginOption(pluginId, key, value);
      if (isDeclaredEffectiveSessionPluginOption(pluginId, key)) {
        persistSessionPluginOption(pluginId, key, value);
      }
    },
    [
      isDeclaredEffectiveSessionPluginOption,
      persistSessionPluginOption,
      setSessionPluginOption,
    ],
  );

  const switchToPersonaAgentMode = useCallback(() => {
    const isPluginAgent = hasAgentCatalogEntryContribution(currentAgent, runtimePlugins);
    if (!isPluginAgent) return;
    const nextAgentId = resolvePersonaAgentId(currentAgent, undefined, agents, [currentAgent]);
    if (nextAgentId && nextAgentId !== currentAgent) {
      switchAgent(nextAgentId);
    }
    sessionOptionContributions
      .filter((option) => option.effective)
      .forEach((option) => {
        handlePluginOptionChange(option.pluginId, option.key, null);
      });
  }, [
    agents,
    currentAgent,
    handlePluginOptionChange,
    runtimePlugins,
    sessionOptionContributions,
    switchAgent,
  ]);

  const prevAgentRef = useRef(currentAgent);
  useEffect(() => {
    if (prevAgentRef.current !== currentAgent) {
      prevAgentRef.current = currentAgent;
      refreshToolsForAgent(currentAgent);
    }
  }, [currentAgent, refreshToolsForAgent]);

  const filteredModels = useMemo(() => {
    if (!availableModels) return null;
    if (agentAllowedModelIds === null) return availableModels;
    if (agentAllowedModelIds.length === 0) return [];
    return availableModels.filter((m) => agentAllowedModelIds.includes(m.id));
  }, [availableModels, agentAllowedModelIds]);

  const {
    agentOptionValues,
    currentAgentOptions,
    handleToggleAgentOption,
    restoreAgentOptions,
    resetAgentOptionDefaults,
  } = useAgentOptions(agents, currentAgent);

  const {
    config: sessionConfig,
    toggleSkill: toggleSessionSkill,
    toggleMcpTool: toggleSessionMcpTool,
    setAgentOption: setSessionAgentOption,
    setPersonaPreset,
    clearPersonaPreset,
    resetToDefaults,
    restoreConfig: restoreSessionConfig,
  } = useSessionConfig({
    getDefaultAgentOptions: () => agentOptionValues,
  });

  const [currentModelId, setCurrentModelId] = useState<string>(() => {
    return localStorage.getItem("defaultModelId") || "";
  });
  const [currentModelValue, setCurrentModelValue] = useState<string>(
    () => localStorage.getItem("defaultModel") || defaultModel,
  );

  const isSessionRestoredRef = useRef(false);
  const lastTeamRouteRequestRef = useRef<string | null>(null);

  // Restore persona from localStorage when navigating from /persona page
  useEffect(() => {
    const personaId = searchParams.get("persona");
    if (!personaId) return;
    const state = location.state as
      | {
          personaPresetId?: string;
          personaSnapshot?: PersonaPresetSnapshot;
        }
      | null
      | undefined;
    setSearchParams(
      (prev) => {
        prev.delete("persona");
        return prev;
      },
      { replace: true },
    );
    if (
      state?.personaPresetId === personaId &&
      state.personaSnapshot?.preset_id === personaId
    ) {
      switchToPersonaAgentMode();
      setPersonaPreset(personaId, state.personaSnapshot);
      return;
    }
    try {
      const raw = localStorage.getItem("lambchat_session_config");
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed.personaPresetId === personaId && parsed.personaSnapshot) {
        switchToPersonaAgentMode();
        setPersonaPreset(personaId, parsed.personaSnapshot);
      }
    } catch {
      /* ignore */
    }
  }, [
    location.state,
    searchParams,
    setSearchParams,
    setPersonaPreset,
    switchToPersonaAgentMode,
  ]);

  useEffect(() => {
    const teamRequest = getTeamRouteRequest(searchParams, location.state);
    if (!teamRequest) return;
    if (!hasAgentCatalogEntryContribution(teamRequest.agentId, runtimePlugins)) {
      return;
    }
    const requestKey = `${teamRequest.agentId}:${teamRequest.teamId}`;
    if (lastTeamRouteRequestRef.current === requestKey) return;

    const optionPath = firstEffectivePluginOptionPath(
      buildSessionOptionContributions(runtimePlugins, {
        agentId: teamRequest.agentId,
      }),
      { effectiveOnly: true },
    );
    if (!optionPath) return;
    lastTeamRouteRequestRef.current = requestKey;

    switchAgent(teamRequest.agentId);
    setSessionPluginOption(
      optionPath.pluginId,
      optionPath.key,
      teamRequest.teamId,
    );
    setSearchParams(
      (prev) => {
        prev.delete("agent");
        prev.delete("team");
        return prev;
      },
      { replace: true },
    );
  }, [location.state, runtimePlugins, searchParams, setSearchParams, setSessionPluginOption, switchAgent]);

  useEffect(() => {
    if (isSessionRestoredRef.current) return;
    const nextSelection = reconcileCurrentModelSelection({
      availableModels,
      currentModelId,
      currentModelValue,
      storedDefaultId: localStorage.getItem("defaultModelId") || "",
      storedDefaultValue: localStorage.getItem("defaultModel") || "",
      fallbackDefaultValue: defaultModel,
    });

    if (nextSelection.modelId && nextSelection.modelId !== currentModelId) {
      setCurrentModelId(nextSelection.modelId);
    }
    if (
      nextSelection.modelValue &&
      nextSelection.modelValue !== currentModelValue
    ) {
      setCurrentModelValue(nextSelection.modelValue);
    }
  }, [availableModels, currentModelId, currentModelValue, defaultModel]);

  useEffect(() => {
    handleToggleAgentOption("model", currentModelValue);
    setSessionAgentOption("model", currentModelValue);
    handleToggleAgentOption("model_id", currentModelId);
    setSessionAgentOption("model_id", currentModelId);
  }, [
    currentModelValue,
    currentModelId,
    handleToggleAgentOption,
    setSessionAgentOption,
  ]);

  useEffect(() => {
    if (!currentAgent && !currentModelId && !currentModelValue) return;
    localStorage.setItem(
      SCHEDULED_TASK_DEFAULTS_KEY,
      JSON.stringify({
        agentId: currentAgent,
        modelId: currentModelId,
        modelValue: currentModelValue,
      }),
    );
  }, [currentAgent, currentModelId, currentModelValue]);

  const handleSelectModel = useCallback(
    (modelId: string, modelValue: string) => {
      setCurrentModelId(modelId);
      setCurrentModelValue(modelValue);
    },
    [],
  );

  // Sync ref synchronously during render so getAgentOptions always has
  // the latest model_id — useEffect introduces a one-tick delay that
  // can cause model_id to be missing when using the default model.
  sessionConfigRef.current = {
    ...sessionConfig,
    enabledSkills: sessionConfig.personaSnapshot
      ? sessionConfig.personaSnapshot.skill_names
      : undefined,
    personaPresetId: sessionConfig.personaPresetId,
    agentOptions: {
      ...agentOptionValues,
      ...(currentModelValue ? { model: currentModelValue } : {}),
      ...(currentModelId ? { model_id: currentModelId } : {}),
    },
  };

  const handleUsePersonaPreset = useCallback(
    async (preset: PersonaPreset) => {
      const snapshot = await activatePersonaPreset(preset.id);
      if (snapshot) {
        switchToPersonaAgentMode();
        setPersonaPreset(preset.id, snapshot);
      }
      return snapshot;
    },
    [activatePersonaPreset, setPersonaPreset, switchToPersonaAgentMode],
  );

  const handleCopyPersonaPreset = useCallback(
    async (preset: PersonaPreset) => {
      await copyPersonaPreset(preset.id);
    },
    [copyPersonaPreset],
  );

  const handleTogglePersonaPreference = useCallback(
    async (
      preset: PersonaPreset,
      preference: { is_favorite?: boolean; is_pinned?: boolean },
    ) => {
      await updatePersonaPreference(preset.id, preference);
    },
    [updatePersonaPreference],
  );

  const handleSavePersonaPreset = useCallback(
    async (
      preset: PersonaPreset | null,
      data: {
        name: string;
        description: string;
        system_prompt: string;
        tags: string[];
        skill_names: string[];
      },
    ) => {
      if (preset) {
        await updatePersonaPreset(preset.id, data);
      } else {
        await createPersonaPreset(data);
      }
    },
    [createPersonaPreset, updatePersonaPreset],
  );

  const effectiveTools = useMemo(() => {
    const sessionDisabled = new Set(sessionConfig.disabledMcpTools);
    if (sessionDisabled.size === 0) return tools;
    return tools.map((t) => {
      if (t.category !== "mcp") return t;
      return { ...t, enabled: t.enabled && !sessionDisabled.has(t.name) };
    });
  }, [tools, sessionConfig.disabledMcpTools]);

  const effectiveSkills = useMemo(
    () =>
      buildEffectiveSkills({
        skills,
        skillsLoading,
        personaSkillNames: sessionConfig.personaSnapshot?.skill_names,
        disabledSkillNames: sessionConfig.disabledSkills,
      }),
    [
      skills,
      skillsLoading,
      sessionConfig.personaSnapshot?.skill_names,
      sessionConfig.disabledSkills,
    ],
  );
  const effectiveEnabledSkillsCount = useMemo(
    () => countEnabledSkills(effectiveSkills),
    [effectiveSkills],
  );

  const effectiveToggleTool = useCallback(
    (toolName: string) => {
      const tool = tools.find((t) => t.name === toolName);
      if (!tool) return;

      if (tool.category === "mcp") {
        toggleSessionMcpTool(toolName);
      }
    },
    [tools, toggleSessionMcpTool],
  );

  const effectiveToggleCategory = useCallback(
    (category: ToolCategory, enabled: boolean) => {
      if (category === "mcp") {
        tools
          .filter((t) => t.category === "mcp" && !t.system_disabled)
          .forEach((t) => {
            const isInSessionDisabled = sessionConfig.disabledMcpTools.includes(
              t.name,
            );
            if (enabled && isInSessionDisabled) {
              toggleSessionMcpTool(t.name);
            } else if (!enabled && !isInSessionDisabled) {
              toggleSessionMcpTool(t.name);
            }
          });
      }
    },
    [tools, sessionConfig.disabledMcpTools, toggleSessionMcpTool],
  );

  const effectiveToggleAll = useCallback(
    (enabled: boolean) => {
      tools
        .filter((t) => t.category === "mcp" && !t.system_disabled)
        .forEach((t) => {
          const isInSessionDisabled = sessionConfig.disabledMcpTools.includes(
            t.name,
          );
          if (enabled && isInSessionDisabled) {
            toggleSessionMcpTool(t.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionMcpTool(t.name);
          }
        });
    },
    [tools, sessionConfig.disabledMcpTools, toggleSessionMcpTool],
  );

  const effectiveToggleSkill = useCallback(
    async (name: string): Promise<boolean> => {
      toggleSessionSkill(name);
      return true;
    },
    [toggleSessionSkill],
  );

  const effectiveToggleSkillCategory = useCallback(
    async (category: SkillSource, enabled: boolean): Promise<boolean> => {
      skills
        .filter((s) => s.enabled && s.source === category)
        .forEach((s) => {
          const isInSessionDisabled = sessionConfig.disabledSkills.includes(
            s.name,
          );
          if (enabled && isInSessionDisabled) {
            toggleSessionSkill(s.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionSkill(s.name);
          }
        });
      return true;
    },
    [skills, sessionConfig.disabledSkills, toggleSessionSkill],
  );

  const effectiveToggleAllSkills = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      skills
        .filter((s) => s.enabled)
        .forEach((s) => {
          const isInSessionDisabled = sessionConfig.disabledSkills.includes(
            s.name,
          );
          if (enabled && isInSessionDisabled) {
            toggleSessionSkill(s.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionSkill(s.name);
          }
        });
      return true;
    },
    [skills, sessionConfig.disabledSkills, toggleSessionSkill],
  );

  const effectiveEnabledToolsCount = useMemo(
    () => effectiveTools.filter((t) => t.enabled).length,
    [effectiveTools],
  );

  const canSendMessage = hasPermission(Permission.CHAT_WRITE);

  const sidebarRef = useRef<SessionSidebarHandle>(null);

  useWebSocketNotifications({
    sessionId,
    enabled: isAuthenticated,
    onSessionUnread: (sid, count, projectId, isFavorite, scheduledTaskId) => {
      sidebarRef.current?.updateSessionUnread(
        sid,
        count,
        projectId,
        isFavorite,
        scheduledTaskId,
      );
    },
  });

  const [externalNavigationTargetRunId, setExternalNavigationTargetRunId] =
    useState<string | null>(null);
  const [
    externalNavigationTargetRunPending,
    setExternalNavigationTargetRunPending,
  ] = useState(false);
  const externalNavigationTargetFile = getExternalNavigationTargetFile(
    location.state,
  );
  const externalNavigationPreviewRequest = getExternalNavigationPreviewRequest(
    location.state,
  );
  const externalScrollToBottom = shouldScrollToBottomAfterExternalNavigation(
    location.state,
  );
  const externalNavigationRunId = searchParams.get("run_id")?.trim() || null;
  const externalNavigationToken =
    externalNavigationTargetFile ||
    externalScrollToBottom ||
    externalNavigationRunId
      ? location.key
      : null;
  const resolvedExternalNavigationTargetRunId =
    externalNavigationTargetRunId || externalNavigationRunId;

  useEffect(() => {
    const targetTraceId = externalNavigationTargetFile?.traceId ?? undefined;

    if (!sessionId || !targetTraceId) {
      setExternalNavigationTargetRunId(null);
      setExternalNavigationTargetRunPending(false);
      return;
    }

    let cancelled = false;
    setExternalNavigationTargetRunPending(true);

    const resolveTargetRunId = async () => {
      try {
        const { sessionApi } = await import("../../../services/api");
        const response = await sessionApi.getRuns(sessionId, {
          trace_id: targetTraceId,
        });
        if (cancelled) {
          return;
        }

        const matchedRun =
          response.runs.find((run) => run.trace_id === targetTraceId) ?? null;
        setExternalNavigationTargetRunId(matchedRun?.run_id ?? null);
        setExternalNavigationTargetRunPending(false);
      } catch (err) {
        if (!cancelled) {
          console.warn(
            "[AppContent] Failed to resolve external navigation run:",
            err,
          );
          setExternalNavigationTargetRunId(null);
          setExternalNavigationTargetRunPending(false);
        }
      }
    };

    resolveTargetRunId();

    return () => {
      cancelled = true;
    };
  }, [sessionId, externalNavigationTargetFile?.traceId]);

  const handleConfigRestored = useCallback(
    (config: {
      agent_id?: string;
      agent_options?: Record<string, boolean | string | number>;
      disabled_skills?: string[];
      enabled_skills?: string[];
      persona_preset_id?: string;
      persona_preset_name?: string;
      persona_snapshot?: import("../../../types").PersonaPresetSnapshot;
      disabled_mcp_tools?: string[];
      disabled_tools?: string[];
      team_id?: string;
      plugin_options?: Record<string, Record<string, unknown>>;
    }) => {
      console.log("[AppContent] Restoring session config:", config);

      isSessionRestoredRef.current = true;

      if (config.agent_id) {
        switchAgent(config.agent_id);
      }

      restoreSessionConfig(config);

      // Fetch latest persona snapshot by ID (API-first for normal views;
      // shared page uses its own SharedPage component and is unaffected).
      // The snapshot in metadata serves as a fallback until the API responds.
      if (config.persona_preset_id) {
        personaPresetApi
          .use(config.persona_preset_id)
          .then((snapshot) => {
            if (snapshot) {
              setPersonaPreset(config.persona_preset_id!, snapshot);
            }
          })
          .catch(() => {
            /* preset may have been deleted — keep metadata snapshot */
          });
      }

      if (config.agent_options) {
        restoreAgentOptions(config.agent_options);

        const restoredModelSelection = getRestoredModelSelection(config);
        if (restoredModelSelection.modelId) {
          setCurrentModelId(restoredModelSelection.modelId);
        }
        if (restoredModelSelection.modelValue) {
          setCurrentModelValue(restoredModelSelection.modelValue);
        }
      }
    },
    [
      restoreSessionConfig,
      restoreAgentOptions,
      switchAgent,
      setPersonaPreset,
    ],
  );

  const { handleSelectSession, handleNewSession } = useSessionSync({
    activeTab: "chat",
    sessionId,
    loadHistory,
    clearMessages,
    onConfigRestored: handleConfigRestored,
  });

  const handleNewSessionWithReset = useCallback(() => {
    const nextSelection = resolveDefaultModelSelection({
      availableModels,
      storedDefaultId: localStorage.getItem("defaultModelId") || "",
      storedDefaultValue: localStorage.getItem("defaultModel") || "",
      fallbackDefaultValue: defaultModel,
    });

    handleNewSession();
    resetToDefaults();

    resetAgentOptionDefaults();

    setCurrentModelId(nextSelection.modelId);
    setCurrentModelValue(nextSelection.modelValue);
  }, [
    availableModels,
    defaultModel,
    handleNewSession,
    resetToDefaults,
    resetAgentOptionDefaults,
  ]);

  const handleMobileClose = useCallback(
    () => setMobileSidebarOpen(false),
    [setMobileSidebarOpen],
  );
  const handleSelectSessionAndClose = useCallback(
    (id: string) => {
      handleSelectSession(id);
      setMobileSidebarOpen(false);
    },
    [handleSelectSession, setMobileSidebarOpen],
  );
  const handleNewSessionAndClose = useCallback(() => {
    handleNewSessionWithReset();
    setMobileSidebarOpen(false);
  }, [handleNewSessionWithReset, setMobileSidebarOpen]);

  const outlineToggleRef = useRef<(() => void) | null>(null);
  const handleToggleOutline = useCallback(() => {
    outlineToggleRef.current?.();
  }, []);

  return (
    <AppShell
      activeTab="chat"
      showProfileModal={showProfileModal}
      onCloseProfileModal={onCloseProfileModal}
      versionInfo={versionInfo}
      setMobileSidebarOpen={setMobileSidebarOpen}
      currentProjectId={currentProjectId}
      projectManager={projectManager}
      onNewSession={handleNewSessionWithReset}
      onShowProfile={onShowProfile}
      runtimePlugins={runtimePlugins}
      availableModels={filteredModels}
      currentModelId={currentModelId}
      onSelectModel={handleSelectModel}
      sessionId={sessionId}
      showOutlineButton={shouldShowMessageOutline(messages)}
      onToggleOutline={handleToggleOutline}
      sidebar={
        <SessionSidebar
          ref={sidebarRef}
          currentSessionId={sessionId}
          onSelectSession={handleSelectSessionAndClose}
          onNewSession={handleNewSessionAndClose}
          onSetPendingProjectId={setPendingProjectId}
          autoExpandProjectId={autoExpandProjectId}
          onConsumeAutoExpandProjectId={clearAutoExpandProjectId}
          newSession={newlyCreatedSession}
          mobileOpen={mobileSidebarOpen}
          onMobileClose={handleMobileClose}
          isCollapsed={sidebarCollapsed}
          onToggleCollapsed={setSidebarCollapsed}
          onShowProfile={onShowProfile}
          runtimePlugins={runtimePlugins}
        />
      }
    >
      <>
        {isPageDragging && (
          <div className="safe-area-viewport-padding fixed inset-0 z-[9999] flex items-center justify-center bg-stone-500/5 transition-colors dark:bg-stone-500/10">
            <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-stone-400 bg-white/95 px-16 py-12 shadow-xl transition-colors dark:border-stone-500 dark:bg-stone-800/95">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-12 w-12 text-stone-500 dark:text-stone-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                />
              </svg>
              <span className="text-lg font-medium text-stone-600 dark:text-stone-300">
                {t("chat.dropFilesHere", "Drop files here to upload")}
              </span>
            </div>
          </div>
        )}

        <ChatView
          messages={messages}
          sessionId={sessionId}
          currentRunId={currentRunId}
          isLoading={isLoading}
          isLoadingHistory={isLoadingHistory}
          connectionStatus={connectionStatus}
          canSendMessage={canSendMessage}
          tools={effectiveTools}
          onToggleTool={effectiveToggleTool}
          onToggleCategory={effectiveToggleCategory}
          onToggleAll={effectiveToggleAll}
          toolsLoading={toolsLoading}
          enabledToolsCount={effectiveEnabledToolsCount}
          totalToolsCount={totalToolsCount}
          skills={effectiveSkills}
          onToggleSkill={effectiveToggleSkill}
          onToggleSkillCategory={effectiveToggleSkillCategory}
          onToggleAllSkills={effectiveToggleAllSkills}
          skillsLoading={skillsLoading}
          pendingSkillNames={pendingSkillNames}
          skillsMutating={skillsMutating}
          enabledSkillsCount={effectiveEnabledSkillsCount}
          totalSkillsCount={effectiveSkills.length}
          enableSkills={enableSkills}
          personaPresets={personaPresets}
          personaPresetsTotal={personaPresetsTotal}
          hasMorePersonaPresets={hasMorePersonaPresets}
          isLoadingMorePersonaPresets={personaPresetsLoadingMore}
          onLoadMorePersonaPresets={handleLoadMorePersonaPresets}
          personaPresetsPage={personaPresetPage}
          onPersonaPresetsPageChange={setPersonaPresetPage}
          onPersonaPresetsSearchChange={handlePersonaPresetSearchChange}
          onPersonaPresetsTagChange={handlePersonaPresetTagChange}
          selectedPersonaPresetId={sessionConfig.personaPresetId}
          selectedPersonaName={sessionConfig.personaSnapshot?.name || null}
          selectedPersonaSnapshot={sessionConfig.personaSnapshot}
          personaSkillsControlled={false}
          personaPresetsLoading={personaPresetsLoading}
          personaPresetsMutating={personaPresetsMutating}
          onUsePersonaPreset={handleUsePersonaPreset}
          onTogglePersonaPreference={handleTogglePersonaPreference}
          onCopyPersonaPreset={handleCopyPersonaPreset}
          onSavePersonaPreset={handleSavePersonaPreset}
          onClearPersonaPreset={clearPersonaPreset}
          canManagePersonaPresets={canManagePersonaPresets}
          agentOptions={currentAgentOptions}
          agentOptionValues={agentOptionValues}
          onToggleAgentOption={handleToggleAgentOption}
          agents={agents}
          currentAgent={currentAgent}
          onSelectAgent={switchAgent}
          selectedTeamId={selectedTeamId}
          pluginOptionValues={sessionPluginOptions}
          onPluginOptionChange={handlePluginOptionChange}
          approvals={approvals}
          onRespondApproval={respondToApproval}
          approvalLoading={approvalLoading}
          onSendMessage={(content, sendAttachments, sendOptions) =>
            void sendMessage(content, undefined, sendAttachments, sendOptions)
          }
          onStopGeneration={stopGeneration}
          activeGoal={activeGoal}
          goalsByRunId={goalsByRunId}
          onClearActiveGoal={clearActiveGoal}
          attachments={pageDragAttachments}
          onAttachmentsChange={setPageDragAttachments}
          externalNavigationToken={externalNavigationToken}
          externalNavigationTargetFile={externalNavigationTargetFile}
          externalNavigationPreview={externalNavigationPreviewRequest}
          externalNavigationTargetRunId={resolvedExternalNavigationTargetRunId}
          externalNavigationTargetRunPending={
            externalNavigationTargetRunPending
          }
          externalScrollToBottom={externalScrollToBottom}
          outlineToggleRef={outlineToggleRef}
          runtimePlugins={runtimePlugins}
        />
        <BlockPreviewPortal />
      </>
    </AppShell>
  );
}
