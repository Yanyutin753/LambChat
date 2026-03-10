/**
 * 注册成功等待验证页面组件
 */

import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Mail, ArrowLeft, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";

export function RegistrationPending() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [isResending, setIsResending] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);

  const email = searchParams.get("email");

  useEffect(() => {
    if (!email) {
      // 如果没有 email 参数，跳转到登录页
      navigate("/login");
    }
  }, [email, navigate]);

  const handleResendVerification = async () => {
    if (!email) return;

    setIsResending(true);
    try {
      await authApi.resendVerification(email);
      setResendSuccess(true);
      toast.success(t("auth.verificationEmailSent"));
    } catch (err) {
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
    } finally {
      setIsResending(false);
    }
  };

  const handleGoToLogin = () => {
    navigate("/login");
  };

  if (!email) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col overflow-y-auto bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* Header */}
      <div className="sticky top-0 z-50 flex items-center justify-between bg-gradient-to-br from-gray-50/90 via-white/90 to-gray-100/90 p-3 backdrop-blur-sm dark:from-stone-950/90 dark:via-stone-900/90 dark:to-stone-800/90 sm:absolute sm:left-4 sm:top-4 sm:bg-transparent sm:p-0 sm:backdrop-blur-none dark:sm:bg-transparent">
        <div
          className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg bg-white/50 backdrop-blur-sm transition-colors hover:bg-white/80 dark:bg-stone-800/50 dark:hover:bg-stone-800/80"
          onClick={handleGoToLogin}
        >
          <ArrowLeft className="h-5 w-5 text-gray-600 dark:text-stone-400" />
        </div>
        <div className="flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle />
        </div>
      </div>

      {/* Background decorations */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
        <div className="absolute -bottom-20 -right-20 h-80 w-80 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
      </div>

      {/* Main content */}
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          {/* Success icon */}
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-stone-100 sm:text-3xl">
              {t("auth.registrationSuccessTitle")}
            </h1>
            <p className="text-gray-600 dark:text-stone-400">
              {t("auth.registrationSuccessDesc")}
            </p>
          </div>

          {/* Email info card */}
          <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-stone-700 dark:bg-stone-800">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
                <Mail className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-stone-100">
                  {t("auth.verificationEmailSentTo")}
                </p>
                <p className="text-sm text-gray-600 dark:text-stone-400">
                  {email}
                </p>
              </div>
            </div>
          </div>

          {/* Instructions */}
          <div className="mb-6 rounded-xl bg-gray-50 p-4 dark:bg-stone-800/50">
            <h2 className="mb-3 font-medium text-gray-900 dark:text-stone-100">
              {t("auth.whatToDoNext")}
            </h2>
            <ol className="space-y-2 text-sm text-gray-600 dark:text-stone-400">
              <li className="flex items-start gap-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-600 dark:bg-blue-900/50 dark:text-blue-400">
                  1
                </span>
                <span>{t("auth.checkInboxStep")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-600 dark:bg-blue-900/50 dark:text-blue-400">
                  2
                </span>
                <span>{t("auth.clickVerifyLinkStep")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-600 dark:bg-blue-900/50 dark:text-blue-400">
                  3
                </span>
                <span>{t("auth.loginAfterVerifyStep")}</span>
              </li>
            </ol>
          </div>

          {/* Resend button */}
          {resendSuccess ? (
            <div className="mb-4 rounded-xl border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20">
              <p className="text-center text-sm text-green-700 dark:text-green-400">
                {t("auth.verificationEmailSent")}
              </p>
            </div>
          ) : (
            <button
              onClick={handleResendVerification}
              disabled={isResending}
              className="mb-4 w-full rounded-xl border border-gray-200 bg-white py-3 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700 sm:py-3.5"
            >
              {isResending ? (
                <span className="flex items-center justify-center gap-2">
                  <LoadingSpinner size="sm" className="text-gray-700 dark:text-stone-300" />
                  {t("auth.sending")}
                </span>
              ) : (
                t("auth.resendVerificationEmail")
              )}
            </button>
          )}

          {/* Back to login */}
          <button
            onClick={handleGoToLogin}
            className="w-full rounded-xl bg-gray-900 py-3 text-sm font-medium text-white shadow-lg shadow-gray-900/25 transition-all hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/30 active:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 sm:py-3.5"
          >
            {t("auth.backToLogin")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RegistrationPending;
