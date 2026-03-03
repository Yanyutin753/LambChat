/**
 * 登录/注册页面组件
 */

import { useState } from "react";
import {
  User,
  Mail,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  AtSign,
  MessageSquare,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";

type AuthMode = "login" | "register";

interface AuthPageProps {
  onSuccess?: () => void;
}

export function AuthPage({ onSuccess }: AuthPageProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, register } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 表单验证
    if (!username.trim()) {
      setError(
        mode === "login"
          ? t("auth.enterAccount")
          : t("auth.validation.enterUsername"),
      );
      return;
    }

    if (mode === "register") {
      if (!email.trim()) {
        setError(t("auth.validation.enterEmail"));
        return;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setError(t("auth.validation.invalidEmail"));
        return;
      }
    }

    if (!password) {
      setError(t("auth.validation.enterPassword"));
      return;
    }

    if (password.length < 6) {
      setError(t("auth.validation.passwordMinLength"));
      return;
    }

    if (mode === "register" && password !== confirmPassword) {
      setError(t("auth.validation.passwordMismatch"));
      return;
    }

    setIsSubmitting(true);

    try {
      if (mode === "login") {
        await login({ username, password });
        toast.success(t("auth.loginSuccess"));
      } else {
        await register({ username, email, password });
        toast.success(t("auth.registerSuccess"));
      }
      onSuccess?.();
    } catch (err) {
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const switchMode = () => {
    setMode(mode === "login" ? "register" : "login");
    setError(null);
    setEmail("");
    setConfirmPassword("");
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* 左上角 Logo */}
      <div className="absolute left-4 top-4 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-stone-100 dark:hover:bg-stone-800">
          <img src="/icons/icon.svg" alt="LambChat" className="h-5 w-5" />
        </div>
      </div>

      {/* 右上角按钮 */}
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
        <div className="absolute -bottom-20 -right-20 h-80 w-80 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
      </div>

      <div className="relative w-full max-w-md px-6">
        {/* Logo 和标题 */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-stone-100 mb-2 tracking-tight">
            LambChat
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-stone-400">
            {mode === "login" ? t("auth.loginHint") : t("auth.registerHint")}
          </p>
        </div>

        {/* 表单卡片 */}
        <div className="rounded-2xl border border-gray-200/60 bg-white/80 p-8 shadow-xl backdrop-blur-sm dark:border-stone-700/60 dark:bg-stone-900/80">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 错误提示 */}
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-600 dark:border-red-900/50 dark:bg-red-950 dark:text-red-400">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            {/* 账号输入 */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("auth.account")}
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500">
                  {mode === "login" ? <AtSign size={20} /> : <User size={20} />}
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-3.5 pl-11 pr-4 text-gray-900 placeholder-gray-400 transition-all focus:border-stone-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-stone-100 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-stone-500 dark:focus:bg-stone-800 dark:focus:ring-stone-700/50"
                  placeholder={
                    mode === "login"
                      ? t("auth.usernameOrEmailPlaceholder")
                      : t("auth.usernamePlaceholder")
                  }
                  autoComplete="username"
                />
              </div>
              {mode === "login" && (
                <p className="mt-1 text-xs text-gray-400 dark:text-stone-500">
                  {t("auth.supportsUsernameOrEmailLogin")}
                </p>
              )}
            </div>

            {/* 邮箱（仅注册） */}
            {mode === "register" && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-stone-300">
                  {t("auth.email")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500">
                    <Mail size={20} />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-3.5 pl-11 pr-4 text-gray-900 placeholder-gray-400 transition-all focus:border-stone-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-stone-100 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-stone-500 dark:focus:bg-stone-800 dark:focus:ring-stone-700/50"
                    placeholder={t("auth.emailPlaceholder")}
                    autoComplete="email"
                  />
                </div>
              </div>
            )}

            {/* 密码 */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("auth.password")}
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500">
                  <Lock size={20} />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-3.5 pl-11 pr-11 text-gray-900 placeholder-gray-400 transition-all focus:border-stone-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-stone-100 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-stone-500 dark:focus:bg-stone-800 dark:focus:ring-stone-700/50"
                  placeholder={t("auth.passwordPlaceholder")}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 transition-colors hover:text-gray-600 dark:text-stone-500 dark:hover:text-stone-300"
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            {/* 确认密码（仅注册） */}
            {mode === "register" && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-stone-300">
                  {t("auth.confirmPassword")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500">
                    <Lock size={20} />
                  </div>
                  <input
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-3.5 pl-11 pr-4 text-gray-900 placeholder-gray-400 transition-all focus:border-stone-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-stone-100 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-stone-500 dark:focus:bg-stone-800 dark:focus:ring-stone-700/50"
                    placeholder={t("auth.confirmPasswordPlaceholder")}
                    autoComplete="new-password"
                  />
                </div>
              </div>
            )}

            {/* 提交按钮 */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-xl bg-gradient-to-r from-stone-800 to-stone-900 py-3.5 font-medium text-white transition-all hover:shadow-lg hover:shadow-stone-500/20 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100 dark:from-stone-100 dark:to-stone-200 dark:text-stone-900 dark:hover:shadow-stone-500/10"
            >
              {isSubmitting ? (
                <span className="flex items-center justify-center gap-2">
                  <LoadingSpinner
                    size="sm"
                    className="text-white dark:text-black"
                  />
                  {t("auth.processing")}
                </span>
              ) : mode === "login" ? (
                t("auth.login")
              ) : (
                t("auth.register")
              )}
            </button>
          </form>

          {/* 切换登录/注册 */}
          <div className="mt-6 text-center text-sm text-gray-500 dark:text-stone-400">
            {mode === "login" ? (
              <>
                {t("auth.noAccount")}{" "}
                <button
                  onClick={switchMode}
                  className="font-medium text-gray-900 hover:text-gray-700 dark:text-stone-100 dark:hover:text-stone-300"
                >
                  {t("auth.registerNow")}
                </button>
              </>
            ) : (
              <>
                {t("auth.hasAccount")}{" "}
                <button
                  onClick={switchMode}
                  className="font-medium text-gray-900 hover:text-gray-700 dark:text-stone-100 dark:hover:text-stone-300"
                >
                  {t("auth.loginNow")}
                </button>
              </>
            )}
          </div>
        </div>

        {/* 底部信息 */}
        <p className="mt-8 text-center text-xs text-gray-400 dark:text-stone-500">
          {t("auth.termsHint")}
        </p>
      </div>
    </div>
  );
}

export default AuthPage;
