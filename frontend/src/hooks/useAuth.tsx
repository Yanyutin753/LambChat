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
  type ReactNode,
} from "react";
import {
  authApi,
  getAccessToken,
  isAuthenticated,
  isTokenExpired,
  getRedirectPath,
  clearRedirectPath,
} from "../services/api";
import { Permission } from "../types";
import type { User, UserCreate, LoginRequest, AuthState } from "../types";

// 认证上下文类型
interface AuthContextType extends AuthState {
  login: (credentials: LoginRequest, turnstileToken?: string) => Promise<void>;
  register: (userData: UserCreate, turnstileToken?: string) => Promise<{ requiresVerification: boolean; email: string }>;
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
  // 存储从 API 获取的动态权限
  const [dynamicPermissions, setDynamicPermissions] = useState<Permission[]>(
    [],
  );

  // 权限列表：从 API 动态获取
  const permissions = dynamicPermissions;

  // 初始化：检查现有 token 并获取用户信息
  useEffect(() => {
    const initAuth = async () => {
      const accessToken = getAccessToken();

      if (!accessToken) {
        setIsLoading(false);
        return;
      }

      // 检查 token 是否过期
      if (isTokenExpired(accessToken)) {
        authApi.logout();
        setToken(null);
        setUser(null);
        setIsLoading(false);
        return;
      }

      setToken(accessToken);

      // 尝试获取用户信息
      try {
        const currentUser = await authApi.getCurrentUser();
        setUser(currentUser);
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
        setUser(null);
      }

      setIsLoading(false);
    };

    initAuth();
  }, []);

  // 监听登出事件
  useEffect(() => {
    const handleLogout = () => {
      setToken(null);
      setUser(null);
    };

    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  // 登录
  const login = useCallback(async (credentials: LoginRequest, turnstileToken?: string) => {
    setIsLoading(true);
    try {
      await authApi.login(credentials, turnstileToken);
      const accessToken = getAccessToken();
      setToken(accessToken);

      // 获取用户信息
      try {
        const currentUser = await authApi.getCurrentUser();
        setUser(currentUser);
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
        return;
      }

      // 登录成功后，跳转到之前的页面
      const redirectPath = getRedirectPath();
      if (redirectPath) {
        clearRedirectPath();
        window.location.href = redirectPath;
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 注册
  const register = useCallback(
    async (userData: UserCreate, turnstileToken?: string): Promise<{ requiresVerification: boolean; email: string }> => {
      setIsLoading(true);
      try {
        await authApi.register(userData, turnstileToken);
        // 不再自动登录，返回是否需要验证
        // 根据 REQUIRE_EMAIL_VERIFICATION 配置，用户可能需要先验证邮箱
        return {
          requiresVerification: true, // 注册成功后需要验证邮箱
          email: userData.email,
        };
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // OAuth 登录 - 重定向到 OAuth 提供商
  const loginWithOAuth = useCallback(async (provider: string) => {
    try {
      const { authorization_url } =
        await authApi.getOAuthAuthorizationUrl(provider);
      // 重定向到 OAuth 授权页面
      window.location.href = authorization_url;
    } catch (error) {
      console.error("OAuth login failed:", error);
      throw error;
    }
  }, []);

  // 处理 OAuth 回调
  const handleOAuthCallback = useCallback(
    async (provider: string, code: string, state: string) => {
      setIsLoading(true);
      try {
        await authApi.handleOAuthCallback(provider, code, state);
        const accessToken = getAccessToken();
        setToken(accessToken);

        // 获取用户信息
        try {
          const currentUser = await authApi.getCurrentUser();
          setUser(currentUser);
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
    authApi.logout();
    setToken(null);
    setUser(null);
  }, []);

  // 刷新用户信息（同时更新动态权限）
  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) return;

    try {
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
      // 更新动态权限
      if (currentUser.permissions) {
        setDynamicPermissions(
          currentUser.permissions.filter((p): p is Permission =>
            Object.values(Permission).includes(p as Permission),
          ),
        );
      }
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

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
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
