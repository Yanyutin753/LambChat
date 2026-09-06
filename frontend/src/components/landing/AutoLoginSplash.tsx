import { useTranslation } from "react-i18next";
import { BrandLogo } from "../common/BrandLogo";
import { BrandWordmark } from "../common/BrandWordmark";

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
          <span className="auto-login-splash-logo-halo" aria-hidden="true" />
          <BrandLogo className="size-12 sm:size-14" alt="LambChat" />
        </div>
        <BrandWordmark className="auto-login-splash-wordmark" width={148} />
        <p
          className="auto-login-splash-status"
          role="status"
          aria-live="polite"
        >
          {text ?? t("landing.autoLoginPending")}
        </p>
        <div className="auto-login-splash-dots" aria-hidden="true">
          <span className="auto-login-splash-dot" />
          <span className="auto-login-splash-dot" />
          <span className="auto-login-splash-dot" />
        </div>
      </div>
    </div>
  );
}
