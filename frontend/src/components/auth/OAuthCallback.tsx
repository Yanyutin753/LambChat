/**
 * OAuth 回调处理页面
 *
 * 处理 OAuth 提供商重定向回来的请求，从 URL fragment 中提取 token 并完成登录。
 */

import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import {
  setTokens,
  getRedirectPath,
  clearRedirectPath,
} from "../../services/api";
import { Loading } from "../common";

export function OAuthCallback() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { refreshUser } = useAuth();
  const processedRef = useRef(false);

  useEffect(() => {
    // 防止 React Strict Mode 双重调用
    if (processedRef.current) return;
    processedRef.current = true;

    const handleCallback = async () => {
      // 从 URL fragment 中提取 token (#access_token=xxx&refresh_token=xxx)
      const hash = window.location.hash.substring(1); // 移除开头的 #
      const params = new URLSearchParams(hash);

      const accessToken = params.get("access_token");
      const refreshToken = params.get("refresh_token");

      // 检查是否有错误参数（从 query 参数中获取）
      const error = searchParams.get("error");

      if (error) {
        console.error("OAuth callback error:", error);
        navigate(`/login?error=${error}`, { replace: true });
        return;
      }

      if (!accessToken || !refreshToken) {
        console.error("No tokens found in callback URL");
        navigate("/login?error=oauth_no_token", { replace: true });
        return;
      }

      try {
        // 保存 token
        setTokens(accessToken, refreshToken);

        // 刷新用户信息
        await refreshUser();

        // 获取重定向路径
        const redirectPath = getRedirectPath() || "/chat";
        clearRedirectPath();

        // 导航到目标页面
        navigate(redirectPath, { replace: true });
      } catch (err) {
        console.error("OAuth callback processing error:", err);
        navigate("/login?error=oauth_processing_failed", { replace: true });
      }
    };

    handleCallback();
  }, [navigate, refreshUser, searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-stone-900">
      <div className="text-center">
        <Loading size="lg" />
        <p className="mt-4 text-gray-600 dark:text-stone-400">
          {t("auth.completingLogin")}
        </p>
      </div>
    </div>
  );
}

export default OAuthCallback;
