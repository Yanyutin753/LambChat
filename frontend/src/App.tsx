import { useEffect, useState } from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { SharedPage } from "./components/share/SharedPage";
import { OAuthCallback } from "./components/auth/OAuthCallback";
import { ForgotPassword } from "./components/auth/ForgotPassword";
import { ResetPassword } from "./components/auth/ResetPassword";
import { VerifyEmail } from "./components/auth/VerifyEmail";
import { RegistrationPending } from "./components/auth/RegistrationPending";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AppContent } from "./components/layout/AppContent";
import { NotFoundPage } from "./components/common/NotFoundPage";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { usePageTitle } from "./hooks/usePageTitle";
import { Permission } from "./types";
import { sessionApi } from "./services/api";

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
  usePageTitle(sessionName || "nav.chat");

  return <AppContent activeTab="chat" />;
}

// Simple page components that set the page title and render AppContent
function SkillsPage() {
  usePageTitle("nav.skills");
  return <AppContent activeTab="skills" />;
}

function UsersPage() {
  usePageTitle("nav.users");
  return <AppContent activeTab="users" />;
}

function RolesPage() {
  usePageTitle("nav.roles");
  return <AppContent activeTab="roles" />;
}

function SettingsPage() {
  usePageTitle("nav.settings");
  return <AppContent activeTab="settings" />;
}

function MCPPage() {
  usePageTitle("nav.mcp");
  return <AppContent activeTab="mcp" />;
}

function FeedbackPage() {
  usePageTitle("nav.feedback");
  return <AppContent activeTab="feedback" />;
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
          <Route path="/" element={<Navigate to="/chat" replace />} />
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
          {/* OAuth callback page - handles OAuth redirect from backend */}
          <Route path="/auth/callback" element={<OAuthCallback />} />
          {/* Password reset pages - no auth required */}
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          {/* Email verification page - no auth required */}
          <Route path="/verify-email" element={<VerifyEmail />} />
          {/* Registration pending verification page - no auth required */}
          <Route path="/registration-pending" element={<RegistrationPending />} />
          {/* Public shared session page - no auth required */}
          <Route path="/shared/:shareId" element={<SharedPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export default App;
