import { useState, useEffect } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { CheckCircle, XCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { BrandWordmark } from "../common/BrandWordmark";
import { BrandLogo } from "../common/BrandLogo";
import { PasswordInput } from "./PasswordInput";
import { APP_NAME } from "../../constants";
import { useMobileKeyboardAware } from "../../hooks/useMobileKeyboardAware";

export function ResetPassword() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);
  const isKeyboardOpen = useMobileKeyboardAware();

  const token = searchParams.get("token");

  useEffect(() => {
    if (!token) {
      toast.error(t("auth.invalidResetToken"));
      setIsError(true);
    }
  }, [token, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      toast.error(t("auth.invalidResetToken"));
      return;
    }
    if (!newPassword.trim()) {
      toast.error(t("auth.passwordRequired"));
      return;
    }
    if (newPassword.length < 6) {
      toast.error(t("auth.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error(t("auth.passwordMismatch"));
      return;
    }

    setIsSubmitting(true);
    try {
      await authApi.resetPassword(token, newPassword);
      setIsSuccess(true);
      toast.success(t("auth.resetPasswordSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("auth.operationFailed"));
      setIsError(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackToLogin = () => navigate("/auth/login");

  const StatusView = ({ type }: { type: "success" | "error" }) => (
    <div className="auth-shell min-h-[100svh] min-h-[100dvh] overflow-y-auto overflow-x-hidden">
      <div className="auth-crosshatch" aria-hidden="true" />
      <div className="auth-atmosphere" aria-hidden="true">
        <div className="auth-glow-main absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.05)_0%,rgba(251,146,60,0.02)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.03)_0%,rgba(251,146,60,0.015)_40%,transparent_70%)]" />
      </div>
      <nav className="fixed top-0 inset-x-0 z-50 bg-white/90 dark:bg-stone-950/90 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300">
        <div className="mx-auto flex h-14 max-w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" className="flex items-center group  gap-1.5">
            <BrandLogo
              alt={APP_NAME}
              className="h-8 transition-transform duration-300 group-hover:scale-105"
            />
            <BrandWordmark
              decorative
              className="h-7 w-auto text-stone-900 dark:text-stone-100"
            />
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>
      <div
        className={`relative z-10 flex min-h-[100svh] min-h-[100dvh] justify-center px-4 sm:px-6 ${
          isKeyboardOpen
            ? "items-start pt-16 sm:pt-20"
            : "items-center py-20 sm:py-24"
        }`}
      >
        <div className="w-full max-w-[22.5rem] sm:max-w-[380px]">
          <div className="mb-5 text-center">
            <div
              className={`auth-status-icon relative mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full ${
                type === "success"
                  ? "bg-emerald-50 dark:bg-emerald-900/20"
                  : "bg-red-50 dark:bg-red-900/20"
              }`}
            >
              {type === "success" ? (
                <CheckCircle className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <XCircle className="h-6 w-6 text-red-500 dark:text-red-400" />
              )}
            </div>
            <h1 className="text-2xl font-bold tracking-[-0.02em] text-stone-900 dark:text-stone-100 mb-1 font-serif">
              {type === "success"
                ? t("auth.resetPasswordSuccessTitle")
                : t("auth.resetPasswordFailed")}
            </h1>
            <p className="text-sm leading-relaxed text-stone-400 dark:text-stone-500">
              {type === "success"
                ? t("auth.resetPasswordSuccessDesc")
                : t("auth.resetPasswordFailedDesc")}
            </p>
          </div>
          <button
            onClick={handleBackToLogin}
            className="blog-btn-primary auth-primary-button min-h-12 w-full rounded-full py-3 text-sm font-medium transition-all"
          >
            {t("auth.goToLogin")}
          </button>
        </div>
      </div>
    </div>
  );

  if (isSuccess) return <StatusView type="success" />;
  if (isError) return <StatusView type="error" />;

  return (
    <div className="auth-shell min-h-[100svh] min-h-[100dvh] overflow-y-auto overflow-x-hidden">
      <div className="auth-crosshatch" aria-hidden="true" />
      <div className="auth-atmosphere" aria-hidden="true">
        <div className="auth-glow-main absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.025)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.035)_0%,rgba(251,146,60,0.015)_40%,transparent_70%)]" />
        <div className="auth-glow-blue absolute top-[30%] left-[5%] w-[350px] h-[350px] bg-[radial-gradient(circle,rgba(56,189,248,0.035)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.025)_0%,transparent_60%)]" />
        <div className="auth-glow-violet absolute bottom-[15%] right-[10%] w-[280px] h-[280px] bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.018)_0%,transparent_60%)]" />
      </div>
      <nav className="fixed top-0 inset-x-0 z-50 bg-white/90 dark:bg-stone-950/90 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300">
        <div className="mx-auto flex h-14 max-w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" className="flex items-center group  gap-1.5">
            <BrandLogo
              alt={APP_NAME}
              className="h-8 transition-transform duration-300 group-hover:scale-105"
            />
            <BrandWordmark
              decorative
              className="h-7 w-auto text-stone-900 dark:text-stone-100"
            />
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>
      <div
        className={`relative z-10 flex min-h-[100svh] min-h-[100dvh] justify-center px-4 sm:px-6 ${
          isKeyboardOpen
            ? "items-start pt-16 sm:pt-20"
            : "items-center py-20 sm:py-24"
        }`}
      >
        <div className="w-full max-w-[22.5rem] sm:max-w-[450px]">
          <div className="mb-5 text-center">
            <h1 className="text-2xl font-bold tracking-[-0.02em] text-stone-900 dark:text-stone-100 mb-1 font-serif">
              {t("auth.resetPassword")}
            </h1>
            <p className="text-13 leading-relaxed text-stone-400 dark:text-stone-500">
              {t("auth.resetPasswordDesc")}
            </p>
          </div>
          <div className="auth-panel rounded-[1.35rem] p-4 sm:rounded-2xl sm:p-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-13 font-medium text-stone-600 dark:text-stone-400">
                  {t("auth.newPassword")}
                </label>
                <PasswordInput
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("auth.newPasswordPlaceholder")}
                  autoComplete="new-password"
                  showPasswordLabel={t("auth.showPassword")}
                  hidePasswordLabel={t("auth.hidePassword")}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-13 font-medium text-stone-600 dark:text-stone-400">
                  {t("auth.confirmNewPassword")}
                </label>
                <PasswordInput
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t("auth.confirmPasswordPlaceholder")}
                  autoComplete="new-password"
                  showPasswordLabel={t("auth.showPassword")}
                  hidePasswordLabel={t("auth.hidePassword")}
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting}
                className="auth-primary-button min-h-12 w-full rounded-xl py-3 text-sm transition-all duration-200 hover:-translate-y-px active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
              >
                <span className="inline-flex items-center justify-center gap-2">
                  {isSubmitting && (
                    <LoadingSpinner
                      size="sm"
                      className="text-white dark:text-stone-900"
                    />
                  )}
                  <span>{t("auth.resetPassword")}</span>
                </span>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;
