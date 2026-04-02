import { lazy, useEffect, useState } from "react";
import { Routes, Route, useParams, useNavigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { ThemeProvider } from "./contexts/ThemeContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { usePageTitle } from "./hooks/usePageTitle";
import { Permission } from "./types";
import { sessionApi } from "./services/api";

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

// Chat Page Component - handles session name for page title
function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
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
        console.warn("[ChatPage] Failed to fetch session:", err);
        setSessionName(null);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  // Use session name if available, otherwise use default "nav.chat"
  usePageTitle(sessionName || "nav.chat", undefined, {
    description: "navDesc.chat",
  });

  return <AppContent key="chat" activeTab="chat" />;
}

// Simple page components that set the page title and render AppContent
function SkillsPage() {
  usePageTitle("nav.skills", undefined, { description: "navDesc.skills" });
  return <AppContent key="skills" activeTab="skills" />;
}

function MarketplacePage() {
  usePageTitle("nav.marketplace", undefined, {
    description: "navDesc.marketplace",
  });
  return <AppContent key="marketplace" activeTab="marketplace" />;
}

function UsersPage() {
  usePageTitle("nav.users", undefined, { description: "navDesc.users" });
  return <AppContent key="users" activeTab="users" />;
}

function RolesPage() {
  usePageTitle("nav.roles", undefined, { description: "navDesc.roles" });
  return <AppContent key="roles" activeTab="roles" />;
}

function SettingsPage() {
  usePageTitle("nav.settings", undefined, {
    description: "navDesc.settings",
  });
  return <AppContent key="settings" activeTab="settings" />;
}

function MCPPage() {
  usePageTitle("nav.mcp", undefined, { description: "navDesc.mcp" });
  return <AppContent key="mcp" activeTab="mcp" />;
}

function FeedbackPage() {
  usePageTitle("nav.feedback", undefined, {
    description: "navDesc.feedback",
  });
  return <AppContent key="feedback" activeTab="feedback" />;
}

function ChannelsPage() {
  usePageTitle("nav.channels", undefined, {
    description: "navDesc.channels",
  });
  return <AppContent key="channels" activeTab="channels" />;
}

function AgentsPage() {
  usePageTitle("nav.agents", undefined, { description: "navDesc.agents" });
  return <AppContent key="agents" activeTab="agents" />;
}

// Auth page wrapper - redirects to /chat after successful login/register
function AuthPageWrapper({
  initialMode,
}: {
  initialMode?: "login" | "register";
}) {
  const navigate = useNavigate();
  usePageTitle(initialMode === "register" ? "auth.register" : "auth.login");
  return (
    <AuthPage
      initialMode={initialMode}
      onSuccess={() => navigate("/chat", { replace: true })}
    />
  );
}

// Main App Component
function App() {
  const { t } = useTranslation();
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <Toaster
          position="top-center"
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
        />
        <Routes>
          <Route path="/" element={<LandingPage />} />
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
                permissions={[Permission.SKILL_READ]}
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
                permissions={[Permission.MARKETPLACE_READ]}
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
          <Route path="/shared/:shareId" element={<SharedPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export default App;
