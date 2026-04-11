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
      // 如果没有 email 参数，跳转到首页（会自动显示登录页）
      navigate("/auth/login");
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
    navigate("/auth/login");
  };

  if (!email) {
    return null;
  }

  return (
    <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
      {/* 左上角返回按钮 */}
      <div className="fixed left-3 top-3 z-50 flex items-center gap-2 sm:left-4 sm:top-4">
        <div
          className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg bg-white/40 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60"
          onClick={handleGoToLogin}
        >
          <ArrowLeft className="h-5 w-5 text-stone-600 dark:text-stone-400" />
        </div>
      </div>

      {/* 右上角按钮 */}
      <div className="fixed right-3 top-3 z-50 flex items-center gap-1.5 rounded-lg bg-white/40 p-1.5 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60 sm:right-4 sm:top-4">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      {/* 主内容区域 */}
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          {/* 成功图标 */}
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
              {t("auth.registrationSuccessTitle")}
            </h1>
            <p className="text-stone-600 dark:text-stone-400">
              {t("auth.registrationSuccessDesc")}
            </p>
          </div>

          {/* 邮箱信息卡片 */}
          <div className="auth-panel mb-6 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="auth-accent-icon flex h-10 w-10 items-center justify-center rounded-full">
                <Mail className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-stone-900 dark:text-stone-100">
                  {t("auth.verificationEmailSentTo")}
                </p>
                <p className="text-sm text-stone-600 dark:text-stone-400">
                  {email}
                </p>
              </div>
            </div>
          </div>

          {/* 操作指引 */}
          <div className="auth-muted-panel mb-6 rounded-xl p-4">
            <h2 className="mb-3 font-medium text-stone-900 dark:text-stone-100">
              {t("auth.whatToDoNext")}
            </h2>
            <ol className="space-y-2 text-sm text-stone-600 dark:text-stone-400">
              <li className="flex items-start gap-2">
                <span className="auth-accent-badge mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium">
                  1
                </span>
                <span>{t("auth.checkInboxStep")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="auth-accent-badge mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium">
                  2
                </span>
                <span>{t("auth.clickVerifyLinkStep")}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="auth-accent-badge mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium">
                  3
                </span>
                <span>{t("auth.loginAfterVerifyStep")}</span>
              </li>
            </ol>
          </div>

          {/* 重发按钮 */}
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
              className="auth-secondary-button mb-4 w-full rounded-xl py-3 text-sm font-medium shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50 sm:py-3.5"
            >
              {isResending ? (
                <span className="flex items-center justify-center gap-2">
                  <LoadingSpinner
                    size="sm"
                    className="text-stone-700 dark:text-stone-300"
                  />
                  {t("auth.sending")}
                </span>
              ) : (
                t("auth.resendVerificationEmail")
              )}
            </button>
          )}

          {/* 返回登录 */}
          <button
            onClick={handleGoToLogin}
            className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 sm:py-3.5"
          >
            {t("auth.backToLogin")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RegistrationPending;
