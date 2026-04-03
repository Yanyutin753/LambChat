import {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { ProfileModal } from "../../profile/ProfileModal";
import { SessionSidebar } from "../../panels/SessionSidebar";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { useAgent } from "../../../hooks/useAgent";
import { useApprovals } from "../../../hooks/useApprovals";
import { useAuth } from "../../../hooks/useAuth";
import { useTools } from "../../../hooks/useTools";
import { useSkills } from "../../../hooks/useSkills";
import { useVersion } from "../../../hooks/useVersion";
import { useProjectManager } from "../../../hooks/useProjectManager";
import { useSessionConfig } from "../../../hooks/useSessionConfig";
import {
  Permission,
  type AgentInfo,
  type Project,
  type ToolCategory,
  type SkillSource,
} from "../../../types";
import type { VersionInfo } from "../../../types";
import type { TabType } from "./types";
import { useDragAndDrop } from "./useDragAndDrop";
import { useWebSocketNotifications } from "./useWebSocketNotifications";
import { useAgentOptions } from "./useAgentOptions";
import { useSessionSync } from "./useSessionSync";
import { ChatView } from "./ChatView";
import { Header } from "./Header";
import { TabContent } from "./TabContent";

interface AppContentProps {
  activeTab: TabType;
}

interface AppShellProps {
  activeTab: TabType;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  agents: AgentInfo[];
  currentAgent: string;
  agentsLoading: boolean;
  onSelectAgent: (id: string) => void;
  currentProjectId: string | null;
  projectManager: { projects: Project[] };
  onNewSession: () => void;
  onShowProfile: () => void;
  sidebar?: ReactNode;
  children: ReactNode;
}

function AppShell({
  activeTab,
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  sidebarCollapsed,
  setSidebarCollapsed,
  setMobileSidebarOpen,
  agents,
  currentAgent,
  agentsLoading,
  onSelectAgent,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  sidebar,
  children,
}: AppShellProps) {
  return (
    <>
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={onCloseProfileModal}
        versionInfo={versionInfo}
      />

      <div className="flex h-[100dvh] w-full overflow-hidden bg-white dark:bg-stone-900">
        {sidebar}

        <div className="relative z-0 flex flex-1 min-w-0 flex-col overflow-hidden">
          <Header
            activeTab={activeTab}
            sidebarCollapsed={sidebarCollapsed}
            setSidebarCollapsed={setSidebarCollapsed}
            setMobileSidebarOpen={setMobileSidebarOpen}
            agents={agents}
            currentAgent={currentAgent}
            agentsLoading={agentsLoading}
            onSelectAgent={onSelectAgent}
            currentProjectId={currentProjectId}
            projectManager={projectManager}
            onNewSession={onNewSession}
            onShowProfile={onShowProfile}
          />

          {children}
        </div>
      </div>
    </>
  );
}

function ChatAppContent({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  sidebarCollapsed,
  setSidebarCollapsed,
  mobileSidebarOpen,
  setMobileSidebarOpen,
  onShowProfile,
}: {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { enableSkills, settings } = useSettingsContext();
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
    totalCount: totalSkillsCount,
    pendingSkillNames,
    isMutating: skillsMutating,
    fetchSkills,
  } = useSkills({ enabled: enableSkills });

  const projectManager = useProjectManager();

  // 创建一个 ref 来存储 sessionConfig，供 useAgent 使用
  const sessionConfigRef = useRef({
    disabledSkills: [] as string[],
    disabledMcpTools: [] as string[],
    agentOptions: {} as Record<string, boolean | string | number>,
  });

  // 先初始化 useAgent 获取 agents 和 currentAgent
  const {
    messages,
    sessionId,
    currentRunId,
    isLoading,
    agents,
    currentAgent,
    agentsLoading,
    newlyCreatedSession,
    sendMessage,
    stopGeneration,
    clearMessages,
    selectAgent,
    loadHistory,
    setPendingProjectId,
    autoExpandProjectId,
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
    getDisabledMcpTools: () => sessionConfigRef.current.disabledMcpTools,
    onSkillAdded: (skillName: string, _description: string, filesCount: number) => {
      console.log(
        `[AppContent] Skill added: ${skillName} (${filesCount} files), refreshing skills list`,
      );
      setTimeout(() => fetchSkills(), 500);
    },
  });

  const prevAgentRef = useRef(currentAgent);
  useEffect(() => {
    if (prevAgentRef.current !== currentAgent) {
      prevAgentRef.current = currentAgent;
      refreshToolsForAgent(currentAgent);
    }
  }, [currentAgent, refreshToolsForAgent]);

  // 现在可以初始化 agentOptions
  const {
    agentOptionValues,
    currentAgentOptions,
    handleToggleAgentOption,
    restoreAgentOptions,
  } = useAgentOptions(agents, currentAgent);

  // 对话级别的配置管理（独立于全局配置）
  const {
    config: sessionConfig,
    toggleSkill: toggleSessionSkill,
    toggleMcpTool: toggleSessionMcpTool,
    setAgentOption: setSessionAgentOption,
    resetToDefaults,
    restoreConfig: restoreSessionConfig,
  } = useSessionConfig({
    getDefaultAgentOptions: () => agentOptionValues,
  });

  // 同步 sessionConfig 到 ref，供 useAgent 使用
  useEffect(() => {
    sessionConfigRef.current = sessionConfig;
  }, [sessionConfig]);

  // Compute effective tools: apply session-level MCP tool overrides (blacklist)
  const effectiveTools = useMemo(() => {
    const sessionDisabled = new Set(sessionConfig.disabledMcpTools);
    if (sessionDisabled.size === 0) return tools;
    return tools.map((t) => {
      if (t.category !== "mcp") return t;
      return { ...t, enabled: t.enabled && !sessionDisabled.has(t.name) };
    });
  }, [tools, sessionConfig.disabledMcpTools]);

  // Compute effective skills: apply session-level skill overrides (blacklist)
  const effectiveSkills = useMemo(() => {
    const sessionDisabled = new Set(sessionConfig.disabledSkills);
    if (sessionDisabled.size === 0) return skills;
    return skills.map((s) => ({
      ...s,
      enabled: s.enabled && !sessionDisabled.has(s.name),
    }));
  }, [skills, sessionConfig.disabledSkills]);

  // Effective toggle callbacks: only update session config (not global state)
  const effectiveToggleTool = useCallback(
    (toolName: string) => {
      const tool = tools.find((t) => t.name === toolName);
      if (!tool) return;

      if (tool.category === "mcp") {
        toggleSessionMcpTool(toolName);
      }
      // Other categories (builtin, human, sandbox) don't support session-level toggle
    },
    [tools, toggleSessionMcpTool],
  );

  const effectiveToggleCategory = useCallback(
    (category: ToolCategory, enabled: boolean) => {
      if (category === "mcp") {
        // For MCP tools, update session config
        tools
          .filter((t) => t.category === "mcp" && !t.system_disabled)
          .forEach((t) => {
            const isInSessionDisabled = sessionConfig.disabledMcpTools.includes(t.name);
            if (enabled && isInSessionDisabled) {
              // Want enabled, currently in disabled list → remove
              toggleSessionMcpTool(t.name);
            } else if (!enabled && !isInSessionDisabled) {
              // Want disabled, not in disabled list → add
              toggleSessionMcpTool(t.name);
            }
          });
      }
      // For other categories, we don't support session-level toggle yet
    },
    [tools, sessionConfig.disabledMcpTools, toggleSessionMcpTool],
  );

  const effectiveToggleAll = useCallback(
    (enabled: boolean) => {
      // Sync MCP tools in session config (disabled list)
      tools
        .filter((t) => t.category === "mcp" && !t.system_disabled)
        .forEach((t) => {
          const isInSessionDisabled = sessionConfig.disabledMcpTools.includes(t.name);
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
      // Only update session config, not global state
      toggleSessionSkill(name);
      return true;
    },
    [toggleSessionSkill],
  );

  const effectiveToggleSkillCategory = useCallback(
    async (category: SkillSource, enabled: boolean): Promise<boolean> => {
      // Only update session config for skills in this category
      skills
        .filter((s) => s.source === category)
        .forEach((s) => {
          const isInSessionDisabled = sessionConfig.disabledSkills.includes(s.name);
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
      // Only update session config for all skills
      skills.forEach((s) => {
        const isInSessionDisabled = sessionConfig.disabledSkills.includes(s.name);
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

  // Effective agent option toggle: update both local state and session config
  const effectiveToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      handleToggleAgentOption(key, value);
      setSessionAgentOption(key, value);
    },
    [handleToggleAgentOption, setSessionAgentOption],
  );

  // Compute effective counts
  const effectiveEnabledToolsCount = useMemo(
    () => effectiveTools.filter((t) => t.enabled).length,
    [effectiveTools],
  );
  const effectiveEnabledSkillsCount = useMemo(
    () => effectiveSkills.filter((s) => s.enabled).length,
    [effectiveSkills],
  );

  const canSendMessage = hasPermission(Permission.CHAT_WRITE);

  useWebSocketNotifications({ sessionId, enabled: isAuthenticated });

  const [sessionName, setSessionName] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const fetchSessionName = async () => {
      try {
        const { sessionApi } = await import("../../../services/api");
        const session = await sessionApi.get(sessionId);
        setSessionName(session?.name || null);
      } catch (err) {
        console.warn("[AppContent] Failed to fetch session:", err);
        setSessionName(null);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  useEffect(() => {
    if (newlyCreatedSession?.name && sessionId === newlyCreatedSession.id) {
      setSessionName(newlyCreatedSession.name);
    }
  }, [newlyCreatedSession?.name, newlyCreatedSession?.id, sessionId]);

  // 处理配置恢复
  const handleConfigRestored = useCallback(
    (config: {
      agent_id?: string;
      agent_options?: Record<string, boolean | string | number>;
      disabled_skills?: string[];
      disabled_mcp_tools?: string[];
      disabled_tools?: string[];
    }) => {
      console.log("[AppContent] Restoring session config:", config);

      // 使用 useSessionConfig 恢复对话级配置
      restoreSessionConfig(config);

      // 恢复 agent options 到 useAgentOptions
      if (config.agent_options) {
        restoreAgentOptions(config.agent_options);
      }
    },
    [restoreSessionConfig, restoreAgentOptions],
  );

  const { handleSelectSession, handleNewSession } = useSessionSync({
    activeTab: "chat",
    sessionId,
    loadHistory,
    clearMessages,
    onConfigRestored: handleConfigRestored,
  });

  // Wrapper that also resets session config on new session
  const handleNewSessionWithReset = useCallback(() => {
    handleNewSession();
    resetToDefaults();
  }, [handleNewSession, resetToDefaults]);

  const handleMobileClose = useCallback(() => setMobileSidebarOpen(false), [
    setMobileSidebarOpen,
  ]);
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

  return (
    <AppShell
      activeTab="chat"
      showProfileModal={showProfileModal}
      onCloseProfileModal={onCloseProfileModal}
      versionInfo={versionInfo}
      sidebarCollapsed={sidebarCollapsed}
      setSidebarCollapsed={setSidebarCollapsed}
      setMobileSidebarOpen={setMobileSidebarOpen}
      agents={agents}
      currentAgent={currentAgent}
      agentsLoading={agentsLoading}
      onSelectAgent={selectAgent}
      currentProjectId={currentProjectId}
      projectManager={projectManager}
      onNewSession={handleNewSessionWithReset}
      onShowProfile={onShowProfile}
      sidebar={
        <SessionSidebar
          currentSessionId={sessionId}
          onSelectSession={handleSelectSessionAndClose}
          onNewSession={handleNewSessionAndClose}
          onSetPendingProjectId={setPendingProjectId}
          autoExpandProjectId={autoExpandProjectId}
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
          totalSkillsCount={totalSkillsCount}
          enableSkills={enableSkills}
          agentOptions={currentAgentOptions}
          agentOptionValues={sessionConfig.agentOptions}
          onToggleAgentOption={effectiveToggleAgentOption}
          approvals={approvals}
          onRespondApproval={respondToApproval}
          approvalLoading={approvalLoading}
          onSendMessage={sendMessage}
          onStopGeneration={stopGeneration}
          attachments={pageDragAttachments}
          onAttachmentsChange={setPageDragAttachments}
          settings={settings || {}}
          i18n={i18n}
        />
      </>
    </AppShell>
  );
}

function NonChatAppContent({
  activeTab,
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  sidebarCollapsed,
  setSidebarCollapsed,
  setMobileSidebarOpen,
  onShowProfile,
}: {
  activeTab: Exclude<TabType, "chat">;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
}) {
  return (
    <AppShell
      activeTab={activeTab}
      showProfileModal={showProfileModal}
      onCloseProfileModal={onCloseProfileModal}
      versionInfo={versionInfo}
      sidebarCollapsed={sidebarCollapsed}
      setSidebarCollapsed={setSidebarCollapsed}
      setMobileSidebarOpen={setMobileSidebarOpen}
      agents={[]}
      currentAgent=""
      agentsLoading={false}
      onSelectAgent={() => {}}
      currentProjectId={null}
      projectManager={{ projects: [] }}
      onNewSession={() => {}}
      onShowProfile={onShowProfile}
    >
      <TabContent activeTab={activeTab} />
    </AppShell>
  );
}

export function AppContent({ activeTab }: AppContentProps) {
  const { versionInfo } = useVersion();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);

  const handleCloseProfileModal = useCallback(
    () => setShowProfileModal(false),
    [],
  );
  const handleShowProfile = useCallback(() => setShowProfileModal(true), []);

  if (activeTab === "chat") {
    return (
      <ChatAppContent
        showProfileModal={showProfileModal}
        onCloseProfileModal={handleCloseProfileModal}
        versionInfo={versionInfo}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        mobileSidebarOpen={mobileSidebarOpen}
        setMobileSidebarOpen={setMobileSidebarOpen}
        onShowProfile={handleShowProfile}
      />
    );
  }

  return (
    <NonChatAppContent
      activeTab={activeTab}
      showProfileModal={showProfileModal}
      onCloseProfileModal={handleCloseProfileModal}
      versionInfo={versionInfo}
      sidebarCollapsed={sidebarCollapsed}
      setSidebarCollapsed={setSidebarCollapsed}
      setMobileSidebarOpen={setMobileSidebarOpen}
      onShowProfile={handleShowProfile}
    />
  );
}
