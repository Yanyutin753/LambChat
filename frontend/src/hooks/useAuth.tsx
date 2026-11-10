/**
 * 认证上下文和 Hook
 * 提供全局认证状态管理
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  useLayoutEffect,
  type ReactNode,
} from "react";
import { authApi, buildOAuthLoginUrl } from "../services/api/auth";
import {
  getAccessToken,
  getRefreshToken,
  isAuthenticated,
  isTokenExpired,
  getRedirectPath,
  clearRedirectPath,
  decodeToken,
} from "../services/api/token";
import {
  applyUserMetadataPreferences,
  SIDEBAR_COLLAPSED_STORAGE_KEY,
} from "./userMetadataPreferences";
import { Permission } from "../types";
import type { User, UserCreate, LoginRequest, AuthState } from "../types";
import i18n from "../i18n";
import { WifiOff } from "lucide-react";
import { EmptyState } from "../components/common/EmptyState";
import { Button } from "../components/common/ui";

export { SIDEBAR_COLLAPSED_STORAGE_KEY };

/** Apply user metadata preferences from backend */
function applyUserMetadata(metadata?: User["metadata"]) {
  applyUserMetadataPreferences({
    metadata,
    localStorage,
    changeLanguage: (language) => {
      i18n.changeLanguage(language);
    },
    dispatchEvent: (event) => {
      window.dispatchEvent(event);
    },
  });
}

// 认证上下文类型
interface AuthContextType extends AuthState {
  login: (
    credentials: LoginRequest,
    turnstileToken?: string,
  ) => Promise<string | null>;
  register: (
    userData: UserCreate,
    turnstileToken?: string,
  ) => Promise<{ requiresVerification: boolean; email: string }>;
  loginWithOAuth: (provider: string) => Promise<void>;
  handleOAuthCallback: (
    provider: string,
    code: string,
    state: string,
  ) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasPermission: (permission: Permission) => boolean;
  hasAnyPermission: (permissions: Permission[]) => boolean;
  hasAllPermissions: (permissions: Permission[]) => boolean;
}

// 创建认证上下文
const AuthContext = createContext<AuthContextType | null>(null);

// Auth Provider 组件
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(getAccessToken());
  const [isLoading, setIsLoading] = useState(true);
  const [initializationFailed, setInitializationFailed] = useState(false);
  const [initializationAttempt, setInitializationAttempt] = useState(0);
  // 存储从 API 获取的动态权限
  const [dynamicPermissions, setDynamicPermissions] = useState<Permission[]>(
    [],
  );

  const refreshRequest = useRef(0);
  const currentUserId = useRef(user?.id);
  useLayoutEffect(() => {
    currentUserId.current = user?.id;
  }, [user?.id]);
  useEffect(
    () => () => {
      refreshRequest.current += 1;
    },
    [],
  );

  // 权限列表：从 API 动态获取
  const permissions = dynamicPermissions;

  // A temporary outage must not discard credentials or redirect to login.
  useEffect(() => {
    let active = true;
    const request = ++refreshRequest.current;
    const isCurrent = () => active && request === refreshRequest.current;
    const initAuth = async () => {
      setIsLoading(true);
      setInitializationFailed(false);
      const accessToken = getAccessToken();

      if (!accessToken) {
        setIsLoading(false);
        return;
      }

      let validToken = accessToken;

      // 检查 token 是否过期，尝试用 refresh token 刷新
      if (isTokenExpired(accessToken)) {
        const refreshToken = getRefreshToken();
        if (refreshToken && !isTokenExpired(refreshToken)) {
          try {
            const tokenResponse = await authApi.refreshToken();
            if (!isCurrent()) return;
            validToken = tokenResponse.access_token;
          } catch (error) {
            if (!isCurrent()) return;
            if ((error as Error & { status?: number })?.status === 401) {
              authApi.logout();
              setToken(null);
              setUser(null);
            } else {
              setInitializationFailed(true);
            }
            setIsLoading(false);
            return;
          }
        } else {
          // refresh token 也不存在或已过期，需要重新登录
          authApi.logout();
          setToken(null);
          setUser(null);
          setIsLoading(false);
          return;
        }
      }

      setToken(validToken);

      // 尝试获取用户信息（带重试）
      try {
        const currentUser = await authApi.getCurrentUser();
        if (!isCurrent()) return;
        setUser(currentUser);
        applyUserMetadata(currentUser.metadata);
        // 更新动态权限
        if (currentUser.permissions) {
          setDynamicPermissions(
            currentUser.permissions.filter((p): p is Permission =>
              Object.values(Permission).includes(p as Permission),
            ),
          );
        }
      } catch {
        if (!isCurrent()) return;
        // authFetch clears rejected credentials through auth:logout.
        if (getAccessToken()) setInitializationFailed(true);
      }

      setIsLoading(false);
    };

    initAuth();
    return () => {
      active = false;
    };
  }, [initializationAttempt]);

  // 监听登出事件
  useEffect(() => {
    const handleLogout = () => {
      refreshRequest.current += 1;
      setIsLoading(false);
      setInitializationFailed(false);
      setDynamicPermissions([]);
      setToken(null);
      setUser(null);
    };

    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  // 登录
  const login = useCallback(
    async (credentials: LoginRequest, turnstileToken?: string) => {
      refreshRequest.current += 1;
      setIsLoading(true);
      try {
        await authApi.login(credentials, turnstileToken);
        const accessToken = getAccessToken();
        setToken(accessToken);

        // 获取用户信息
        try {
          const currentUser = await authApi.getCurrentUser();
          setUser(currentUser);
          applyUserMetadata(currentUser.metadata);
          // 更新动态权限
          if (currentUser.permissions) {
            setDynamicPermissions(
              currentUser.permissions.filter((p): p is Permission =>
                Object.values(Permission).includes(p as Permission),
              ),
            );
          }
        } catch {
          // 获取用户信息失败，清除登录状态
          authApi.logout();
          setToken(null);
          setIsLoading(false);
          return null;
        }

        // 登录成功后，跳转到之前的页面
        const redirectPath = getRedirectPath();
        if (redirectPath) {
          clearRedirectPath();
        }
        return redirectPath ?? null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // 注册
  const register = useCallback(
    async (
      userData: UserCreate,
      turnstileToken?: string,
    ): Promise<{ requiresVerification: boolean; email: string }> => {
      setIsLoading(true);
      try {
        const response = await authApi.register(userData, turnstileToken);
        return {
          requiresVerification: response.requires_verification,
          email: userData.email,
        };
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // OAuth 登录 - 直接导航到后端 OAuth 端点，由服务端重定向到提供商
  const loginWithOAuth = useCallback(async (provider: string) => {
    window.location.href = buildOAuthLoginUrl(provider);
  }, []);

  // 处理 OAuth 回调
  const handleOAuthCallback = useCallback(
    async (provider: string, code: string, state: string) => {
      refreshRequest.current += 1;
      setIsLoading(true);
      try {
        await authApi.handleOAuthCallback(provider, code, state);
        const accessToken = getAccessToken();
        setToken(accessToken);

        // 获取用户信息
        try {
          const currentUser = await authApi.getCurrentUser();
          setUser(currentUser);
          applyUserMetadata(currentUser.metadata);
          // 更新动态权限
          if (currentUser.permissions) {
            setDynamicPermissions(
              currentUser.permissions.filter((p): p is Permission =>
                Object.values(Permission).includes(p as Permission),
              ),
            );
          }
        } catch {
          // 忽略用户信息获取失败
        }
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // 登出
  const logout = useCallback(() => {
    refreshRequest.current += 1;
    setDynamicPermissions([]);
    authApi.logout();
    setToken(null);
    setUser(null);
  }, []);

  // Refresh identity without replaying old cloud preferences over local edits.
  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) return;
    const accessToken = getAccessToken();
    if (!accessToken) return;
    const subject = decodeToken(accessToken)?.sub;
    const request = ++refreshRequest.current;
    try {
      const currentUser = await authApi.getCurrentUser();
      const latestToken = getAccessToken();
      if (
        request !== refreshRequest.current ||
        !latestToken ||
        (latestToken !== accessToken &&
          (typeof subject !== "string" ||
            decodeToken(latestToken)?.sub !== subject))
      )
        return;
      setToken(latestToken);
      setUser(currentUser);
      // OAuth's first refresh still restores the newly signed-in account.
      if (currentUserId.current !== currentUser.id)
        applyUserMetadata(currentUser.metadata);
      setDynamicPermissions(
        (currentUser.permissions ?? []).filter((p): p is Permission =>
          Object.values(Permission).includes(p as Permission),
        ),
      );
    } catch (error) {
      console.error("Failed to refresh user info:", error);
    }
  }, []);

  // 检查是否拥有某个权限
  const hasPermission = useCallback(
    (permission: Permission): boolean => {
      return permissions.includes(permission);
    },
    [permissions],
  );

  // 检查是否拥有任意一个权限
  const hasAnyPermission = useCallback(
    (perms: Permission[]): boolean => {
      return perms.some((p) => permissions.includes(p));
    },
    [permissions],
  );

  // 检查是否拥有所有权限
  const hasAllPermissions = useCallback(
    (perms: Permission[]): boolean => {
      return perms.every((p) => permissions.includes(p));
    },
    [permissions],
  );

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!token && !!user,
    isLoading,
    permissions,
    login,
    register,
    loginWithOAuth,
    handleOAuthCallback,
    logout,
    refreshUser,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
  };

  return (
    <AuthContext.Provider value={value}>
      {initializationFailed ? (
        <div
          role="alert"
          className="safe-area-viewport-padding flex min-h-[calc(100dvh-var(--titlebar-inset,0px))] items-center justify-center bg-theme-bg-primary p-6"
        >
          <EmptyState
            icon={<WifiOff size={20} />}
            title={i18n.t("backendErrors.serviceUnavailable")}
            action={
              <Button
                variant="primary"
                onClick={() =>
                  setInitializationAttempt((attempt) => attempt + 1)
                }
              >
                {i18n.t("common.retry")}
              </Button>
            }
          />
        </div>
      ) : (
        children
      )}
    </AuthContext.Provider>
  );
}

// useAuth Hook
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// 默认导出
// eslint-disable-next-line react-refresh/only-export-components
export default useAuth;
