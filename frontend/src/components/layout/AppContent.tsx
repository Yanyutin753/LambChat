import { useRef, useEffect, useState, useCallback } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Menu, Check, X } from "lucide-react";
import { ChatMessage } from "../chat/ChatMessage";
import { ChatInput } from "../chat/ChatInput";
import { ApprovalPanel } from "../panels/ApprovalPanel";
import { SkillsPanel } from "../panels/SkillsPanel";
import { SessionSidebar } from "../panels/SessionSidebar";
import { UsersPanel } from "../panels/UsersPanel";
import { RolesPanel } from "../panels/RolesPanel";
import { SettingsPanel } from "../panels/SettingsPanel";
import { MCPPanel } from "../panels/MCPPanel";
import { FeedbackPanel } from "../panels/FeedbackPanel";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { Loading } from "../common";
import { AgentSelector } from "../agent/AgentSelector";
import { ProfileModal } from "../profile/ProfileModal";
import { UserMenu } from "./UserMenu";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { useAgent } from "../../hooks/useAgent";
import { useApprovals } from "../../hooks/useApprovals";
import { useAuth } from "../../hooks/useAuth";
import { useTools } from "../../hooks/useTools";
import { useSkills } from "../../hooks/useSkills";
import { useVersion } from "../../hooks/useVersion";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useBrowserNotification } from "../../hooks/useBrowserNotification";
import { Permission } from "../../types";
import { sessionApi } from "../../services/api";

export type TabType =
  | "chat"
  | "skills"
  | "users"
  | "roles"
  | "settings"
  | "mcp"
  | "feedback";

interface AppContentProps {
  activeTab: TabType;
}

export function AppContent({ activeTab }: AppContentProps) {
  const { t } = useTranslation();
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  const location = useLocation();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const navigate = useNavigate();
  const { enableMcp, enableSkills } = useSettingsContext();
  const { versionInfo } = useVersion();

  // Get approvals hook's addApproval method
  const {
    approvals,
    respondToApproval,
    addApproval,
    clearApprovals,
    isLoading: approvalLoading,
  } = useApprovals({ sessionId: null }); // Initialize with null first

  // Tool selector hook
  const {
    tools,
    isLoading: toolsLoading,
    enabledCount: enabledToolsCount,
    totalCount: totalToolsCount,
    toggleTool,
    toggleCategory,
    toggleAll,
    getDisabledToolNames,
  } = useTools({ enabled: enableMcp });

  // Skills selector hook
  const {
    skills,
    isLoading: skillsLoading,
    enabledCount: enabledSkillsCount,
    totalCount: totalSkillsCount,
    toggleSkillWrapper,
    toggleCategory: toggleSkillCategory,
    toggleAll: toggleAllSkills,
    fetchSkills,
  } = useSkills({ enabled: enableSkills });

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
  } = useAgent({
    onApprovalRequired: (approval) => {
      // When SSE receives approval_required event, add directly to approvals list
      // No need to poll /human/pending endpoint
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
      // When conversation fails, clear all pending approvals
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
      fetchSkills();
    },
  });

  // Browser notification
  const { requestPermission, notify, isSupported, permission } =
    useBrowserNotification();

  // Request notification permission on first interaction
  useEffect(() => {
    console.log("[AppContent] Notification state:", {
      isSupported,
      permission,
    });
    if (isSupported && permission === "default") {
      requestPermission();
    }
  }, [isSupported, permission, requestPermission]);

  // WebSocket for task completion notifications
  useWebSocket({
    enabled: !!sessionId,
    onTaskComplete: (notification: {
      data: { session_id: string; status: string; message?: string };
    }) => {
      const { session_id, status, message } = notification.data;
      console.log("[AppContent] Task complete notification:", notification, {
        isSupported,
        permission,
      });

      // Show browser notification
      if (isSupported && permission === "granted") {
        console.log("[AppContent] Showing browser notification:", status);
        const navigateToSession = () => {
          if (session_id !== sessionId) {
            navigate(`/chat/${session_id}`);
          }
        };
        if (status === "completed") {
          notify(t("notification.taskCompleted"), {
            body: message,
            onClick: navigateToSession,
            url: `/chat/${session_id}`,
          });
        } else {
          notify(t("notification.taskFailed"), {
            body: message,
            onClick: navigateToSession,
            url: `/chat/${session_id}`,
          });
        }
      } else {
        console.log(
          "[AppContent] Browser notification not shown, permission:",
          permission,
        );
      }

      // Navigate function for notifications
      const navigateToSession = () => {
        if (session_id !== sessionId) {
          // Use replace + state to prevent sync effect from reverting the navigation
          navigate(`/chat/${session_id}`, {
            replace: true,
            state: { externalNavigate: true },
          });
        }
      };

      // Show toast notification (clickable)
      const toastMessage =
        status === "completed"
          ? message || t("notification.taskCompleted")
          : message || t("notification.taskFailed");
      const isSuccess = status === "completed";

      toast.custom(
        (visible) => (
          <div
            className={`cursor-pointer px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 transition-all ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
            } ${
              isSuccess
                ? "bg-green-50 dark:bg-green-900/80 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-700"
                : "bg-red-50 dark:bg-red-900/80 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-700"
            }`}
            onClick={() => {
              navigateToSession();
              toast.remove();
            }}
          >
            {isSuccess ? (
              <Check
                size={18}
                className="text-green-600 dark:text-green-400 flex-shrink-0"
              />
            ) : (
              <X
                size={18}
                className="text-red-600 dark:text-red-400 flex-shrink-0"
              />
            )}
            <span className="text-sm font-medium">{toastMessage}</span>
          </div>
        ),
        { duration: 4000 },
      );
    },
  });

  // Session name state - needs to be after useAgent since it depends on sessionId
  const [sessionName, setSessionName] = useState<string | null>(null);

  // Fetch session name when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const fetchSessionName = async () => {
      try {
        const session = await sessionApi.get(sessionId);
        if (session?.name) {
          setSessionName(session.name);
        } else {
          setSessionName(null);
        }
      } catch (err) {
        console.warn("[AppContent] Failed to fetch session:", err);
        setSessionName(null);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  // Sync sessionName with newlyCreatedSession.name (e.g., after title generation)
  useEffect(() => {
    if (newlyCreatedSession?.name && sessionId === newlyCreatedSession.id) {
      setSessionName(newlyCreatedSession.name);
    }
  }, [newlyCreatedSession?.name, newlyCreatedSession?.id, sessionId]);

  // Agent options state
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});

  // Get current agent's options
  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions = currentAgentInfo?.options || {};

  // Reset agent options when agent changes
  useEffect(() => {
    const options = agents.find((a) => a.id === currentAgent)?.options;
    if (options) {
      const defaultValues: Record<string, boolean | string | number> = {};
      Object.entries(options).forEach(([key, option]) => {
        defaultValues[key] = option.default;
      });
      setAgentOptionValues(defaultValues);
    } else {
      setAgentOptionValues({});
    }
  }, [currentAgent, agents]);

  // Handler for toggling agent options
  const handleToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      setAgentOptionValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const { settings } = useSettingsContext();
  const { hasPermission } = useAuth();
  const canSendMessage = hasPermission(Permission.CHAT_WRITE);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Flag to prevent sync loops between URL and state
  const isSyncingRef = useRef(false);
  const [isNearBottom, setIsNearBottom] = useState(true);

  // Check if user is near the bottom (within 100px)
  const checkIfNearBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;
    const threshold = 100;
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      threshold;
    setIsNearBottom(isAtBottom);
    return isAtBottom;
  }, []);

  // Track previous message count to detect new messages
  const prevMessagesCountRef = useRef(messages.length);

  // Auto-scroll to bottom when new messages are added or when loading
  useEffect(() => {
    const prevCount = prevMessagesCountRef.current;
    const newCount = messages.length;

    // Scroll to bottom when:
    // 1. New message is added (count increased)
    // 2. User is already near bottom
    if (newCount > prevCount || isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
    }

    prevMessagesCountRef.current = newCount;
  }, [messages, isNearBottom]);

  // Track scroll position
  const handleScroll = useCallback(() => {
    checkIfNearBottom();
  }, [checkIfNearBottom]);

  // Sync from URL only on initial mount
  useEffect(() => {
    if (urlSessionId && !isSyncingRef.current) {
      isSyncingRef.current = true;
      loadHistory(urlSessionId).finally(() => {
        // Delay reset to allow state to settle
        setTimeout(() => {
          isSyncingRef.current = false;
        }, 100);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Sync URL with sessionId state (when sessionId changes from internal actions)
  useEffect(() => {
    if (isSyncingRef.current) return;

    // Skip sync if this navigation was initiated externally (e.g., from toast click)
    // This prevents the sync effect from reverting the user's navigation
    if ((location.state as { externalNavigate?: boolean })?.externalNavigate) {
      // Clear the externalNavigate flag after handling
      navigate(location.pathname, { replace: true, state: {} });
      return;
    }

    if (sessionId && sessionId !== urlSessionId) {
      // New session created - update URL
      isSyncingRef.current = true;
      navigate(`/chat/${sessionId}`, { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    } else if (!sessionId && urlSessionId) {
      // Session cleared - clear URL
      isSyncingRef.current = true;
      navigate("/chat", { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    }
  }, [sessionId, urlSessionId, navigate, location]);

  // Handle session selection from sidebar
  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      // loadHistory has its own isLoadingHistoryRef guard, no need to check here
      try {
        await loadHistory(selectedSessionId);
        // Update URL
        navigate(`/chat/${selectedSessionId}`);
        // Scroll to top after loading history
        messagesContainerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        console.error("[handleSelectSession] Error:", err);
      }
    },
    [navigate, loadHistory],
  );

  // Handle new session
  const handleNewSession = useCallback(() => {
    clearMessages();
    // URL sync is handled by the useEffect above
  }, [clearMessages]);

  return (
    <>
      {/* Profile Modal - rendered at top level via portal */}
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={() => setShowProfileModal(false)}
        versionInfo={versionInfo}
      />

      <div className="flex h-[100dvh] w-full overflow-hidden bg-white dark:bg-stone-900">
        {/* Session Sidebar - only show on chat tab */}
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
          {/* Header */}
          <header className="relative z-50 flex items-center px-3 py-4 sm:px-4 mb-2">
            {/* Left: Expand Sidebar + Menu + Agent Selector / Page Title */}
            <div className="flex items-center gap-2 flex-shrink-0">
              {activeTab === "chat" ? (
                <>
                  {/* Expand sidebar button - when collapsed */}
                  {sidebarCollapsed && (
                    <button
                      onClick={() => setSidebarCollapsed(false)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-stone-800 transition-colors"
                      title={t("sidebar.expandSidebar")}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        className="w-5 h-5 text-gray-600 dark:text-stone-400"
                      >
                        <path
                          fillRule="evenodd"
                          clipRule="evenodd"
                          d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.07354 19.4265 5.6146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.5523 5 12Z"
                          fill="currentColor"
                        />
                      </svg>
                    </button>
                  )}
                  {/* Mobile menu button - only when sidebar is not collapsed */}
                  {!sidebarCollapsed && (
                    <button
                      onClick={() => setMobileSidebarOpen(true)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-stone-800 sm:hidden transition-colors"
                    >
                      <Menu
                        size={20}
                        className="text-gray-600 dark:text-stone-400"
                      />
                    </button>
                  )}
                  {/* Agent Selector - Performance Optimized */}
                  <AgentSelector
                    agents={agents}
                    currentAgent={currentAgent}
                    agentsLoading={agentsLoading}
                    onSelectAgent={selectAgent}
                  />
                </>
              ) : (
                /* Page Title for non-chat pages */
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => navigate("/chat")}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
                    title={t("errors.backToHome")}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="size-5"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
                      />
                    </svg>
                  </button>
                  <div className="flex h-8 items-center gap-2">
                    <span className="text-base font-bold text-gray-700 dark:text-stone-200 font-serif">
                      LambChat
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Right: New Chat (when sidebar collapsed) + Theme Toggle + User Menu */}
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {activeTab === "chat" && sidebarCollapsed && (
                <button
                  onClick={handleNewSession}
                  className="flex cursor-pointer px-2 py-2 rounded-xl text-gray-600 dark:text-gray-400 dark:text-stone-300 dark:hover:bg-stone-800 transition"
                  title={t("sidebar.newChat")}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    strokeWidth="0.1"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    className="w-5 h-5"
                  >
                    <path
                      d="M15.6729 3.91287C16.8918 2.69392 18.8682 2.69392 20.0871 3.91287C21.3061 5.13182 21.3061 7.10813 20.0871 8.32708L14.1499 14.2643C13.3849 15.0293 12.3925 15.5255 11.3215 15.6785L9.14142 15.9899C8.82983 16.0344 8.51546 15.9297 8.29289 15.7071C8.07033 15.4845 7.96554 15.1701 8.01005 14.8586L8.32149 12.6785C8.47449 11.6075 8.97072 10.615 9.7357 9.85006L15.6729 3.91287ZM18.6729 5.32708C18.235 4.88918 17.525 4.88918 17.0871 5.32708L11.1499 11.2643C10.6909 11.7233 10.3932 12.3187 10.3014 12.9613L10.1785 13.8215L11.0386 13.6986C11.6812 13.6068 12.2767 13.3091 12.7357 12.8501L18.6729 6.91287C19.1108 6.47497 19.1108 5.76499 18.6729 5.32708ZM11 3.99929C11.0004 4.55157 10.5531 4.99963 10.0008 5.00007C9.00227 5.00084 8.29769 5.00827 7.74651 5.06064C7.20685 5.11191 6.88488 5.20117 6.63803 5.32695C6.07354 5.61457 5.6146 6.07351 5.32698 6.63799C5.19279 6.90135 5.10062 7.24904 5.05118 7.8542C5.00078 8.47105 5 9.26336 5 10.4V13.6C5 14.7366 5.00078 15.5289 5.05118 16.1457C5.10062 16.7509 5.19279 17.0986 5.32698 17.3619C5.6146 17.9264 6.07354 18.3854 6.63803 18.673C6.90138 18.8072 7.24907 18.8993 7.85424 18.9488C8.47108 18.9992 9.26339 19 10.4 19H13.6C14.7366 19 15.5289 18.9992 16.1458 18.9488C16.7509 18.8993 17.0986 18.8072 17.362 18.673C17.9265 18.3854 18.3854 17.9264 18.673 17.3619C18.7988 17.1151 18.8881 16.7931 18.9393 16.2535C18.9917 15.7023 18.9991 14.9977 18.9999 13.9992C19.0003 13.4469 19.4484 12.9995 20.0007 13C20.553 13.0004 21.0003 13.4485 20.9999 14.0007C20.9991 14.9789 20.9932 15.7808 20.9304 16.4426C20.8664 17.116 20.7385 17.7136 20.455 18.2699C19.9757 19.2107 19.2108 19.9756 18.27 20.455C17.6777 20.7568 17.0375 20.8826 16.3086 20.9421C15.6008 21 14.7266 21 13.6428 21H10.3572C9.27339 21 8.39925 21 7.69138 20.9421C6.96253 20.8826 6.32234 20.7568 5.73005 20.455C4.78924 19.9756 4.02433 19.2107 3.54497 18.2699C3.24318 17.6776 3.11737 17.0374 3.05782 16.3086C2.99998 15.6007 2.99999 14.7266 3 13.6428V10.3572C2.99999 9.27337 2.99998 8.39922 3.05782 7.69134C3.11737 6.96249 3.24318 6.3223 3.54497 5.73001C4.02433 4.7892 4.78924 4.0243 5.73005 3.54493C6.28633 3.26149 6.88399 3.13358 7.55735 3.06961C8.21919 3.00673 9.02103 3.00083 9.99922 3.00007C10.5515 2.99964 10.9996 3.447 11 3.99929Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
              )}
              <LanguageToggle />
              <ThemeToggle />
              <UserMenu onShowProfile={() => setShowProfileModal(true)} />
            </div>
          </header>

          {/* Main Content */}
          {activeTab === "chat" ? (
            <>
              {/* Messages */}
              <main
                ref={messagesContainerRef}
                onScroll={handleScroll}
                className="relative flex-1 overflow-y-auto overflow-x-hidden min-h-0 overscroll-contain pb-5"
                style={{ WebkitOverflowScrolling: "touch" }}
              >
                {/* Session loading indicator - show when loading history (no messages yet) */}
                {isLoading && messages.length === 0 && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm">
                    <Loading size="lg" />
                  </div>
                )}
                {messages.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center px-4 py-8">
                    {/* Title */}
                    <div className="flex items-center gap-3 mb-7 sm:mb-9">
                      <h1 className="text-3xl sm:text-4xl font-semibold text-gray-700 dark:text-stone-200 font-serif">
                        LambChat
                      </h1>
                    </div>

                    {/* Suggestion Cards */}
                    <div className="w-full max-w-lg space-y-3 px-4">
                      {(
                        settings?.settings.frontend.find(
                          (s) => s.key === "WELCOME_SUGGESTIONS",
                        )?.value as
                          | Array<{ icon: string; text: string }>
                          | undefined
                      )?.map((suggestion) => (
                        <button
                          key={suggestion.text}
                          onClick={() => sendMessage(suggestion.text)}
                          className="w-full flex items-center gap-3 rounded-xl border border-gray-200 dark:border-stone-700 px-4 py-3 text-left text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-800 transition-colors"
                        >
                          <span className="text-lg">{suggestion.icon}</span>
                          <span>{suggestion.text}</span>
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 sm:mt-6 flex items-center gap-2 text-xs text-gray-400 dark:text-stone-500">
                      <a
                        href="https://github.com/Yanyutin753/LambChat"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium hover:text-gray-600 dark:hover:text-stone-400 transition-colors font-serif"
                      >
                        LambChat
                      </a>
                      {versionInfo?.app_version && (
                        <>
                          <span>·</span>
                          <span>v{versionInfo.app_version}</span>
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="dark:divide-stone-800">
                    {messages.map((message) => (
                      <ChatMessage
                        key={message.id}
                        message={message}
                        sessionId={sessionId ?? undefined}
                        sessionName={sessionName ?? undefined}
                        runId={currentRunId ?? undefined}
                      />
                    ))}
                    {/* Session feedback - using per-message ratings instead */}

                    <div ref={messagesEndRef} />
                  </div>
                )}
              </main>

              {/* Scroll to bottom button - Show when user is not at bottom and messages exist */}
              {messages.length > 0 && !isNearBottom && (
                <button
                  onClick={() => {
                    messagesEndRef.current?.scrollIntoView({
                      behavior: "smooth",
                    });
                    setTimeout(() => checkIfNearBottom(), 100);
                  }}
                  className="absolute left-1/2 -translate-x-1/2 z-50 flex items-center p-1.5 rounded-full bg-white/70 border border-gray-200 dark:border-none dark:bg-white/10 shadow-md hover:shadow-lg transition-all hover:scale-105"
                  style={{
                    bottom: "9rem",
                    left: "50%",
                    transform: "translateX(-50%)",
                  }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-5 h-5 text-stone-600 dark:text-stone-200"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}

              {/* Approval Panel - positioned above input */}
              <ApprovalPanel
                approvals={approvals}
                onRespond={respondToApproval}
                isLoading={approvalLoading}
              />

              {/* Input */}
              <ChatInput
                onSend={sendMessage}
                onStop={stopGeneration}
                isLoading={isLoading}
                canSend={canSendMessage}
                tools={tools}
                onToggleTool={toggleTool}
                onToggleCategory={toggleCategory}
                onToggleAll={toggleAll}
                toolsLoading={toolsLoading}
                enabledToolsCount={enabledToolsCount}
                totalToolsCount={totalToolsCount}
                enableMcp={enableMcp}
                skills={skills}
                onToggleSkill={toggleSkillWrapper}
                onToggleSkillCategory={toggleSkillCategory}
                onToggleAllSkills={toggleAllSkills}
                skillsLoading={skillsLoading}
                enabledSkillsCount={enabledSkillsCount}
                totalSkillsCount={totalSkillsCount}
                enableSkills={enableSkills}
                agentOptions={currentAgentOptions}
                agentOptionValues={agentOptionValues}
                onToggleAgentOption={handleToggleAgentOption}
              />
            </>
          ) : activeTab === "skills" ? (
            <main className="flex-1 overflow-hidden">
              <SkillsPanel />
            </main>
          ) : activeTab === "users" ? (
            <main className="flex-1 overflow-hidden">
              <UsersPanel />
            </main>
          ) : activeTab === "roles" ? (
            <main className="flex-1 overflow-hidden">
              <RolesPanel />
            </main>
          ) : activeTab === "settings" ? (
            <main className="flex-1 overflow-hidden">
              <SettingsPanel />
            </main>
          ) : activeTab === "mcp" ? (
            <main className="flex-1 overflow-hidden">
              <MCPPanel />
            </main>
          ) : activeTab === "feedback" ? (
            <main className="flex-1 overflow-hidden">
              <FeedbackPanel />
            </main>
          ) : null}
        </div>
      </div>
    </>
  );
}
