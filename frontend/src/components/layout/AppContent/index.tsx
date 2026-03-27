import { useState, useEffect } from "react";
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
import { Permission } from "../../../types";
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

export function AppContent({ activeTab }: AppContentProps) {
  const { t, i18n } = useTranslation();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);

  const { enableSkills, settings } = useSettingsContext();
  const { versionInfo } = useVersion();

  // Page-level drag & drop
  const {
    isPageDragging,
    pageDragAttachments,
    setPageDragAttachments,
  } = useDragAndDrop();

  // Approvals
  const {
    approvals,
    respondToApproval,
    addApproval,
    clearApprovals,
    isLoading: approvalLoading,
  } = useApprovals({ sessionId: null });

  // Auth & permissions (needed before useTools for disabledToolsVersion)
  const { hasPermission, isAuthenticated, user } = useAuth();

  // Derive a version key from disabled_tools so useTools re-fetches when they change
  // (e.g. when user toggles a tool in MCPServerCard)
  const disabledToolsVersion = JSON.stringify(
    user?.metadata?.disabled_tools ?? [],
  );

  // Tools
  const {
    tools,
    isLoading: toolsLoading,
    enabledCount: enabledToolsCount,
    totalCount: totalToolsCount,
    toggleTool,
    toggleCategory,
    toggleAll,
    getDisabledToolNames,
  } = useTools(disabledToolsVersion);

  // Skills
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

  // Agent
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

  // Agent options
  const { agentOptionValues, currentAgentOptions, handleToggleAgentOption } =
    useAgentOptions(agents, currentAgent);

  const canSendMessage = hasPermission(Permission.CHAT_WRITE);

  // WebSocket notifications
  useWebSocketNotifications({ sessionId, enabled: isAuthenticated });

  // Session name
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

  // Session sync
  const { handleSelectSession, handleNewSession } = useSessionSync({
    sessionId,
    loadHistory,
    clearMessages,
  });

  return (
    <>
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={() => setShowProfileModal(false)}
        versionInfo={versionInfo}
      />

      <div className="flex h-[100dvh] w-full overflow-hidden bg-white dark:bg-stone-900">
        {/* Drag overlay */}
        {isPageDragging && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-stone-500/5 dark:bg-stone-500/10  transition-colors">
            <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-stone-400 dark:border-stone-500 bg-white/95 dark:bg-stone-800/95 px-16 py-12 shadow-xl transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-stone-500 dark:text-stone-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
              <span className="text-lg font-medium text-stone-600 dark:text-stone-300">
                {t("chat.dropFilesHere", "Drop files here to upload")}
              </span>
            </div>
          </div>
        )}

        {/* Session Sidebar */}
        {activeTab === "chat" && (
          <SessionSidebar
            currentSessionId={sessionId}
            onSelectSession={(id) => {
              handleSelectSession(id);
              setMobileSidebarOpen(false);
            }}
            onNewSession={() => {
              handleNewSession();
              setMobileSidebarOpen(false);
            }}
            onSetPendingProjectId={setPendingProjectId}
            autoExpandProjectId={autoExpandProjectId}
            newSession={newlyCreatedSession}
            mobileOpen={mobileSidebarOpen}
            onMobileClose={() => setMobileSidebarOpen(false)}
            isCollapsed={sidebarCollapsed}
            onToggleCollapsed={setSidebarCollapsed}
            onShowProfile={() => setShowProfileModal(true)}
          />
        )}

        {/* Main Content */}
        <div className="relative z-0 flex flex-1 flex-col min-w-0 overflow-hidden">
          <Header
            activeTab={activeTab}
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
            onShowProfile={() => setShowProfileModal(true)}
          />

          {activeTab === "chat" ? (
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
          ) : (
            <TabContent activeTab={activeTab} />
          )}
        </div>
      </div>
    </>
  );
}
