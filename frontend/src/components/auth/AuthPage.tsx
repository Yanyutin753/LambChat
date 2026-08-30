/**
 * 登录/注册页面组件
 */

import {
  useState,
  useEffect,
  useRef,
  Fragment,
  useMemo,
  useCallback,
  useId,
} from "react";
import { Link } from "react-router-dom";
import {
  User,
  Mail,
  AlertCircle,
  AtSign,
  Sparkles,
  ShieldCheck,
  Workflow,
  Database,
} from "lucide-react";
import { PasswordInput } from "./PasswordInput";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Turnstile } from "react-turnstile";
import { useAuth } from "../../hooks/useAuth";
import { useMobileKeyboardAware } from "../../hooks/useMobileKeyboardAware";
import { useTheme } from "../../contexts/ThemeContext";
import { Loading, LoadingSpinner } from "../common/LoadingSpinner";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { BrandWordmark } from "../common/BrandWordmark";
import { BrandLogo } from "../common/BrandLogo";
import { authApi } from "../../services/api";
import { APP_NAME, GITHUB_URL } from "../../constants";
import {
  AUTH_REDIRECT_ANIMATION_MS,
  AUTH_REDIRECT_FAILSAFE_MS,
  resolvePostAuthRedirectPath,
} from "./authRedirectTransition";

const CURRENT_YEAR = new Date().getFullYear();

type AuthMode = "login" | "register";

interface TurnstileConfig {
  enabled: boolean;
  site_key: string;
  require_on_login: boolean;
  require_on_register: boolean;
  require_on_password_change: boolean;
}

interface AuthPageProps {
  onSuccess?: (redirectPath?: string) => void;
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
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [contactAdminOpen, setContactAdminOpen] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileKey, setTurnstileKey] = useState(0); // 用于强制重新渲染 Turnstile
  const { theme } = useTheme();
  const isKeyboardOpen = useMobileKeyboardAware();
  const { login, register, loginWithOAuth } = useAuth();
  const authId = useId();
  const accountInputId = `${authId}-account`;
  const emailInputId = `${authId}-email`;
  const passwordInputId = `${authId}-password`;
  const confirmPasswordInputId = `${authId}-confirm-password`;

  // 当主题变化时，强制重新渲染 Turnstile 以更新主题
  useEffect(() => {
    setTurnstileKey((prev) => prev + 1);
  }, [theme]);

  // Memoize submit label to avoid recalculating on unrelated renders
  const submitLabel = useMemo(
    () => (mode === "login" ? t("auth.login") : t("auth.register")),
    [mode, t],
  );

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

  // Memoize Turnstile requirement check
  const showTurnstile = useMemo(() => {
    if (!turnstileConfig.enabled || !turnstileConfig.site_key) return false;
    if (mode === "login") return turnstileConfig.require_on_login;
    if (mode === "register") return turnstileConfig.require_on_register;
    return false;
  }, [
    turnstileConfig.enabled,
    turnstileConfig.site_key,
    turnstileConfig.require_on_login,
    turnstileConfig.require_on_register,
    mode,
  ]);

  // Use ref to access current mode without adding it to deps
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const characterPanelRef = useRef<HTMLDivElement | null>(null);
  const redirectTimerRef = useRef<number | null>(null);
  const redirectFailsafeRef = useRef<number | null>(null);

  const clearRedirectTimers = useCallback(() => {
    if (redirectTimerRef.current !== null) {
      window.clearTimeout(redirectTimerRef.current);
      redirectTimerRef.current = null;
    }
    if (redirectFailsafeRef.current !== null) {
      window.clearTimeout(redirectFailsafeRef.current);
      redirectFailsafeRef.current = null;
    }
  }, []);

  useEffect(() => clearRedirectTimers, [clearRedirectTimers]);

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

  // 重置 Turnstile token 当模式切换时
  useEffect(() => {
    setTurnstileToken(null);
    // 通过改变 key 强制重新渲染 Turnstile
    setTurnstileKey((prev) => prev + 1);
  }, [mode]);

  // OAuth 登录处理
  const handleOAuthLogin = useCallback(
    async (provider: string) => {
      try {
        await loginWithOAuth(provider);
      } catch {
        toast.error(t("auth.oauthLoginFailed"));
      }
    },
    [loginWithOAuth, t],
  );

  const beginSuccessRedirect = useCallback(
    (redirectPath?: string | null) => {
      const nextPath = resolvePostAuthRedirectPath(redirectPath);
      clearRedirectTimers();
      setIsRedirecting(true);

      redirectFailsafeRef.current = window.setTimeout(() => {
        setIsRedirecting(false);
        setIsSubmitting(false);
      }, AUTH_REDIRECT_FAILSAFE_MS);

      redirectTimerRef.current = window.setTimeout(() => {
        try {
          onSuccess?.(nextPath);
        } catch (err) {
          console.error("[AuthPage] Failed to redirect after login:", err);
          setIsRedirecting(false);
          setIsSubmitting(false);
        }
      }, AUTH_REDIRECT_ANIMATION_MS);
    },
    [onSuccess, clearRedirectTimers],
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
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
      if (showTurnstile && !turnstileToken) {
        setError(t("auth.turnstileRequired"));
        return;
      }

      setIsSubmitting(true);
      let startedRedirect = false;

      try {
        if (mode === "login") {
          const redirectPath = await login(
            { username, password },
            turnstileToken || undefined,
          );
          toast.success(t("auth.loginSuccess"));
          startedRedirect = true;
          beginSuccessRedirect(redirectPath);
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
          startedRedirect = true;
          beginSuccessRedirect();
        }
      } catch (err) {
        const errorMessage =
          (err as Error).message || t("auth.operationFailed");

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
          setError(t("auth.pleaseLoginWithEmail"));
          toast.error(errorMessage);
        } else {
          toast.error(errorMessage);
          setError(errorMessage);
        }

        // 重置 Turnstile widget
        setTurnstileToken(null);
        setTurnstileKey((prev) => prev + 1);
      } finally {
        if (!startedRedirect) {
          setIsSubmitting(false);
        }
      }
    },
    [
      mode,
      t,
      username,
      password,
      email,
      confirmPassword,
      login,
      register,
      showTurnstile,
      turnstileToken,
      beginSuccessRedirect,
    ],
  );

  const switchMode = useCallback(() => {
    // 如果注册已禁用，不允许切换到注册模式
    if (mode === "login" && !registrationEnabled) {
      return;
    }
    setMode(mode === "login" ? "register" : "login");
    setError(null);
    setEmail("");
    setConfirmPassword("");
  }, [mode, registrationEnabled]);

  // RAF-throttled character gaze: buffers pointer events and applies CSS
  // custom properties only once per animation frame.
  const rafRef = useRef<number>(0);
  const pendingGazeRef = useRef({ x: 0, y: 0 });

  const applyCharacterGaze = useCallback(() => {
    const panel = characterPanelRef.current;
    if (!panel) return;
    const { x, y } = pendingGazeRef.current;
    panel.style.setProperty("--eye-x", `${(x * 10).toFixed(2)}px`);
    panel.style.setProperty("--eye-y", `${(y * 5).toFixed(2)}px`);
    panel.style.setProperty("--pupil-x", `${(x * 3.5).toFixed(2)}px`);
    panel.style.setProperty("--pupil-y", `${(y * 2.5).toFixed(2)}px`);
    panel.style.setProperty("--mouth-x", `${(x * 4).toFixed(2)}px`);
    panel.style.setProperty("--mouth-y", `${(y * 2).toFixed(2)}px`);
    panel.style.setProperty("--mouth-rotate", `${(x * 2).toFixed(2)}deg`);
    rafRef.current = 0;
  }, []);

  const setCharacterGaze = useCallback(
    (xRatio: number, yRatio: number) => {
      pendingGazeRef.current = { x: xRatio, y: yRatio };
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(applyCharacterGaze);
      }
    },
    [applyCharacterGaze],
  );

  const resetCharacterGaze = useCallback(() => {
    pendingGazeRef.current = { x: 0, y: 0 };
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(applyCharacterGaze);
    }
  }, [applyCharacterGaze]);

  const handleGlobalCharacterPointerMove = useCallback(
    (event: PointerEvent) => {
      const viewportWidth = Math.max(window.innerWidth, 1);
      const viewportHeight = Math.max(window.innerHeight, 1);
      const xRatio = Math.max(
        -1,
        Math.min(1, (event.clientX / viewportWidth - 0.5) * 2.4),
      );
      const yRatio = Math.max(
        -1,
        Math.min(1, (event.clientY / viewportHeight - 0.5) * 2.2),
      );
      setCharacterGaze(xRatio, yRatio);
    },
    [setCharacterGaze],
  );

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return undefined;
    }
    window.addEventListener("pointermove", handleGlobalCharacterPointerMove, {
      passive: true,
    });
    window.addEventListener("pointerleave", resetCharacterGaze);
    window.addEventListener("blur", resetCharacterGaze);
    return () => {
      window.removeEventListener(
        "pointermove",
        handleGlobalCharacterPointerMove,
      );
      window.removeEventListener("pointerleave", resetCharacterGaze);
      window.removeEventListener("blur", resetCharacterGaze);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [handleGlobalCharacterPointerMove, resetCharacterGaze]);

  if (isRedirecting) {
    return (
      <div className="auth-shell safe-area-top safe-area-bottom flex min-h-screen items-center justify-center">
        <div className="text-center">
          <Loading size="lg" className="justify-center" />
          <p className="mt-4 text-stone-600 dark:text-stone-400">
            {t("auth.completingLogin")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell auth-lamb-shell min-h-[100svh] min-h-[100dvh] overflow-y-auto overflow-x-hidden">
      <div className="auth-crosshatch" aria-hidden="true" />
      <div className="auth-lamb-pattern" aria-hidden="true" />

      {/* Atmospheric background with aurora glow orbs */}
      <div className="auth-atmosphere" aria-hidden="true">
        <div className="auth-glow-main absolute -top-24 left-1/2 -translate-x-1/2 w-[720px] h-[520px] bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.065)_0%,rgba(251,146,60,0.025)_42%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.04)_0%,rgba(251,146,60,0.018)_42%,transparent_70%)]" />
        <div className="auth-glow-blue absolute top-[34%] left-[4%] w-[360px] h-[360px] bg-[radial-gradient(circle,rgba(56,189,248,0.04)_0%,transparent_62%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.028)_0%,transparent_62%)]" />
        <div className="auth-glow-violet absolute bottom-[10%] right-[8%] w-[300px] h-[300px] bg-[radial-gradient(circle,rgba(168,85,247,0.035)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.022)_0%,transparent_60%)]" />
        {/* Floating light orbs */}
        <div className="auth-light-orb auth-light-orb-amber absolute top-[18%] left-[6%] opacity-50" />
        <div className="auth-light-orb auth-light-orb-blue absolute top-[52%] right-[4%] opacity-35" />
        <div className="auth-light-orb auth-light-orb-violet absolute bottom-[18%] left-[28%] opacity-25" />
      </div>

      {/* Mobile navbar */}
      <nav className="safe-area-top fixed top-0 inset-x-0 z-50 bg-white/90 dark:bg-stone-950/90 border-b border-stone-100/60 dark:border-stone-800/40 transition-shadow duration-300 lg:hidden">
        <div className="mx-auto flex h-16 max-w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" className="flex items-center group  gap-1.5">
            <BrandLogo
              alt={APP_NAME}
              className="h-8 transition-transform duration-300 group-hover:scale-105"
            />
            <BrandWordmark
              decorative
              className="h-8 w-auto text-slate-900 dark:text-stone-100"
            />
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
      </nav>

      {/* Main content */}
      <div
        className={`relative z-10 flex min-h-[100svh] min-h-[100dvh] justify-center lg:justify-stretch ${
          isKeyboardOpen
            ? "items-start px-4 pt-[calc(4rem+var(--app-safe-area-top,0px))] sm:px-6 sm:pt-[calc(5rem+var(--app-safe-area-top,0px))] lg:px-0 lg:pt-0"
            : "items-center px-4 pt-[calc(5.5rem+var(--app-safe-area-top,0px))] pb-[calc(4.5rem+var(--app-safe-area-bottom,0px))] sm:px-6 sm:pt-[calc(6rem+var(--app-safe-area-top,0px))] sm:pb-[calc(5rem+var(--app-safe-area-bottom,0px))] lg:px-0 lg:py-0"
        }`}
      >
        <div className="grid w-full max-w-[980px] items-center gap-8 lg:min-h-[100svh] lg:max-w-none lg:grid-cols-2 lg:gap-0">
          <div
            ref={characterPanelRef}
            className="auth-illustration-panel hidden lg:flex"
          >
            <Link to="/" className="auth-illustration-brand">
              <BrandLogo alt={APP_NAME} className="h-8" />
              <BrandWordmark
                decorative
                className="auth-illustration-wordmark h-8 w-auto"
              />
            </Link>

            <div className="auth-character-stage" aria-hidden="true">
              <span className="auth-lamb-feature-chip auth-lamb-feature-chip-agents font-serif">
                <Workflow size={13} />
                {t("auth.featureAgents")}
              </span>
              <span className="auth-lamb-feature-chip auth-lamb-feature-chip-tools">
                <ShieldCheck size={13} />
                {t("auth.featureTools")}
              </span>
              <span className="auth-lamb-feature-chip auth-lamb-feature-chip-skills">
                <Sparkles size={13} />
                {t("auth.featureSkills")}
              </span>
              <span className="auth-lamb-feature-chip auth-lamb-feature-chip-memory">
                <Database size={13} />
                {t("auth.featureMemory")}
              </span>
              <div className="auth-character auth-character-purple">
                <span className="auth-character-antenna auth-character-antenna-left" />
                <span className="auth-character-antenna auth-character-antenna-right" />
                <span className="auth-character-eye auth-character-eye-left" />
                <span className="auth-character-eye auth-character-eye-right" />
                <span className="auth-character-mouth" />
              </div>
              <div className="auth-character auth-character-black">
                <span className="auth-character-antenna auth-character-antenna-left" />
                <span className="auth-character-antenna auth-character-antenna-right" />
                <span className="auth-character-eye auth-character-eye-left" />
                <span className="auth-character-eye auth-character-eye-right" />
                <span className="auth-character-mouth" />
              </div>
              <div className="auth-character auth-character-orange">
                <span className="auth-character-eye auth-character-eye-left" />
                <span className="auth-character-eye auth-character-eye-right" />
                <span className="auth-character-cheek auth-character-cheek-left" />
                <span className="auth-character-cheek auth-character-cheek-right" />
                <span className="auth-character-mouth" />
              </div>
              <div className="auth-character auth-character-yellow">
                <span className="auth-character-eye auth-character-eye-left" />
                <span className="auth-character-eye auth-character-eye-right" />
                <span className="auth-character-cheek auth-character-cheek-left" />
                <span className="auth-character-cheek auth-character-cheek-right" />
                <span className="auth-character-mouth" />
              </div>
            </div>

            <div className="auth-illustration-links">
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                {t("auth.privacyPolicy")}
              </a>
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                {t("auth.termsOfService")}
              </a>
            </div>
          </div>

          <div className="auth-form-side relative flex w-full justify-center lg:min-h-[100svh] lg:items-center">
            <div className="absolute right-6 top-6 hidden items-center gap-1.5 lg:flex">
              <LanguageToggle />
              <ThemeToggle />
            </div>
            <div className="auth-form-frame w-full max-w-[23.5rem] sm:max-w-[420px] lg:max-w-[520px]">
              <div className="auth-mobile-spirit lg:hidden" aria-hidden="true">
                <span className="auth-mobile-orbit" />
                <span className="auth-mobile-spark auth-mobile-spark-one" />
                <span className="auth-mobile-spark auth-mobile-spark-two" />
                <span className="auth-mobile-character auth-mobile-character-tall">
                  <span className="auth-mobile-eye auth-mobile-eye-left" />
                  <span className="auth-mobile-eye auth-mobile-eye-right" />
                  <span className="auth-mobile-smile" />
                </span>
                <span className="auth-mobile-character auth-mobile-character-wide">
                  <span className="auth-mobile-eye auth-mobile-eye-left" />
                  <span className="auth-mobile-eye auth-mobile-eye-right" />
                  <span className="auth-mobile-smile" />
                </span>
                <span className="auth-mobile-character auth-mobile-character-round">
                  <span className="auth-mobile-eye auth-mobile-eye-left" />
                  <span className="auth-mobile-eye auth-mobile-eye-right" />
                  <span className="auth-mobile-smile" />
                </span>
              </div>
              {/* Form surface */}
              <div className="auth-form-surface">
                <div className="auth-form-heading mb-7 text-center sm:mb-9">
                  <h1 className="mb-1.5 text-[1.75rem] font-bold tracking-tight text-slate-950 sm:text-3xl dark:text-stone-50 font-serif">
                    {mode === "login"
                      ? t("auth.welcomeBack")
                      : t("auth.register")}
                  </h1>
                  <p className="text-sm leading-relaxed text-slate-500 dark:text-stone-400 font-serif">
                    {mode === "login"
                      ? t("auth.loginHint")
                      : t("auth.registerHint")}
                  </p>
                </div>

                <form
                  onSubmit={handleSubmit}
                  key={mode}
                  className="auth-form-animate space-y-4"
                >
                  {/* Error */}
                  {error && (
                    <div>
                      <div className="flex items-center gap-2 rounded-full border border-red-200/60 bg-red-50/80 px-4 py-2 text-xs text-red-600 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-400">
                        <AlertCircle size={14} className="flex-shrink-0" />
                        <span>{error}</span>
                      </div>
                      {(error.includes("邮箱") ||
                        error.includes("激活") ||
                        error.includes("verify") ||
                        error.includes("activate")) && (
                        <button
                          onClick={() => setContactAdminOpen(true)}
                          className="mt-1.5 text-xs text-stone-400 transition-colors hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
                        >
                          {t("contactAdmin.supportLink")}
                        </button>
                      )}
                    </div>
                  )}

                  {/* Account input */}
                  <div className="auth-field-group">
                    <label
                      htmlFor={accountInputId}
                      className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-stone-300 font-serif"
                    >
                      {mode === "login"
                        ? t("auth.emailOrUsername")
                        : t("auth.account")}
                    </label>
                    <div className="relative">
                      <div className="auth-field-icon pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400 dark:text-stone-500">
                        {mode === "login" ? (
                          <AtSign size={15} />
                        ) : (
                          <User size={15} />
                        )}
                      </div>
                      <input
                        id={accountInputId}
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="auth-input w-full rounded-full py-3 pl-11 pr-4 text-sm transition-all"
                        placeholder={
                          mode === "login"
                            ? t("auth.usernameOrEmailPlaceholder")
                            : t("auth.usernamePlaceholder")
                        }
                        autoComplete="username"
                      />
                    </div>
                  </div>

                  {/* Email (register only) */}
                  {mode === "register" && (
                    <div className="auth-field-group">
                      <label
                        htmlFor={emailInputId}
                        className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-stone-300 font-serif"
                      >
                        {t("auth.email")}
                      </label>
                      <div className="relative">
                        <div className="auth-field-icon pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400 dark:text-stone-500">
                          <Mail size={15} />
                        </div>
                        <input
                          id={emailInputId}
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          className="auth-input w-full rounded-full py-3 pl-11 pr-4 text-sm transition-all"
                          placeholder={t("auth.emailPlaceholder")}
                          autoComplete="email"
                        />
                      </div>
                    </div>
                  )}

                  {/* Password */}
                  <div className="auth-field-group">
                    <label
                      htmlFor={passwordInputId}
                      className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-stone-300 font-serif"
                    >
                      {t("auth.password")}
                    </label>
                    <PasswordInput
                      id={passwordInputId}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={t("auth.passwordPlaceholder")}
                      className="rounded-full py-3"
                      autoComplete={
                        mode === "login" ? "current-password" : "new-password"
                      }
                      showPasswordLabel={t("auth.showPassword")}
                      hidePasswordLabel={t("auth.hidePassword")}
                    />
                  </div>

                  {/* Confirm password (register only) */}
                  {mode === "register" && (
                    <div className="auth-field-group">
                      <label
                        htmlFor={confirmPasswordInputId}
                        className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-stone-300 font-serif"
                      >
                        {t("auth.confirmPassword")}
                      </label>
                      <PasswordInput
                        id={confirmPasswordInputId}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder={t("auth.confirmPasswordPlaceholder")}
                        className="rounded-full py-3"
                        autoComplete="new-password"
                        showPasswordLabel={t("auth.showPassword")}
                        hidePasswordLabel={t("auth.hidePassword")}
                      />
                    </div>
                  )}

                  {mode === "login" && (
                    <div className="auth-forgot-row flex justify-end text-sm">
                      <Link
                        to="/auth/reset-request"
                        className="shrink-0 font-medium text-slate-500 transition-colors duration-200 hover:text-slate-700 hover:underline underline-offset-4 dark:text-stone-400 dark:hover:text-stone-200 font-serif"
                      >
                        {t("auth.forgotPassword")}
                      </Link>
                    </div>
                  )}

                  {/* Turnstile */}
                  {showTurnstile && (
                    <div className="flex justify-center overflow-hidden">
                      <div className="max-w-[300px] w-full">
                        <Turnstile
                          key={turnstileKey}
                          sitekey={turnstileConfig.site_key}
                          onSuccess={(token) => setTurnstileToken(token)}
                          onError={() => {
                            setTurnstileToken(null);
                            setError(t("auth.turnstileError"));
                          }}
                          onExpire={() => setTurnstileToken(null)}
                          theme={theme === "dark" ? "dark" : "light"}
                        />
                      </div>
                    </div>
                  )}

                  {/* Submit button */}
                  <button
                    type="submit"
                    disabled={isSubmitting || isRedirecting}
                    className="auth-primary-button mt-1 min-h-12 w-full rounded-full py-3 text-base font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50 font-serif"
                  >
                    <span className="inline-flex items-center justify-center gap-2">
                      {isSubmitting && (
                        <LoadingSpinner
                          size="sm"
                          className="text-white dark:text-stone-900"
                        />
                      )}
                      <span className="auth-submit-label">{submitLabel}</span>
                    </span>
                  </button>
                </form>

                {/* OAuth buttons */}
                {oauthProviders.length > 0 && (
                  <div className="mt-5">
                    <div className="auth-divider-ornament mb-4">
                      <span className="flex-shrink-0 text-xs font-medium text-slate-400 dark:text-stone-500">
                        {t("auth.or")}
                      </span>
                    </div>
                    <div className="grid gap-2">
                      {oauthProviders.map((provider) => (
                        <Fragment key={provider.id}>
                          <button
                            type="button"
                            onClick={() => handleOAuthLogin(provider.id)}
                            className="auth-oauth-btn auth-social-provider flex h-12 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold text-slate-900 transition-all active:translate-y-0 dark:text-stone-100 font-serif"
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
                            <span>
                              {t("auth.loginWith", {
                                provider:
                                  provider.id === "google"
                                    ? "Google"
                                    : provider.name,
                              })}
                            </span>
                          </button>
                        </Fragment>
                      ))}
                    </div>
                  </div>
                )}

                {/* Switch mode */}
                <div className="auth-mode-switch mt-6 flex flex-wrap items-center justify-center gap-1.5 text-sm text-slate-500 dark:text-stone-400 font-serif">
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
                        className="font-medium text-stone-900 underline-offset-4 transition-all duration-200 hover:text-stone-700 hover:underline dark:text-white dark:hover:text-stone-200 font-serif"
                      >
                        {mode === "login"
                          ? t("auth.registerNow")
                          : t("auth.loginNow")}
                      </button>
                    </>
                  ) : (
                    mode === "login" && (
                      <span>{t("auth.registrationDisabled")}</span>
                    )
                  )}
                </div>
                {/* Terms spacer */}
                {mode === "login" && <div className="mt-4" />}
              </div>

              {/* Footer - content-visibility: auto defers rendering until visible */}
              <div
                className="auth-footer-enter safe-area-bottom mt-5 flex flex-col items-center gap-3 sm:mt-7 sm:gap-4 lg:hidden"
                style={{
                  contentVisibility: "auto",
                  containIntrinsicSize: "0 80px",
                }}
              >
                <div
                  className="auth-footer-divider w-32 sm:w-40"
                  aria-hidden="true"
                />
                <div className="flex flex-wrap items-center justify-center gap-x-2 text-10 text-stone-400 dark:text-stone-500 sm:gap-x-3 sm:text-xs font-serif">
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
                  <span className="text-stone-600 dark:text-stone-400 font-serif transition-colors">
                    {t("auth.poweredBy")}{" "}
                    <a
                      href={GITHUB_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-stone-900 dark:hover:text-stone-200 font-serif transition-colors"
                    >
                      {APP_NAME}
                    </a>
                  </span>
                  <span className="text-stone-300 dark:text-stone-600">·</span>
                  <span>{CURRENT_YEAR}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ContactAdminDialog
        isOpen={contactAdminOpen}
        onClose={() => setContactAdminOpen(false)}
        reason="emailActivation"
      />
    </div>
  );
}

export default AuthPage;
