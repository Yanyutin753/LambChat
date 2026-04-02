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
import { Permission, type AgentInfo, type Project } from "../../../types";
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
  const { hasPermission, isAuthenticated, user } = useAuth();

  const { isPageDragging, pageDragAttachments, setPageDragAttachments } =
    useDragAndDrop();

  const {
    approvals,
    respondToApproval,
    addApproval,
    clearApprovals,
    isLoading: approvalLoading,
  } = useApprovals({ sessionId: null });

  const disabledToolsVersion = useMemo(
    () =>
      JSON.stringify(
        ((user?.metadata?.disabled_tools as string[] | undefined) ?? [])
          .slice()
          .sort(),
      ),
    [user?.metadata?.disabled_tools],
  );

  const {
    tools,
    isLoading: toolsLoading,
    enabledCount: enabledToolsCount,
    totalCount: totalToolsCount,
    toggleTool,
    toggleCategory,
    toggleAll,
    getDisabledToolNames,
    refreshToolsForAgent,
  } = useTools(disabledToolsVersion);

  const {
    skills,
    isLoading: skillsLoading,
    enabledCount: enabledSkillsCount,
    totalCount: totalSkillsCount,
    pendingSkillNames,
    isMutating: skillsMutating,
    toggleSkillWrapper,
    toggleCategory: toggleSkillCategory,
    toggleAll: toggleAllSkills,
    fetchSkills,
  } = useSkills({ enabled: enableSkills });

  const projectManager = useProjectManager();

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
      refreshToolsForAgent(currentAgent, user?.metadata);
    }
  }, [currentAgent, refreshToolsForAgent, user?.metadata]);

  const { agentOptionValues, currentAgentOptions, handleToggleAgentOption } =
    useAgentOptions(agents, currentAgent);

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

  const { handleSelectSession, handleNewSession } = useSessionSync({
    activeTab: "chat",
    sessionId,
    loadHistory,
    clearMessages,
  });

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
    handleNewSession();
    setMobileSidebarOpen(false);
  }, [handleNewSession, setMobileSidebarOpen]);

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
      onNewSession={handleNewSession}
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
          tools={tools}
          onToggleTool={toggleTool}
          onToggleCategory={toggleCategory}
          onToggleAll={toggleAll}
          toolsLoading={toolsLoading}
          enabledToolsCount={enabledToolsCount}
          totalToolsCount={totalToolsCount}
          skills={skills}
          onToggleSkill={toggleSkillWrapper}
          onToggleSkillCategory={toggleSkillCategory}
          onToggleAllSkills={toggleAllSkills}
          skillsLoading={skillsLoading}
          pendingSkillNames={pendingSkillNames}
          skillsMutating={skillsMutating}
          enabledSkillsCount={enabledSkillsCount}
          totalSkillsCount={totalSkillsCount}
          enableSkills={enableSkills}
          agentOptions={currentAgentOptions}
          agentOptionValues={agentOptionValues}
          onToggleAgentOption={handleToggleAgentOption}
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
