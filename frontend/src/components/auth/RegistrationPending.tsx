import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Mail, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { AuthLayout } from "./AuthLayout";

export function RegistrationPending() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [isResending, setIsResending] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const email = searchParams.get("email");

  useEffect(() => {
    if (!email) navigate("/auth/login");
  }, [email, navigate]);

  const handleResendVerification = async () => {
    if (!email) return;
    setIsResending(true);
    try {
      await authApi.resendVerification(email);
      setResendSuccess(true);
      toast.success(t("auth.verificationEmailSent"));
    } catch (err) {
      toast.error((err as Error).message || t("auth.operationFailed"));
    } finally {
      setIsResending(false);
    }
  };

  const handleGoToLogin = () => navigate("/auth/login");

  if (!email) return null;

  return (
    <AuthLayout>
      <div className="mb-5 text-center">
        <div className="auth-status-icon relative mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-900/20">
          <CheckCircle className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
        </div>
        <h1 className="text-xl font-bold text-stone-900 dark:text-stone-100 mb-1 font-serif">
          {t("auth.registrationSuccessTitle")}
        </h1>
        <p className="text-sm text-stone-400 dark:text-stone-500">
          {t("auth.registrationSuccessDesc")}
        </p>
      </div>

      <div className="auth-panel mb-3 rounded-xl p-3">
        <div className="flex items-center gap-2.5">
          <div className="auth-accent-icon flex h-8 w-8 items-center justify-center rounded-full">
            <Mail className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-stone-700 dark:text-stone-300">
              {t("auth.verificationEmailSentTo")}
            </p>
            <p className="text-xs text-stone-400 dark:text-stone-500 truncate">
              {email}
            </p>
          </div>
        </div>
      </div>

      <div className="auth-muted-panel mb-3 rounded-xl p-3">
        <h2 className="mb-2 text-xs font-medium text-stone-700 dark:text-stone-300">
          {t("auth.whatToDoNext")}
        </h2>
        <ol className="space-y-1.5 text-xs text-stone-500 dark:text-stone-400">
          <li className="flex items-start gap-2">
            <span className="auth-accent-badge mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
              1
            </span>
            <span>{t("auth.checkInboxStep")}</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="auth-accent-badge mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
              2
            </span>
            <span>{t("auth.clickVerifyLinkStep")}</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="auth-accent-badge mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
              3
            </span>
            <span>{t("auth.loginAfterVerifyStep")}</span>
          </li>
        </ol>
      </div>

      {resendSuccess ? (
        <div className="mb-2.5 rounded-lg border border-emerald-200/60 bg-emerald-50/80 p-2.5 text-center text-xs text-emerald-700 dark:border-emerald-800/40 dark:bg-emerald-900/20 dark:text-emerald-400">
          {t("auth.verificationEmailSent")}
        </div>
      ) : (
        <button
          onClick={handleResendVerification}
          disabled={isResending}
          className="blog-btn-ghost auth-secondary-button mb-2.5 w-full rounded-full py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="inline-flex items-center justify-center gap-2">
            {isResending && <LoadingSpinner size="sm" />}
            <span>{t("auth.resendVerificationEmail")}</span>
          </span>
        </button>
      )}

      <button
        onClick={handleGoToLogin}
        className="blog-btn-primary auth-primary-button w-full rounded-full py-2.5 text-sm font-medium transition-all"
      >
        {t("auth.backToLogin")}
      </button>
    </AuthLayout>
  );
}

export default RegistrationPending;
