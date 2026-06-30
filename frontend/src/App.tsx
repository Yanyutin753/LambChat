import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  Routes,
  Route,
  useParams,
  useNavigate,
  useLocation,
  Navigate,
  matchPath,
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
import { sessionApi } from "./services/api";
import {
  getCachedSessionTitle,
  listenSessionTitleUpdated,
} from "./utils/sessionTitleEvents";
import { APP_TOASTER_CLASS_NAME } from "./components/layout/AppContent/appToastLayout";
import { PwaStatusToasts } from "./components/pwa/PwaStatusToasts";
import { appNotificationService } from "./services/notifications/appNotificationService";
import { UpdateDialog } from "./components/update/UpdateDialog";
import { useAutoUpdate } from "./hooks/useAutoUpdate";
import { useAuth } from "./hooks/useAuth";
import { useExtensionContributions } from "./hooks/useExtensionContributions";
import {
  buildAppRouteContributions,
  type CoreAppRouteContribution,
  type PluginRuntimeContributionStates,
} from "./extensions/coreContributions";

const EMPTY_RUNTIME_PLUGINS: PluginRuntimeContributionStates = [];
const BUILTIN_PLUGIN_APP_ROUTE_LOADING_PATHS = [
  "/agent-team",
  "/feedback",
  "/usage",
  "/workflows",
  "/workflows/:workflowId/editor",
  "/workflows/:workflowId/runs/:runId",
] as const;

const SharedPage = lazy(() =>
  import("./components/share/SharedPage").then((m) => ({
    default: m.SharedPage,
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
const NotFoundPage = lazy(() =>
  import("./components/common/NotFoundPage").then((m) => ({
    default: m.NotFoundPage,
  })),
);

function ChatPageSEO() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [sessionName, setSessionName] = useState<string | null>(null);
  const prevSessionIdRef = useRef<string | null>(null);

  // Fetch session name when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      prevSessionIdRef.current = null;
      return;
    }

    // Reset only when switching to a different session
    if (sessionId !== prevSessionIdRef.current) {
      setSessionName(null);
      prevSessionIdRef.current = sessionId;
    }

    const fetchSessionName = async () => {
      try {
        const session = await sessionApi.get(sessionId);
        if (session?.name) {
          setSessionName(session.name);
        }
      } catch (err) {
        console.warn("[ChatPage] Failed to fetch session:", err);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  // React immediately when generateTitle finishes in the active chat session.
  useEffect(() => {
    if (!sessionId) return;

    const cachedTitle = getCachedSessionTitle(sessionId);
    if (cachedTitle) {
      setSessionName(cachedTitle);
    }

    return listenSessionTitleUpdated((detail) => {
      if (detail.sessionId === sessionId) {
        setSessionName(detail.title);
      }
    });
  }, [sessionId]);

  // Poll for session name after initial load (handles race with generate-title)
  useEffect(() => {
    if (!sessionId || sessionName) return;

    const delay = setTimeout(() => {
      sessionApi
        .get(sessionId)
        .then((session) => {
          if (session?.name) setSessionName(session.name);
        })
        .catch(() => {});
    }, 3000);

    return () => clearTimeout(delay);
  }, [sessionId, sessionName]);

  // Use session name if available, otherwise use default "nav.chat"
  useSEO({
    title: sessionName || "seo.chat.title",
    description: "seo.chat.description",
    path: sessionId ? `/chat/${sessionId}` : "/chat",
  });

  return null;
}

// Chat Page Component
function ChatPage({
  runtimePlugins,
}: {
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  return (
    <>
      <ChatPageSEO />
      <AppContent key="chat" activeTab="chat" runtimePlugins={runtimePlugins} />
    </>
  );
}

function CoreAppRoutePage({
  route,
  runtimePlugins,
}: {
  route: CoreAppRouteContribution;
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  useSEO({
    title: route.seoTitle,
    description: route.seoDescription,
    path: route.seoPath ?? route.path,
  });

  return (
    <AppContent
      key={route.tab}
      activeTab={route.tab}
      runtimePlugins={runtimePlugins}
    />
  );
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
  const location = useLocation();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const canReadExtensionContributions = isAuthenticated && !isAuthLoading;
  const {
    data: extensionContributions,
    isLoading: areExtensionContributionsLoading,
    error: extensionContributionsError,
  } = useExtensionContributions({ enabled: canReadExtensionContributions });
  const runtimePlugins = extensionContributions?.plugins ?? EMPTY_RUNTIME_PLUGINS;
  const appRouteContributions = useMemo(
    () => buildAppRouteContributions(runtimePlugins),
    [runtimePlugins],
  );
  const pluginAppRouteLoadingPaths = useMemo(() => {
    const declaredPluginPaths = appRouteContributions
      .filter((route) => route.pluginId)
      .map((route) => route.path);
    return Array.from(
      new Set([
        ...BUILTIN_PLUGIN_APP_ROUTE_LOADING_PATHS,
        ...declaredPluginPaths,
      ]),
    );
  }, [appRouteContributions]);
  const shouldShowPluginRouteLoading =
    canReadExtensionContributions &&
    (areExtensionContributionsLoading ||
      (!extensionContributions && !extensionContributionsError)) &&
    pluginAppRouteLoadingPaths.some((path) =>
      path === location.pathname || Boolean(matchPath({ path, end: true }, location.pathname)),
    );

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
                  <ChatPage runtimePlugins={runtimePlugins} />
                </ProtectedRoute>
              }
            />
            {appRouteContributions.map((route) => (
              <Route
                key={route.id}
                path={route.path}
                element={
                  <ProtectedRoute
                    permissions={
                      route.permissions ? [...route.permissions] : undefined
                    }
                    redirectTo={route.redirectTo}
                    showToast={route.showNoPermissionToast}
                    toastMessage={
                      route.showNoPermissionToast
                        ? t("errors.noPermission")
                        : undefined
                    }
                    loadingComponent={
                      route.id === "files" ? <FilesPageSkeleton /> : undefined
                    }
                  >
                    <CoreAppRoutePage
                      route={route}
                      runtimePlugins={runtimePlugins}
                    />
                  </ProtectedRoute>
                }
              />
            ))}
            {shouldShowPluginRouteLoading && (
              <Route
                path={location.pathname}
                element={
                  <ProtectedRoute>
                    <ChatPageSkeleton />
                  </ProtectedRoute>
                }
              />
            )}
            <Route path="/models" element={<Navigate to="/agents" replace />} />
            {/* OAuth callback page - handles OAuth redirect from backend */}
            <Route path="/auth/callback" element={<OAuthCallback />} />
            {/* Password reset pages - no auth required */}
            <Route path="/auth/reset-request" element={<ForgotPassword />} />
            <Route path="/auth/reset-password" element={<ResetPassword />} />
            {/* Email verification page - no auth required */}
            <Route path="/auth/verify-email" element={<VerifyEmail />} />
            {/* Registration pending verification page - no auth required */}
            <Route path="/auth/pending" element={<RegistrationPending />} />
            {/* Public shared session page - no auth required */}
            <Route
              path="/shared/:shareId"
              element={
                <Suspense fallback={null}>
                  <SharedPage />
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
