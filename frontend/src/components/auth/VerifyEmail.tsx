/**
 * 验证邮箱页面组件
 */

import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Mail, CheckCircle, XCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { APP_NAME } from "../../constants";

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
        const errorMessage =
          (err as Error).message || t("auth.verifyEmailFailed");
        toast.error(errorMessage);
      } finally {
        setIsSubmitting(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (token) {
      handleVerify(token);
    }
  }, [token, handleVerify]);

  const handleGoToLogin = () => {
    navigate("/auth/login");
  };

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
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 通用 Header 组件
  const Header = () => (
    <>
      <div className="fixed left-3 top-3 z-50 flex items-center gap-2 sm:left-4 sm:top-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/40 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60">
          <img
            src="/icons/icon.svg"
            alt={APP_NAME}
            className="h-6 w-6 rounded"
          />
        </div>
      </div>
      <div className="fixed right-3 top-3 z-50 flex items-center gap-1.5 rounded-lg bg-white/40 p-1.5 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60 sm:right-4 sm:top-4">
        <LanguageToggle />
        <ThemeToggle />
      </div>
    </>
  );

  // 加载中状态
  if (status === "loading") {
    return (
      <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="auth-accent-icon mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                <LoadingSpinner className="h-8 w-8" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
                {t("auth.verifyingEmail")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.pleaseWait")}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 成功状态
  if (status === "success") {
    return (
      <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
                {t("auth.verifyEmailSuccessTitle")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.verifyEmailSuccessDesc")}
              </p>
            </div>

            <button
              onClick={handleGoToLogin}
              className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 sm:py-3.5"
            >
              {t("auth.goToLogin")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 错误状态
  if (status === "error") {
    const email = searchParams.get("email");

    return (
      <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <XCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
                {t("auth.verifyEmailFailed")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.verifyEmailFailedDesc")}
              </p>
            </div>

            <div className="space-y-3">
              {email && (
                <button
                  onClick={handleResend}
                  disabled={isSubmitting}
                  className="auth-secondary-button w-full rounded-xl py-3 text-sm font-medium shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50 sm:py-3.5"
                >
                  {isSubmitting ? (
                    <span className="flex items-center justify-center gap-2">
                      <LoadingSpinner
                        size="sm"
                        className="text-stone-700 dark:text-stone-300"
                      />
                      {t("auth.sending")}
                    </span>
                  ) : (
                    t("auth.resendVerification")
                  )}
                </button>
              )}
              <button
                onClick={handleGoToLogin}
                className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 sm:py-3.5"
              >
                {t("auth.goToLogin")}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 空闲状态 - 无 token
  return (
    <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
      <Header />
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          <div className="mb-8 text-center">
            <div className="auth-accent-icon mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
              <Mail className="h-8 w-8" />
            </div>
            <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
              {t("auth.verifyEmail")}
            </h1>
            <p className="text-stone-600 dark:text-stone-400">
              {t("auth.verifyEmailDesc")}
            </p>
          </div>

          <button
            onClick={handleGoToLogin}
            className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 sm:py-3.5"
          >
            {t("auth.goToLogin")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VerifyEmail;
