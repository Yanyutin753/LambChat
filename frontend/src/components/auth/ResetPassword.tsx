/**
 * 重置密码页面组件
 */

import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Lock, CheckCircle, XCircle } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { authApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { APP_NAME } from "../../constants";

export function ResetPassword() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);

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
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
      setIsError(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackToLogin = () => {
    navigate("/auth/login");
  };

  // 成功状态
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
                {t("auth.resetPasswordSuccessTitle")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.resetPasswordSuccessDesc")}
              </p>
            </div>

            <button
              onClick={handleBackToLogin}
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
  if (isError) {
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
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <XCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
              </div>
              <h1 className="mb-2 text-2xl font-bold text-stone-900 dark:text-stone-100 sm:text-3xl font-serif">
                {t("auth.resetPasswordFailed")}
              </h1>
              <p className="text-stone-600 dark:text-stone-400">
                {t("auth.resetPasswordFailedDesc")}
              </p>
            </div>

            <button
              onClick={handleBackToLogin}
              className="auth-primary-button w-full rounded-xl py-3 text-sm font-medium transition-all hover:-translate-y-0.5 active:translate-y-0 sm:py-3.5"
            >
              {t("auth.goToLogin")}
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
              {t("auth.resetPassword")}
            </h1>
            <p className="text-sm text-stone-600 dark:text-stone-400 sm:text-base">
              {t("auth.resetPasswordDesc")}
            </p>
          </div>

          {/* 表单卡片 */}
          <div className="auth-panel rounded-2xl p-6 sm:p-8">
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* 新密码 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.newPassword")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
                    <Lock size={16} className="sm:h-[18px] sm:w-[18px]" />
                  </div>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="auth-input w-full rounded-xl py-2.5 pl-10 pr-3 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={t("auth.newPasswordPlaceholder")}
                    autoComplete="new-password"
                  />
                </div>
              </div>

              {/* 确认密码 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.confirmNewPassword")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
                    <Lock size={16} className="sm:h-[18px] sm:w-[18px]" />
                  </div>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="auth-input w-full rounded-xl py-2.5 pl-10 pr-3 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={t("auth.confirmPasswordPlaceholder")}
                    autoComplete="new-password"
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
                    {t("auth.processing")}
                  </span>
                ) : (
                  t("auth.resetPassword")
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;
