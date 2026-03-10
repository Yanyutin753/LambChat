/**
 * 登录/注册页面组件
 */

import { useState, useEffect, useRef } from "react";
import { User, Mail, Lock, AlertCircle, AtSign } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Turnstile } from "react-turnstile";
import { useAuth } from "../../hooks/useAuth";
import { useTheme } from "../../contexts/ThemeContext";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { authApi } from "../../services/api";

type AuthMode = "login" | "register";

interface TurnstileConfig {
  enabled: boolean;
  site_key: string;
  require_on_login: boolean;
  require_on_register: boolean;
  require_on_password_change: boolean;
}

interface AuthPageProps {
  onSuccess?: () => void;
}

export function AuthPage({ onSuccess }: AuthPageProps) {
  const { t } = useTranslation();

  // 覆盖全局 overflow: hidden，允许登录页面滚动
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    
    // 保存原始样式
    const originalHtmlOverflow = html.style.overflow;
    const originalBodyOverflow = body.style.overflow;
    const originalRootOverflow = root?.style.overflow;
    
    // 设置允许滚动
    html.style.overflow = 'auto';
    body.style.overflow = 'auto';
    if (root) root.style.overflow = 'auto';
    
    // 组件卸载时恢复原始样式
    return () => {
      html.style.overflow = originalHtmlOverflow;
      body.style.overflow = originalBodyOverflow;
      if (root) root.style.overflow = originalRootOverflow || '';
    };
  }, []);

  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileKey, setTurnstileKey] = useState(0); // 用于强制重新渲染 Turnstile

  const { theme } = useTheme();

  // 当主题变化时，强制重新渲染 Turnstile 以更新主题
  useEffect(() => {
    setTurnstileKey(prev => prev + 1);
  }, [theme]);

  const { login, register, loginWithOAuth } = useAuth();
  const [oauthProviders, setOauthProviders] = useState<
    { id: string; name: string }[]
  >([]);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [turnstileConfig, setTurnstileConfig] = useState<TurnstileConfig>({
    enabled: false,
    site_key: "",
    require_on_login: false,
    require_on_register: true,
    require_on_password_change: true,
  });

  // Use ref to access current mode without adding it to deps
  const modeRef = useRef(mode);
  modeRef.current = mode;

  // 获取 OAuth 提供商列表和认证设置
  useEffect(() => {
    let mounted = true;
    const fetchAuthData = async () => {
      try {
        const result = await authApi.getOAuthProviders();
        if (!mounted) return;
        setOauthProviders(result.providers);
        setRegistrationEnabled(result.registration_enabled);
        // 设置 Turnstile 配置
        if (result.turnstile) {
          setTurnstileConfig(result.turnstile);
        }
        // 如果注册已关闭且当前是注册模式，切换回登录
        if (!result.registration_enabled && modeRef.current === "register") {
          setMode("login");
          setEmail("");
          setConfirmPassword("");
        }
      } catch {
        // 忽略错误，可能 OAuth 未配置
      }
    };
    fetchAuthData();
    return () => {
      mounted = false;
    };
  }, []);

  // 检查当前模式是否需要 Turnstile
  const requiresTurnstile = () => {
    if (!turnstileConfig.enabled || !turnstileConfig.site_key) return false;
    if (mode === "login") return turnstileConfig.require_on_login;
    if (mode === "register") return turnstileConfig.require_on_register;
    return false;
  };

  // 重置 Turnstile token 当模式切换时
  useEffect(() => {
    setTurnstileToken(null);
    // 通过改变 key 强制重新渲染 Turnstile
    setTurnstileKey(prev => prev + 1);
  }, [mode]);

  // OAuth 登录处理
  const handleOAuthLogin = async (provider: string) => {
    try {
      await loginWithOAuth(provider);
    } catch {
      toast.error(t("auth.oauthLoginFailed"));
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
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

    // Turnstile 验证
    if (requiresTurnstile() && !turnstileToken) {
      setError(t("auth.turnstileRequired"));
      return;
    }

    setIsSubmitting(true);

    try {
      if (mode === "login") {
        await login({ username, password }, turnstileToken || undefined);
        toast.success(t("auth.loginSuccess"));
      } else {
        await register({ username, email, password }, turnstileToken || undefined);
        toast.success(t("auth.registerSuccess"));
      }
      onSuccess?.();
    } catch (err) {
      const errorMessage = (err as Error).message || t("auth.operationFailed");
      toast.error(errorMessage);
      setError(errorMessage);
      // 重置 Turnstile widget
      setTurnstileToken(null);
      setTurnstileKey(prev => prev + 1);
    } finally {
      setIsSubmitting(false);
    }
  };

  const switchMode = () => {
    // 如果注册已禁用，不允许切换到注册模式
    if (mode === "login" && !registrationEnabled) {
      return;
    }
    setMode(mode === "login" ? "register" : "login");
    setError(null);
    setEmail("");
    setConfirmPassword("");
  };

  return (
    <div className="min-h-screen overflow-y-auto overflow-x-hidden bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* 左上角 Logo */}
      <div className="fixed left-3 top-3 z-50 flex items-center gap-2 sm:left-4 sm:top-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/50 backdrop-blur-sm transition-colors hover:bg-white/80 dark:bg-stone-800/50 dark:hover:bg-stone-800/80">
          <img
            src="/icons/icon.svg"
            alt="LambChat"
            className="h-5 w-5 rounded-full"
          />
        </div>
      </div>

      {/* 右上角按钮 */}
      <div className="fixed right-3 top-3 z-50 flex items-center gap-1.5 rounded-lg bg-white/50 p-1 backdrop-blur-sm dark:bg-stone-800/50 sm:right-4 sm:top-4 sm:gap-2 sm:bg-transparent sm:backdrop-blur-none dark:sm:bg-transparent">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      {/* 背景装饰 */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
        <div className="absolute -bottom-20 -right-20 h-80 w-80 rounded-full bg-gray-200/50 blur-3xl dark:bg-stone-700/30" />
      </div>

      {/* 主内容区域 - CSS Grid 实现居中且可滚动 */}
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          {/* Logo 和标题 */}
          <div className="mb-6 text-center sm:mb-8">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-stone-100 mb-2 tracking-tight font-serif sm:text-3xl">
              LambChat
            </h1>
            <p className="mt-1.5 text-sm text-gray-500 dark:text-stone-400 sm:mt-2">
              {mode === "login" ? t("auth.loginHint") : t("auth.registerHint")}
            </p>
          </div>

          {/* 表单卡片 */}
          <div className="w-full rounded-2xl border border-gray-200/60 bg-white/90 p-5 shadow-xl backdrop-blur-sm dark:border-stone-700/40 dark:bg-stone-900/90 sm:p-8">
            {/* OAuth 登录按钮 - 放在最上面 */}
            {oauthProviders.length > 0 && (
              <div className="mb-4 space-y-2.5 sm:mb-6 sm:space-y-3">
                {oauthProviders.map((provider) => (
                  <button
                    key={provider.id}
                    type="button"
                    onClick={() => handleOAuthLogin(provider.id)}
                    className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-all hover:-translate-y-0.5 hover:bg-gray-50 hover:shadow-md active:translate-y-0 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700 dark:hover:shadow-lg sm:gap-3 sm:px-4 sm:py-3"
                  >
                    {provider.id === "google" && (
                      <svg
                        className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5"
                        viewBox="0 0 24 24"
                      >
                        <path
                          fill="currentColor"
                          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        />
                        <path
                          fill="currentColor"
                          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                        />
                      </svg>
                    )}
                    {provider.id === "github" && (
                      <svg
                        className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                      >
                        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                      </svg>
                    )}
                    {provider.id === "apple" && (
                      <svg
                        className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                      >
                        <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
                      </svg>
                    )}
                    <span className="text-xs sm:text-sm">
                      {t("auth.continueWith", { provider: provider.name })}
                    </span>
                  </button>
                ))}

                {/* 分隔线 */}
                <div className="relative flex items-center py-2.5 sm:py-3">
                  <div className="flex-grow border-t border-gray-200 dark:border-stone-700" />
                  <span className="flex-shrink-0 mx-3 text-[10px] font-medium uppercase tracking-widest text-gray-400 dark:text-stone-500 sm:mx-4 sm:text-xs">
                    {t("auth.or")}
                  </span>
                  <div className="flex-grow border-t border-gray-200 dark:border-stone-700" />
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3.5 sm:space-y-5">
              {/* 错误提示 */}
              {error && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200/60 bg-red-50/80 p-2.5 text-xs text-red-600 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-400 sm:p-3 sm:text-sm">
                  <AlertCircle
                    size={14}
                    className="flex-shrink-0 sm:h-4 sm:w-4"
                  />
                  <span>{error}</span>
                </div>
              )}

              {/* 账号输入 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.account")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500 sm:pl-3.5">
                    {mode === "login" ? (
                      <AtSign size={16} className="sm:h-[18px] sm:w-[18px]" />
                    ) : (
                      <User size={16} className="sm:h-[18px] sm:w-[18px]" />
                    )}
                  </div>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-2.5 pl-10 pr-3 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400 dark:focus:bg-stone-800 dark:focus:ring-blue-500/20 sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={
                      mode === "login"
                        ? t("auth.usernameOrEmailPlaceholder")
                        : t("auth.usernamePlaceholder")
                    }
                    autoComplete="username"
                  />
                </div>
                {mode === "login" && (
                  <p className="mt-1 text-[10px] text-gray-400 dark:text-stone-500 sm:mt-1.5 sm:text-xs">
                    {t("auth.supportsUsernameOrEmailLogin")}
                  </p>
                )}
              </div>

              {/* 邮箱（仅注册） */}
              {mode === "register" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                    {t("auth.email")}
                  </label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500 sm:pl-3.5">
                      <Mail size={16} className="sm:h-[18px] sm:w-[18px]" />
                    </div>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-2.5 pl-10 pr-3 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400 dark:focus:bg-stone-800 dark:focus:ring-blue-500/20 sm:py-3 sm:pl-11 sm:pr-4"
                      placeholder={t("auth.emailPlaceholder")}
                      autoComplete="email"
                    />
                  </div>
                </div>
              )}

              {/* 密码 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.password")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500 sm:pl-3.5">
                    <Lock size={16} className="sm:h-[18px] sm:w-[18px]" />
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-2.5 pl-10 pr-3 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400 dark:focus:bg-stone-800 dark:focus:ring-blue-500/20 sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={t("auth.passwordPlaceholder")}
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                  />
                </div>
              </div>

              {/* 确认密码（仅注册） */}
              {mode === "register" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                    {t("auth.confirmPassword")}
                  </label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 dark:text-stone-500 sm:pl-3.5">
                      <Lock size={16} className="sm:h-[18px] sm:w-[18px]" />
                    </div>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="w-full rounded-xl border border-gray-200/80 bg-white/80 py-2.5 pl-10 pr-3 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-stone-600/60 dark:bg-stone-800/60 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400 dark:focus:bg-stone-800 dark:focus:ring-blue-500/20 sm:py-3 sm:pl-11 sm:pr-4"
                      placeholder={t("auth.confirmPasswordPlaceholder")}
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              )}

              {/* Turnstile 人机验证 */}
              {requiresTurnstile() && (
                <div className="mb-4 w-full rounded-xl border border-gray-200/80 bg-white/80 p-3 dark:border-stone-600/60 dark:bg-stone-800/60 sm:mb-6 sm:p-4">
                  <div className="flex justify-center">
                    <Turnstile
                      key={turnstileKey}
                      sitekey={turnstileConfig.site_key}
                      onSuccess={(token) => setTurnstileToken(token)}
                      onError={() => {
                        setTurnstileToken(null);
                        setError(t("auth.turnstileError"));
                      }}
                      onExpire={() => setTurnstileToken(null)}
                      theme={theme}
                    />
                  </div>
                </div>
              )}

              {/* 提交按钮 */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-xl bg-gray-900 py-3 text-sm font-medium text-white shadow-lg shadow-gray-900/25 transition-all hover:-translate-y-0.5 hover:bg-gray-800 hover:shadow-xl hover:shadow-gray-900/30 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 dark:bg-white dark:text-gray-900 dark:shadow-white/10 dark:hover:bg-stone-100 sm:py-3.5"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <LoadingSpinner
                      size="sm"
                      className="text-white dark:text-gray-900"
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
            <div className="mt-4 flex flex-wrap items-center justify-center gap-1 text-xs text-gray-500 dark:text-stone-400 sm:mt-5 sm:text-sm">
              {registrationEnabled ? (
                <>
                  <span>
                    {mode === "login" ? t("auth.noAccount") : t("auth.hasAccount")}
                  </span>
                  <button
                    type="button"
                    onClick={switchMode}
                    className="font-medium text-gray-900 underline-offset-2 transition-all hover:text-gray-700 hover:underline dark:text-white dark:hover:text-stone-200"
                  >
                    {mode === "login"
                      ? t("auth.registerNow")
                      : t("auth.loginNow")}
                  </button>
                </>
              ) : (
                mode === "login" && (
                  <span className="text-gray-400 dark:text-stone-500">
                    {t("auth.registrationDisabled")}
                  </span>
                )
              )}
            </div>

            {/* 服务条款 */}
            <p className="mt-3 text-center text-[10px] text-gray-400 dark:text-stone-500 sm:mt-4 sm:text-xs">
              {t("auth.termsHint")}
            </p>

            {/* 页脚 */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-x-2 text-[10px] text-gray-400 dark:text-stone-500 sm:mt-6 sm:gap-x-3 sm:text-xs">
              <a
                href="https://github.com/LLM-Lamb/LambChat"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 transition-colors hover:text-gray-600 dark:hover:text-stone-300 sm:gap-1.5"
              >
                <svg
                  className="h-3 w-3 sm:h-3.5 sm:w-3.5"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
                <span>GitHub</span>
              </a>
              <span className="text-gray-300 dark:text-stone-600">·</span>
              <span>
                {t("auth.poweredBy")}{" "}
                <a
                  href="https://github.com/Yanyutin753/LambChat"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-serif text-gray-600 hover:text-gray-900 dark:text-stone-400 dark:hover:text-stone-200"
                >
                  LambChat
                </a>
              </span>
              <span className="text-gray-300 dark:text-stone-600">·</span>
              <span>{new Date().getFullYear()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
