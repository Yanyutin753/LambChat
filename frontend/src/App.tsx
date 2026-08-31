import { lazy, Suspense, useEffect, useState } from "react";
import {
  Routes,
  Route,
  useParams,
  useNavigate,
  Navigate,
} from "react-router-dom";
import { Toaster, ToastBar, toast } from "react-hot-toast";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ChatPageSkeleton, FilesPageSkeleton } from "./components/skeletons";
import { ThemeProvider } from "./contexts/ThemeContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { SelectionActionPopover } from "./components/common/SelectionActionPopover.tsx";
import { useSEO } from "./hooks/usePageTitle";
import { GITHUB_URL } from "./constants";
import { Permission } from "./types";
import {
  getCachedSessionTitle,
  listenSessionTitleUpdated,
} from "./utils/sessionTitleEvents";
import { APP_TOASTER_CLASS_NAME } from "./components/layout/AppContent/appToastLayout";
import { PwaStatusToasts } from "./components/pwa/PwaStatusToasts";
import { appNotificationService } from "./services/notifications/appNotificationService";
import { UpdateDialog } from "./components/update/UpdateDialog";
import { useAutoUpdate } from "./hooks/useAutoUpdate";

const SharedEntry = lazy(() =>
  import("./components/share/SharedEntry").then((m) => ({
    default: m.SharedEntry,
  })),
);
const OAuthCallback = lazy(() =>
  import("./components/auth/OAuthCallback").then((m) => ({
    default: m.OAuthCallback,
  })),
);
const ForgotPassword = lazy(() =>
  import("./components/auth/ForgotPassword").then((m) => ({
    default: m.ForgotPassword,
  })),
);
const ResetPassword = lazy(() =>
  import("./components/auth/ResetPassword").then((m) => ({
    default: m.ResetPassword,
  })),
);
const VerifyEmail = lazy(() =>
  import("./components/auth/VerifyEmail").then((m) => ({
    default: m.VerifyEmail,
  })),
);
const RegistrationPending = lazy(() =>
  import("./components/auth/RegistrationPending").then((m) => ({
    default: m.RegistrationPending,
  })),
);
const LandingPage = lazy(() =>
  import("./components/landing/LandingPage").then((m) => ({
    default: m.LandingPage,
  })),
);
const AuthPage = lazy(() =>
  import("./components/auth/AuthPage").then((m) => ({ default: m.AuthPage })),
);
const AppContent = lazy(() =>
  import("./components/layout/AppContent/index").then((m) => ({
    default: m.AppContent,
  })),
);

// Dev-only cover gallery — excluded from production builds via the DEV guard.
const CoverGalleryDemo = import.meta.env.DEV
  ? lazy(() =>
      import("./components/fileLibrary/__demo__/CoverGallery").then((m) => ({
        default: m.CoverGalleryDemo,
      })),
    )
  : null;
const NotFoundPage = lazy(() =>
  import("./components/common/NotFoundPage").then((m) => ({
    default: m.NotFoundPage,
  })),
);

function ChatPageSEO() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [sessionName, setSessionName] = useState<string | null>(() =>
    sessionId ? getCachedSessionTitle(sessionId) : null,
  );

  // React immediately when generateTitle finishes in the active chat session.
  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const cachedTitle = getCachedSessionTitle(sessionId);
    setSessionName(cachedTitle);

    return listenSessionTitleUpdated((detail) => {
      if (detail.sessionId === sessionId) {
        setSessionName(detail.title);
      }
    });
  }, [sessionId]);

  // Use session name if available, otherwise use default "nav.chat"
  useSEO({
    title: sessionName || "seo.chat.title",
    description: "seo.chat.description",
    path: sessionId ? `/chat/${sessionId}` : "/chat",
  });

  return null;
}

// Chat Page Component
function ChatPage() {
  return (
    <>
      <ChatPageSEO />
      <AppContent key="chat" activeTab="chat" />
    </>
  );
}

// Simple page components that set the page title and render AppContent
function SkillsPage() {
  useSEO({
    title: "seo.skills.title",
    description: "seo.skills.description",
    path: "/skills",
  });
  return <AppContent key="skills" activeTab="skills" />;
}

function MarketplacePage() {
  useSEO({
    title: "seo.marketplace.title",
    description: "seo.marketplace.description",
    path: "/marketplace",
  });
  return <AppContent key="marketplace" activeTab="marketplace" />;
}

function UsersPage() {
  useSEO({
    title: "seo.users.title",
    description: "seo.users.description",
    path: "/users",
  });
  return <AppContent key="users" activeTab="users" />;
}

function RolesPage() {
  useSEO({
    title: "seo.roles.title",
    description: "seo.roles.description",
    path: "/roles",
  });
  return <AppContent key="roles" activeTab="roles" />;
}

function SettingsPage() {
  useSEO({
    title: "seo.settings.title",
    description: "seo.settings.description",
    path: "/settings",
  });
  return <AppContent key="settings" activeTab="settings" />;
}

function MCPPage() {
  useSEO({
    title: "seo.mcp.title",
    description: "seo.mcp.description",
    path: "/mcp",
  });
  return <AppContent key="mcp" activeTab="mcp" />;
}

function FeedbackPage() {
  useSEO({
    title: "seo.feedback.title",
    description: "seo.feedback.description",
    path: "/feedback",
  });
  return <AppContent key="feedback" activeTab="feedback" />;
}

function ChannelsPage() {
  useSEO({
    title: "seo.channels.title",
    description: "seo.channels.description",
    path: "/channels",
  });
  return <AppContent key="channels" activeTab="channels" />;
}

function AgentsPage() {
  useSEO({
    title: "seo.agents.title",
    description: "seo.agents.description",
    path: "/agents",
  });
  return <AppContent key="agents" activeTab="agents" />;
}

function FilesPage() {
  useSEO({
    title: "seo.files.title",
    description: "seo.files.description",
    path: "/files",
  });
  return <AppContent key="files" activeTab="files" />;
}

function BookmarksPage() {
  useSEO({
    title: "seo.bookmarks.title",
    description: "seo.bookmarks.description",
    path: "/bookmarks",
  });
  return <AppContent key="bookmarks" activeTab="bookmarks" />;
}

function TeamPage() {
  useSEO({
    title: "seo.team.title",
    description: "seo.team.description",
    path: "/team",
  });
  return <AppContent key="team" activeTab="team" />;
}

function PersonaPage() {
  useSEO({
    title: "seo.persona.title",
    description: "seo.persona.description",
    path: "/persona",
  });
  return <AppContent key="persona" activeTab="persona" />;
}

function NotificationsPage() {
  useSEO({
    title: "seo.notifications.title",
    description: "seo.notifications.description",
    path: "/notifications",
  });
  return <AppContent key="notifications" activeTab="notifications" />;
}

function MemoryPage() {
  useSEO({
    title: "seo.memory.title",
    description: "seo.memory.description",
    path: "/memory",
  });
  return <AppContent key="memory" activeTab="memory" />;
}

function ScheduledTasksPage() {
  const { taskId } = useParams<{ taskId?: string }>();
  useSEO({
    title: "seo.scheduledTasks.title",
    description: "seo.scheduledTasks.description",
    path: taskId ? `/scheduled-tasks/${taskId}` : "/scheduled-tasks",
  });
  return <AppContent key="scheduled-tasks" activeTab="scheduled-tasks" />;
}

function UsagePage() {
  useSEO({
    title: "seo.usage.title",
    description: "seo.usage.description",
    path: "/usage",
  });
  return <AppContent key="usage" activeTab="usage" />;
}

function GitHubPage() {
  useSEO({
    title: "LambChat GitHub",
    description: "seo.landing.description",
    path: "/github",
    omitSuffix: true,
  });

  useEffect(() => {
    window.location.replace(GITHUB_URL);
  }, []);

  return null;
}

// Auth page wrapper - redirects to /chat after successful login/register
function AuthPageWrapper({
  initialMode,
}: {
  initialMode?: "login" | "register";
}) {
  const navigate = useNavigate();
  useSEO({
    title: initialMode === "register" ? "auth.register" : "auth.login",
    path: initialMode === "register" ? "/auth/register" : "/auth/login",
    noindex: true,
  });
  return (
    <AuthPage
      initialMode={initialMode}
      onSuccess={(redirectPath) =>
        navigate(redirectPath ?? "/chat", { replace: true })
      }
    />
  );
}

// Main App Component
function App() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Auto-update for desktop and mobile
  const {
    state: updateState,
    showDialog: showUpdateDialog,
    setShowDialog: setShowUpdateDialog,
    startUpdate,
    skipUpdate,
  } = useAutoUpdate();
  const updatePlatform = (() => {
    if (typeof window === "undefined") return "web";
    const win = window as unknown as Record<string, unknown>;
    if (win.__TAURI__ || win.__TAURI_INTERNALS__) return "tauri";
    if (typeof win.Capacitor !== "undefined") {
      const cap = win.Capacitor as Record<string, unknown>;
      const p = typeof cap.getPlatform === "function" ? cap.getPlatform() : "";
      if (p === "ios") return "ios";
      if (p === "android") return "android";
    }
    return "web";
  })();

  useEffect(() => {
    appNotificationService.setNavigator((route) => {
      navigate(route, { replace: false });
    });
    appNotificationService.initializeNativeClickHandlers();
    return () => appNotificationService.setNavigator(null);
  }, [navigate]);

  return (
    <ThemeProvider>
      <ErrorBoundary>
        <Toaster
          position="top-center"
          containerClassName={APP_TOASTER_CLASS_NAME}
          containerStyle={{
            top: "calc(56px + var(--app-safe-area-top, 0px))",
          }}
          toastOptions={{
            duration: 4000,
            style: {
              background: "#333",
              color: "#fff",
              borderRadius: "8px",
              padding: "12px 16px",
              minWidth: "280px",
            },
            success: {
              duration: 3000,
              iconTheme: {
                primary: "#22c55e",
                secondary: "#fff",
              },
            },
            error: {
              duration: 5000,
              iconTheme: {
                primary: "#ef4444",
                secondary: "#fff",
              },
            },
          }}
        >
          {(currentToast) => {
            if (currentToast.type === "custom") {
              return <ToastBar toast={currentToast} />;
            }

            return (
              <ToastBar toast={currentToast}>
                {({ icon, message }) => (
                  <div className="flex w-full items-center gap-3 text-left">
                    <span className="flex shrink-0 items-center">{icon}</span>
                    <div className="min-w-0 flex-1 leading-snug">{message}</div>
                    <button
                      type="button"
                      className="-mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-full text-white/60 transition-colors hover:bg-white/10 hover:text-white focus:outline-none focus:ring-2 focus:ring-white/30"
                      aria-label={t("common.dismiss", "关闭")}
                      onClick={(event) => {
                        event.stopPropagation();
                        toast.dismiss(currentToast.id);
                      }}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                )}
              </ToastBar>
            );
          }}
        </Toaster>
        <PwaStatusToasts />
        {showUpdateDialog && updateState.available && (
          <UpdateDialog
            state={updateState}
            isOpen={showUpdateDialog}
            onUpgrade={startUpdate}
            onSkip={skipUpdate}
            onDismiss={() => setShowUpdateDialog(false)}
            platform={updatePlatform as "tauri" | "android" | "ios"}
          />
        )}
        <SelectionActionPopover />
        <Suspense fallback={<ChatPageSkeleton />}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/interface" element={<LandingPage />} />
            <Route path="/features" element={<LandingPage />} />
            <Route path="/architecture" element={<LandingPage />} />
            <Route path="/dashboard" element={<LandingPage />} />
            <Route path="/responsive" element={<LandingPage />} />
            <Route path="/github" element={<GitHubPage />} />
            {/* Auth routes */}
            <Route path="/auth/login" element={<AuthPageWrapper />} />
            <Route
              path="/auth/register"
              element={<AuthPageWrapper initialMode="register" />}
            />
            <Route
              path="/chat/:sessionId?"
              element={
                <ProtectedRoute>
                  <ChatPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/skills"
              element={
                <ProtectedRoute
                  permissions={[
                    Permission.SKILL_READ,
                    Permission.MARKETPLACE_READ,
                  ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <SkillsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/marketplace"
              element={
                <ProtectedRoute
                  permissions={[
                    Permission.SKILL_READ,
                    Permission.MARKETPLACE_READ,
                  ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <MarketplacePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/mcp"
              element={
                <ProtectedRoute
                  permissions={[Permission.MCP_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <MCPPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/users"
              element={
                <ProtectedRoute
                  permissions={[Permission.USER_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <UsersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/roles"
              element={
                <ProtectedRoute
                  permissions={[Permission.ROLE_MANAGE]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <RolesPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute
                  permissions={[Permission.SETTINGS_MANAGE]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <SettingsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/feedback"
              element={
                <ProtectedRoute
                  permissions={[Permission.FEEDBACK_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <FeedbackPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/channels/:channelType?/:instanceId?"
              element={
                <ProtectedRoute
                  permissions={[Permission.CHANNEL_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <ChannelsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/agents"
              element={
                <ProtectedRoute>
                  <AgentsPage />
                </ProtectedRoute>
              }
            />
            <Route path="/models" element={<Navigate to="/agents" replace />} />
            <Route
              path="/team"
              element={
                <ProtectedRoute permissions={[Permission.TEAM_READ]}>
                  <TeamPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/persona"
              element={
                <ProtectedRoute>
                  <PersonaPage />
                </ProtectedRoute>
              }
            />
            {import.meta.env.DEV && CoverGalleryDemo && (
              <Route
                path="/dev/covers"
                element={
                  <Suspense fallback={null}>
                    <CoverGalleryDemo />
                  </Suspense>
                }
              />
            )}
            <Route
              path="/files"
              element={
                <ProtectedRoute loadingComponent={<FilesPageSkeleton />}>
                  <FilesPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookmarks"
              element={
                <ProtectedRoute loadingComponent={<FilesPageSkeleton />}>
                  <BookmarksPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/notifications"
              element={
                <ProtectedRoute
                  permissions={[Permission.NOTIFICATION_MANAGE]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <NotificationsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/memory"
              element={
                <ProtectedRoute>
                  <MemoryPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/scheduled-tasks/:taskId?"
              element={
                <ProtectedRoute
                  permissions={[Permission.SCHEDULED_TASK_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <ScheduledTasksPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/usage"
              element={
                <ProtectedRoute
                  permissions={[Permission.USAGE_READ]}
                  redirectTo="/chat"
                  showToast
                  toastMessage={t("errors.noPermission")}
                >
                  <UsagePage />
                </ProtectedRoute>
              }
            />
            {/* OAuth callback page - handles OAuth redirect from backend */}
            <Route path="/auth/callback" element={<OAuthCallback />} />
            {/* Password reset pages - no auth required */}
            <Route path="/auth/reset-request" element={<ForgotPassword />} />
            <Route path="/auth/reset-password" element={<ResetPassword />} />
            {/* Email verification page - no auth required */}
            <Route path="/auth/verify-email" element={<VerifyEmail />} />
            {/* Registration pending verification page - no auth required */}
            <Route path="/auth/pending" element={<RegistrationPending />} />
            {/* Public shared page (session or project) - no auth required */}
            <Route
              path="/shared/:shareId"
              element={
                <Suspense fallback={null}>
                  <SharedEntry />
                </Suspense>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export default App;
