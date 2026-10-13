import { useTranslation } from "react-i18next";
import { BrandLogo } from "../common/BrandLogo";
import { BrandWordmark } from "../common/BrandWordmark";
import { LoadingSpinner } from "../common/LoadingSpinner";

/**
 * 全屏品牌过渡页：自动登录/跳转等待期的统一过渡（`/` 鉴权校验、OAuth 回调、
 * 登录成功跳转）。底色与 ChatPageSkeleton 一致，跳转后视觉无缝衔接。
 */
export function AutoLoginSplash({ text }: { text?: string }) {
  const { t } = useTranslation();

  return (
    <div
      className="auto-login-splash safe-area-viewport-padding"
      data-auto-login-splash=""
    >
      <div className="auto-login-splash-brand">
        <div className="auto-login-splash-logo">
          <BrandLogo className="size-10 sm:size-12" alt="LambChat" />
        </div>
        <BrandWordmark className="auto-login-splash-wordmark" width={148} />
        <p
          className="auto-login-splash-status"
          role="status"
          aria-live="polite"
        >
          <LoadingSpinner size="xs" color="text-theme-text-tertiary" />
          <span className="loading-label">
            {text ?? t("landing.autoLoginPending")}
          </span>
        </p>
      </div>
    </div>
  );
}
