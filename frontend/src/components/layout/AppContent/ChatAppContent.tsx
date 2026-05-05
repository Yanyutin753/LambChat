import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { usePersonaPresets } from "../../../hooks/usePersonaPresets";
import { useProjectManager } from "../../../hooks/useProjectManager";
import { useSessionConfig } from "../../../hooks/useSessionConfig";
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
import { buildEffectiveSkills, countEnabledSkills } from "./skillAvailability";
import { AppShell } from "./AppShell";
import { ChatView } from "./ChatView";
import { shouldShowMessageOutline } from "./messageOutline";

export interface ChatAppContentProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: import("../../../types").VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
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
}: ChatAppContentProps) {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { enableSkills, settings, availableModels, defaultModel } =
    useSettingsContext();
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
  } = useSkills({ enabled: enableSkills });

  const canReadPersonaPresets = hasPermission(Permission.PERSONA_PRESET_READ);
  const canManagePersonaPresets =
    hasPermission(Permission.PERSONA_PRESET_WRITE) ||
    hasPermission(Permission.PERSONA_PRESET_ADMIN);
  const {
    presets: personaPresets,
    isLoading: personaPresetsLoading,
    isMutating: personaPresetsMutating,
    usePreset: activatePersonaPreset,
    copyPreset: copyPersonaPreset,
    createPreset: createPersonaPreset,
    updatePreset: updatePersonaPreset,
  } = usePersonaPresets({ enabled: canReadPersonaPresets });

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
    sendMessage,
    stopGeneration,
    clearMessages,
    switchAgent,
    loadHistory,
    setPendingProjectId,
    autoExpandProjectId,
    clearAutoExpandProjectId,
    currentProjectId,
  } = useAgent({
    onApprovalRequired: (approval) => {
      addApproval({
        id: approval.id,
        message: approval.message,
        type: "form",
        fields: approval.fields || [],
        status: "pending",
        session_id: sessionId,
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
    onStreamDone: () => {
      if (sessionId) {
        import("../../../services/api").then(({ sessionApi }) => {
          sessionApi
            .get(sessionId)
            .then((session) => {
              if (session?.name) setSessionName(session.name);
            })
            .catch(() => {});
        });
      }
    },
  });

  const prevAgentRef = useRef(currentAgent);
  useEffect(() => {
    if (prevAgentRef.current !== currentAgent) {
      prevAgentRef.current = currentAgent;
      refreshToolsForAgent(currentAgent);
    }
  }, [currentAgent, refreshToolsForAgent]);

  const filteredModels = useMemo(() => {
    if (!availableModels) return null;
    if (!agentAllowedModelIds || agentAllowedModelIds.length === 0)
      return availableModels;
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
      setPersonaPreset(personaId, state.personaSnapshot);
      return;
    }
    try {
      const raw = localStorage.getItem("lambchat_session_config");
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed.personaPresetId === personaId && parsed.personaSnapshot) {
        setPersonaPreset(personaId, parsed.personaSnapshot);
      }
    } catch {
      /* ignore */
    }
  }, [location.state, searchParams, setSearchParams, setPersonaPreset]);

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
        setPersonaPreset(preset.id, snapshot);
      }
      return snapshot;
    },
    [activatePersonaPreset, setPersonaPreset],
  );

  const handleCopyPersonaPreset = useCallback(
    async (preset: PersonaPreset) => {
      await copyPersonaPreset(preset.id);
    },
    [copyPersonaPreset],
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

  const effectiveSkills = useMemo(() => {
    return buildEffectiveSkills({
      skills,
      skillsLoading,
      personaSkillNames: sessionConfig.personaSnapshot?.skill_names,
      disabledSkillNames: sessionConfig.disabledSkills,
    });
  }, [
    skills,
    sessionConfig.disabledSkills,
    sessionConfig.personaSnapshot,
    skillsLoading,
  ]);

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
      effectiveSkills
        .filter((s) => s.source === category)
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
    [effectiveSkills, sessionConfig.disabledSkills, toggleSessionSkill],
  );

  const effectiveToggleAllSkills = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      effectiveSkills.forEach((s) => {
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
    [effectiveSkills, sessionConfig.disabledSkills, toggleSessionSkill],
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
    onSessionUnread: (sid, count, projectId, isFavorite) => {
      sidebarRef.current?.updateSessionUnread(
        sid,
        count,
        projectId,
        isFavorite,
      );
    },
  });

  const [sessionName, setSessionName] = useState<string | null>(null);
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
  const externalNavigationToken =
    externalNavigationTargetFile || externalScrollToBottom
      ? location.key
      : null;

  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const fetchSessionName = async () => {
      try {
        const { sessionApi } = await import("../../../services/api");
        const session = await sessionApi.get(sessionId);
        if (session?.name) setSessionName(session.name);
      } catch (err) {
        console.warn("[AppContent] Failed to fetch session:", err);
      }
    };

    fetchSessionName();
  }, [sessionId]);

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

  useEffect(() => {
    if (newlyCreatedSession?.name && sessionId === newlyCreatedSession.id) {
      setSessionName(newlyCreatedSession.name);
    }
  }, [newlyCreatedSession?.name, newlyCreatedSession?.id, sessionId]);

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
    }) => {
      console.log("[AppContent] Restoring session config:", config);

      isSessionRestoredRef.current = true;

      if (config.agent_id) {
        switchAgent(config.agent_id);
      }

      restoreSessionConfig(config);

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
    [restoreSessionConfig, restoreAgentOptions, switchAgent],
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
      availableModels={filteredModels}
      currentModelId={currentModelId}
      onSelectModel={handleSelectModel}
      sessionId={sessionId}
      sessionName={sessionName}
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
        />
      }
    >
      <>
        {isPageDragging && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-stone-500/5 transition-colors dark:bg-stone-500/10">
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
          sessionName={sessionName}
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
          enabledSkillsCount={countEnabledSkills(effectiveSkills)}
          totalSkillsCount={effectiveSkills.length}
          enableSkills={enableSkills}
          personaPresets={personaPresets}
          selectedPersonaPresetId={sessionConfig.personaPresetId}
          selectedPersonaName={sessionConfig.personaSnapshot?.name || null}
          personaSkillsControlled={false}
          personaPresetsLoading={personaPresetsLoading}
          personaPresetsMutating={personaPresetsMutating}
          onUsePersonaPreset={handleUsePersonaPreset}
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
          approvals={approvals}
          onRespondApproval={respondToApproval}
          approvalLoading={approvalLoading}
          onSendMessage={sendMessage}
          onStopGeneration={stopGeneration}
          attachments={pageDragAttachments}
          onAttachmentsChange={setPageDragAttachments}
          settings={settings || {}}
          i18n={i18n}
          externalNavigationToken={externalNavigationToken}
          externalNavigationTargetFile={externalNavigationTargetFile}
          externalNavigationPreview={externalNavigationPreviewRequest}
          externalNavigationTargetRunId={externalNavigationTargetRunId}
          externalNavigationTargetRunPending={
            externalNavigationTargetRunPending
          }
          externalScrollToBottom={externalScrollToBottom}
          outlineToggleRef={outlineToggleRef}
        />
        <BlockPreviewPortal />
      </>
    </AppShell>
  );
}
