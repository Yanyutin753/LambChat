/**
 * 登录/注册页面组件
 */

import { useState, useEffect, useRef, Fragment } from "react";
import { Link } from "react-router-dom";
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
import { APP_NAME, GITHUB_URL } from "../../constants";

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
  /** Force initial auth mode */
  initialMode?: AuthMode;
}

export function AuthPage({ onSuccess, initialMode }: AuthPageProps) {
  const { t } = useTranslation();

  // 覆盖全局 overflow: hidden，允许登录页面滚动
  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => {
      document.documentElement.classList.remove("allow-scroll");
    };
  }, []);

  const [mode, setMode] = useState<AuthMode>(initialMode ?? "login");
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
    setTurnstileKey((prev) => prev + 1);
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
    setTurnstileKey((prev) => prev + 1);
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
        onSuccess?.();
      } else {
        const result = await register(
          { username, email, password },
          turnstileToken || undefined,
        );
        if (result.requiresVerification) {
          // 注册成功，需要验证邮箱
          toast.success(t("auth.registerSuccessVerification"));
          // 跳转到验证等待页面
          window.location.href = `/auth/pending?email=${encodeURIComponent(
            result.email,
          )}`;
          return;
        }
        toast.success(t("auth.registerSuccess"));
        onSuccess?.();
      }
    } catch (err) {
      const errorMessage = (err as Error).message || t("auth.operationFailed");

      // 检查是否是邮箱未验证或账户未激活错误，跳转到验证页面
      if (
        errorMessage.includes("请先验证邮箱") ||
        errorMessage.includes("账户未激活")
      ) {
        // 如果输入的是邮箱，直接跳转
        const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username);
        if (isEmail) {
          toast.error(errorMessage);
          setTimeout(() => {
            window.location.href = `/auth/pending?email=${encodeURIComponent(
              username,
            )}`;
          }, 1500);
          return;
        }
        // 如果是用户名，提示用户
        setError(
          t("auth.pleaseLoginWithEmail") || "请使用注册邮箱登录以完成验证",
        );
        toast.error(errorMessage);
      } else {
        toast.error(errorMessage);
        setError(errorMessage);
      }

      // 重置 Turnstile widget
      setTurnstileToken(null);
      setTurnstileKey((prev) => prev + 1);
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
    <div className="auth-shell min-h-screen overflow-y-auto overflow-x-hidden">
      {/* 左上角 Logo */}
      <div className="fixed left-3 top-3 z-50 flex items-center gap-2 sm:left-4 sm:top-4">
        <Link
          to="/"
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/40 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60"
        >
          <img
            src="/icons/icon.svg"
            alt={APP_NAME}
            className="h-5 w-5 rounded-full"
          />
        </Link>
      </div>

      {/* 右上角按钮 */}
      <div className="fixed right-3 top-3 z-50 flex items-center gap-1.5 rounded-lg bg-white/40 p-1.5 shadow-sm transition-colors hover:bg-white/60 dark:bg-stone-800/40 dark:hover:bg-stone-800/60 sm:right-4 sm:top-4">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      {/* 主内容区域 - CSS Grid 实现居中且可滚动 */}
      <div className="grid min-h-screen place-items-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-md py-8">
          {/* Logo 和标题 */}
          <div className="mb-6 text-center sm:mb-8">
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 mb-2 tracking-tight font-serif sm:text-3xl">
              {APP_NAME}
            </h1>
            <p className="mt-1.5 text-sm text-stone-500 dark:text-stone-400 sm:mt-2">
              {mode === "login" ? t("auth.loginHint") : t("auth.registerHint")}
            </p>
          </div>

          {/* 表单卡片 */}
          <div className="auth-panel w-full rounded-2xl p-5 sm:p-8">
            {/* OAuth 登录按钮 - 放在最上面 */}
            {oauthProviders.length > 0 && (
              <div className="mb-4 sm:mb-6">
                {/* 横排 OAuth 按钮 */}
                <div className="flex items-center justify-center gap-2.5 sm:gap-3">
                  {oauthProviders.map((provider) => (
                    <Fragment key={provider.id}>
                      <button
                        type="button"
                        onClick={() => handleOAuthLogin(provider.id)}
                        className="flex items-center justify-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm font-medium text-stone-700 shadow-sm transition-all hover:-translate-y-0.5 hover:bg-stone-50 hover:shadow-md active:translate-y-0 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700 dark:hover:shadow-lg sm:gap-2.5 sm:px-4 sm:py-3"
                      >
                        {provider.id === "google" && (
                          <svg
                            className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5"
                            viewBox="0 0 48 48"
                          >
                            <path
                              fill="#EA4335"
                              d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                            />
                            <path
                              fill="#4285F4"
                              d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                            />
                            <path
                              fill="#FBBC05"
                              d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                            />
                            <path
                              fill="#34A853"
                              d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
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
                      </button>
                    </Fragment>
                  ))}
                </div>

                {/* 分隔线 */}
                <div className="relative mt-3 flex items-center sm:mt-4">
                  <div className="flex-grow border-t border-stone-200 dark:border-stone-700" />
                  <span className="flex-shrink-0 mx-3 text-[10px] font-medium uppercase tracking-widest text-stone-400 dark:text-stone-500 sm:mx-4 sm:text-xs">
                    {t("auth.or")}
                  </span>
                  <div className="flex-grow border-t border-stone-200 dark:border-stone-700" />
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
                <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.account")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
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
                    className="auth-input w-full rounded-xl py-2.5 pl-10 pr-3 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4"
                    placeholder={
                      mode === "login"
                        ? t("auth.usernameOrEmailPlaceholder")
                        : t("auth.usernamePlaceholder")
                    }
                    autoComplete="username"
                  />
                </div>
                {mode === "login" && (
                  <p className="mt-1 text-[10px] text-stone-400 dark:text-stone-500 sm:mt-1.5 sm:text-xs">
                    {t("auth.supportsUsernameOrEmailLogin")}
                  </p>
                )}
              </div>

              {/* 邮箱（仅注册） */}
              {mode === "register" && (
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
                      autoComplete="email"
                    />
                  </div>
                </div>
              )}

              {/* 密码 */}
              <div>
                <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                  {t("auth.password")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
                    <Lock size={16} className="sm:h-[18px] sm:w-[18px]" />
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="auth-input w-full rounded-xl py-2.5 pl-10 pr-3 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4"
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
                  <label className="mb-1 block text-xs font-medium text-stone-700 dark:text-stone-300 sm:mb-1.5 sm:text-sm">
                    {t("auth.confirmPassword")}
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
              )}

              {/* Turnstile 人机验证 */}
              {requiresTurnstile() && (
                <div className="auth-input mb-4 w-full rounded-xl p-3 sm:mb-6 sm:p-4">
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
                ) : mode === "login" ? (
                  t("auth.login")
                ) : (
                  t("auth.register")
                )}
              </button>
            </form>

            {/* 切换登录/注册 */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-1 text-xs text-stone-500 dark:text-stone-400 sm:mt-5 sm:text-sm">
              {registrationEnabled ? (
                <>
                  <span>
                    {mode === "login"
                      ? t("auth.noAccount")
                      : t("auth.hasAccount")}
                  </span>
                  <button
                    type="button"
                    onClick={switchMode}
                    className="font-medium text-stone-900 underline-offset-2 transition-all hover:text-stone-700 hover:underline dark:text-white dark:hover:text-stone-200"
                  >
                    {mode === "login"
                      ? t("auth.registerNow")
                      : t("auth.loginNow")}
                  </button>
                </>
              ) : (
                mode === "login" && (
                  <span className="text-stone-400 dark:text-stone-500">
                    {t("auth.registrationDisabled")}
                  </span>
                )
              )}
            </div>

            {/* 忘记密码链接 */}
            {mode === "login" && (
              <div className="mt-2 text-center">
                <Link
                  to="/auth/reset-request"
                  className="text-xs text-stone-500 transition-colors hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 sm:text-sm"
                >
                  {t("auth.forgotPassword")}
                </Link>
              </div>
            )}

            {/* 服务条款 */}
            <p className="mt-3 text-center text-[10px] text-stone-400 dark:text-stone-500 sm:mt-4 sm:text-xs">
              {t("auth.termsHint")}
            </p>

            {/* 页脚 */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-x-2 text-[10px] text-stone-400 dark:text-stone-500 sm:mt-6 sm:gap-x-3 sm:text-xs">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 transition-colors hover:text-stone-600 dark:hover:text-stone-300 sm:gap-1.5"
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
              <span className="text-stone-300 dark:text-stone-600">·</span>
              <span>
                {t("auth.poweredBy")}{" "}
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-serif text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-200"
                >
                  {APP_NAME}
                </a>
              </span>
              <span className="text-stone-300 dark:text-stone-600">·</span>
              <span>{new Date().getFullYear()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
