import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Mail, CheckCircle, XCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { AuthLayout } from "./AuthLayout";

type VerifyStatus = "loading" | "success" | "error" | "idle";

export function VerifyEmail() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<VerifyStatus>("idle");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const token = searchParams.get("token");

  const handleVerify = useCallback(
    async (verifyToken: string) => {
      setStatus("loading");
      setIsSubmitting(true);
      try {
        await authApi.verifyEmail(verifyToken);
        setStatus("success");
        toast.success(t("auth.verifyEmailSuccess"));
      } catch (err) {
        setStatus("error");
        toast.error((err as Error).message || t("auth.verifyEmailFailed"));
      } finally {
        setIsSubmitting(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (token) handleVerify(token);
  }, [token, handleVerify]);

  const handleGoToLogin = () => navigate("/auth/login");

  const handleResend = async () => {
    const email = searchParams.get("email");
    if (!email) {
      toast.error(t("auth.emailRequired"));
      return;
    }
    setIsSubmitting(true);
    try {
      await authApi.resendVerification(email);
      toast.success(t("auth.verificationEmailSent"));
    } catch (err) {
      toast.error((err as Error).message || t("auth.operationFailed"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const StatusIcon = ({
    type,
  }: {
    type: "loading" | "success" | "error" | "idle";
  }) => {
    const config = {
      loading: {
        icon: <LoadingSpinner className="h-6 w-6" />,
        bg: "bg-stone-100 dark:bg-stone-800/50",
      },
      success: {
        icon: (
          <CheckCircle className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
        ),
        bg: "bg-emerald-50 dark:bg-emerald-900/20",
      },
      error: {
        icon: <XCircle className="h-6 w-6 text-red-500 dark:text-red-400" />,
        bg: "bg-red-50 dark:bg-red-900/20",
      },
      idle: {
        icon: <Mail className="h-6 w-6 text-stone-500 dark:text-stone-400" />,
        bg: "bg-stone-100 dark:bg-stone-800/50",
      },
    };
    const c = config[type];
    return (
      <div
        className={`auth-status-icon relative mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full ${c.bg}`}
      >
        {c.icon}
      </div>
    );
  };

  const GoToLoginButton = () => (
    <button
      onClick={handleGoToLogin}
      className="blog-btn-primary auth-primary-button w-full rounded-full py-2.5 text-sm font-medium transition-all"
    >
      {t("auth.goToLogin")}
    </button>
  );

  return (
    <AuthLayout>
      <div className="mb-5 text-center">
        <StatusIcon type={status} />
        <h1 className="text-xl font-bold text-stone-900 dark:text-stone-100 mb-1 font-serif">
          {status === "loading" && t("auth.verifyingEmail")}
          {status === "success" && t("auth.verifyEmailSuccessTitle")}
          {status === "error" && t("auth.verifyEmailFailed")}
          {status === "idle" && t("auth.verifyEmail")}
        </h1>
        <p className="text-sm text-stone-400 dark:text-stone-500">
          {(status === "loading" || status === "idle") && t("auth.pleaseWait")}
          {status === "success" && t("auth.verifyEmailSuccessDesc")}
          {status === "error" && t("auth.verifyEmailFailedDesc")}
        </p>
      </div>

      {status === "error" && searchParams.get("email") && (
        <button
          onClick={handleResend}
          disabled={isSubmitting}
          className="blog-btn-ghost auth-secondary-button mb-2.5 w-full rounded-full py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="inline-flex items-center justify-center gap-2">
            {isSubmitting && <LoadingSpinner size="sm" />}
            <span>{t("auth.resendVerification")}</span>
          </span>
        </button>
      )}

      <GoToLoginButton />
    </AuthLayout>
  );
}

export default VerifyEmail;
