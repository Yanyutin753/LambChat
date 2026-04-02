/**
 * 受保护路由组件
 * 用于需要认证的页面
 */

import { type ReactNode, useEffect } from "react";
import { Navigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";

interface ProtectedRouteProps {
  children: ReactNode;
  /** 需要的权限（任意一个即可） */
  permissions?: Permission[];
  /** 需要全部满足的权限 */
  requireAllPermissions?: Permission[];
  /** 是否需要管理员权限 */
  requireAdmin?: boolean;
  /** 加载中显示的组件 */
  loadingComponent?: ReactNode;
  /** 无权限时显示的组件 */
  fallbackComponent?: ReactNode;
  /** 无权限时重定向的路径（与 fallbackComponent 互斥，优先使用） */
  redirectTo?: string;
  /** 无权限时是否显示 Toast 提示 */
  showToast?: boolean;
  /** Toast 提示消息 */
  toastMessage?: string;
}

// 加载动画组件 - ChatGPT 风格
function LoadingSpinner() {
  const { t } = useTranslation();
  return (
    <div className="auth-shell flex min-h-screen">
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="flex items-center justify-center gap-1.5 mb-6">
            <span
              className="h-3 w-3 rounded-full bg-[var(--theme-primary)]"
              style={{
                animation: "bounce 1.4s ease-in-out infinite both",
                animationDelay: "-0.32s",
              }}
            />
            <span
              className="h-3 w-3 rounded-full bg-[var(--theme-primary)]"
              style={{
                animation: "bounce 1.4s ease-in-out infinite both",
                animationDelay: "-0.16s",
              }}
            />
            <span
              className="h-3 w-3 rounded-full bg-[var(--theme-primary)]"
              style={{
                animation: "bounce 1.4s ease-in-out infinite both",
                animationDelay: "0s",
              }}
            />
          </div>
          <p className="text-[var(--theme-text-secondary)] text-sm font-medium tracking-wide">
            {t("common.loading")}
          </p>
        </div>
        <style>{`
          @keyframes bounce {
            0%, 80%, 100% {
              transform: scale(0.6);
              opacity: 0.4;
            }
            40% {
              transform: scale(1);
              opacity: 1;
            }
          }
        `}</style>
      </div>
    </div>
  );
}

// 无权限提示组件
function NoPermission() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50 dark:bg-stone-900">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
          <svg
            className="h-8 w-8 text-red-500 dark:text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h2 className="mb-2 text-xl font-semibold text-stone-900 dark:text-stone-100">
          {t("errors.noPermissionTitle")}
        </h2>
        <p className="text-stone-500 dark:text-stone-400">
          {t("errors.noPermission")}
        </p>
      </div>
    </div>
  );
}

export function ProtectedRoute({
  children,
  permissions,
  requireAllPermissions,
  requireAdmin,
  loadingComponent,
  fallbackComponent,
  redirectTo,
  showToast = false,
  toastMessage = "您没有权限访问此页面",
}: ProtectedRouteProps) {
  const {
    isAuthenticated,
    isLoading,
    hasAnyPermission,
    hasAllPermissions,
  } = useAuth();

  // 检查是否有访问权限
  const checkAccess = (): boolean => {
    // 检查管理员权限
    if (requireAdmin) {
      const adminPermissions = [
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.ROLE_MANAGE,
      ];
      if (!hasAnyPermission(adminPermissions)) {
        return false;
      }
    }

    // 检查需要全部满足的权限
    if (requireAllPermissions && requireAllPermissions.length > 0) {
      if (!hasAllPermissions(requireAllPermissions)) {
        return false;
      }
    }

    // 检查需要任意满足的权限
    if (permissions && permissions.length > 0) {
      if (!hasAnyPermission(permissions)) {
        return false;
      }
    }

    return true;
  };

  const hasAccess = checkAccess();

  // 无权限时的处理：显示 Toast
  useEffect(() => {
    if (!isLoading && isAuthenticated && !hasAccess && showToast) {
      toast.error(toastMessage);
    }
  }, [isLoading, isAuthenticated, hasAccess, showToast, toastMessage]);

  // 加载中
  if (isLoading) {
    return <>{loadingComponent || <LoadingSpinner />}</>;
  }

  // 未登录 → 重定向到登录页
  if (!isAuthenticated) {
    return <Navigate to="/auth/login" replace />;
  }

  // 无权限
  if (!hasAccess) {
    // 优先使用重定向
    if (redirectTo) {
      return <Navigate to={redirectTo} replace />;
    }
    // 否则显示 fallback 组件或默认无权限页面
    return <>{fallbackComponent || <NoPermission />}</>;
  }

  return <>{children}</>;
}

export default ProtectedRoute;
