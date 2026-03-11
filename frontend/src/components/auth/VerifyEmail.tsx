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
    navigate("/");
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
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/50 backdrop-blur-sm transition-colors hover:bg-white/80 dark:bg-stone-800/50 dark:hover:bg-stone-800/80">
          <img
            src="/icons/icon.svg"
            alt="LambChat"
            className="h-6 w-6 rounded"
          />
        </div>
      </div>
      <div className="fixed right-3 top-3 z-50 flex items-center gap-1.5 rounded-lg bg-white/50 p-1 backdrop-blur-sm dark:bg-stone-800/50 sm:right-4 sm:top-4 sm:gap-2 sm:bg-transparent sm:backdrop-blur-none dark:sm:bg-transparent">
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
        <div className="absolute -bottom-20 -right-20 h-80 w-80 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
      </div>
    </>
  );

  // 加载中状态
  if (status === "loading") {
    return (
      <div className="min-h-screen overflow-y-auto overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
                <LoadingSpinner className="h-8 w-8 text-blue-600 dark:text-blue-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-stone-100 sm:text-3xl">
                {t("auth.verifyingEmail")}
              </h1>
              <p className="text-gray-600 dark:text-stone-400">
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
      <div className="min-h-screen overflow-y-auto overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-stone-100 sm:text-3xl">
                {t("auth.verifyEmailSuccessTitle")}
              </h1>
              <p className="text-gray-600 dark:text-stone-400">
                {t("auth.verifyEmailSuccessDesc")}
              </p>
            </div>

            <button
              onClick={handleGoToLogin}
              className="w-full rounded-xl bg-gray-900 py-3 text-sm font-medium text-white shadow-lg shadow-gray-900/25 transition-all hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/30 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 sm:py-3.5"
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
      <div className="min-h-screen overflow-y-auto overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
        <Header />
        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <XCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-stone-100 sm:text-3xl">
                {t("auth.verifyEmailFailed")}
              </h1>
              <p className="text-gray-600 dark:text-stone-400">
                {t("auth.verifyEmailFailedDesc")}
              </p>
            </div>

            <div className="space-y-3">
              {email && (
                <button
                  onClick={handleResend}
                  disabled={isSubmitting}
                  className="w-full rounded-xl border border-gray-200 bg-white py-3 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700 sm:py-3.5"
                >
                  {isSubmitting ? (
                    <span className="flex items-center justify-center gap-2">
                      <LoadingSpinner
                        size="sm"
                        className="text-gray-700 dark:text-stone-300"
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
                className="w-full rounded-xl bg-gray-900 py-3 text-sm font-medium text-white shadow-lg shadow-gray-900/25 transition-all hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/30 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 sm:py-3.5"
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
    <div className="min-h-screen overflow-y-auto overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      <Header />
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
              <Mail className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            </div>
            <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-stone-100 sm:text-3xl">
              {t("auth.verifyEmail")}
            </h1>
            <p className="text-gray-600 dark:text-stone-400">
              {t("auth.verifyEmailDesc")}
            </p>
          </div>

          <button
            onClick={handleGoToLogin}
            className="w-full rounded-xl bg-gray-900 py-3 text-sm font-medium text-white shadow-lg shadow-gray-900/25 transition-all hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/30 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 sm:py-3.5"
          >
            {t("auth.goToLogin")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VerifyEmail;
