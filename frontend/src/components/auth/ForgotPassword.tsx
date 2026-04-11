/**
 * 忘记密码页面组件
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, ArrowLeft, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { APP_NAME } from "../../constants";

interface ForgotPasswordProps {
  onBackToLogin?: () => void;
}

export function ForgotPassword({ onBackToLogin }: ForgotPasswordProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleBackToLogin = () => {
    if (onBackToLogin) {
      onBackToLogin();
    } else {
      navigate("/auth/login");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      toast.error(t("auth.emailRequired"));
      return;
    }

    setIsSubmitting(true);

    try {
      await authApi.forgotPassword(email);
      setIsSuccess(true);
      toast.success(t("auth.forgotPasswordSuccess"));
    } catch (err) {
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSuccess) {
    return (
      <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
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

        <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
          <div className="w-full max-w-md py-8">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
                {t("auth.checkYourEmail")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.forgotPasswordEmailSent")}
              </p>
            </div>

            <button
              onClick={handleBackToLogin}
              className="auth-secondary-button flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-medium shadow-sm transition-all"
            >
              <ArrowLeft size={16} />
              {t("auth.backToLogin")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
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

      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          {/* 标题 */}
          <div className="mb-6 text-center sm:mb-8">
            <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
              {t("auth.forgotPassword")}
            </h1>
            <p className="text-sm text-stone-600 dark:text-stone-400 sm:text-base">
              {t("auth.forgotPasswordDesc")}
            </p>
          </div>

          {/* 表单卡片 */}
          <div className="auth-panel rounded-2xl p-6 sm:p-8">
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* 邮箱输入 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.email")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
                    <Mail size={16} className="sm:h-[18px] sm:w-[18px]" />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="auth-input w-full rounded-xl py-2.5 pl-10 pr-3 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={t("auth.emailPlaceholder")}
                  />
                </div>
              </div>

              {/* 提交按钮 */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 sm:py-3.5"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <LoadingSpinner
                      size="sm"
                      className="text-white dark:text-stone-900"
                    />
                    {t("auth.sending")}
                  </span>
                ) : (
                  t("auth.sendResetEmail")
                )}
              </button>
            </form>
          </div>

          {/* 返回登录链接 */}
          <div className="mt-6 text-center">
            <button
              onClick={handleBackToLogin}
              className="inline-flex items-center gap-1.5 text-sm text-stone-600 transition-colors hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-200"
            >
              <ArrowLeft size={14} />
              {t("auth.backToLogin")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForgotPassword;
