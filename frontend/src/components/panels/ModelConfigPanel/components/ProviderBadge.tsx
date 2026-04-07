/**
 * Provider icon badge with provider-specific brand color
 */
import { getProviderMeta } from "../../../../types/model";
import {
  getProviderIconUrl,
  isMonochromeProvider,
} from "../../../agent/modelIcon";

export function ProviderBadge({
  provider,
  size = "md",
}: {
  provider: string;
  size?: "sm" | "md" | "lg";
}) {
  const meta = getProviderMeta(provider);
  const color = meta?.color || "#78716c";
  const iconUrl = getProviderIconUrl(provider);
  const mono = isMonochromeProvider(provider);
  const sizeClasses = {
    sm: "w-8 h-8 text-xs",
    md: "w-10 h-10 text-sm",
    lg: "w-12 h-12 text-base",
  };
  const imageSizes = {
    sm: 18,
    md: 22,
    lg: 26,
  };

  return (
    <div
      className={`flex items-center justify-center rounded-xl font-bold flex-shrink-0 overflow-hidden ${sizeClasses[size]}`}
      style={{
        background: iconUrl
          ? "var(--model-surface-elevated, var(--theme-bg-card))"
          : color,
        boxShadow: iconUrl
          ? `0 8px 18px -16px ${color}55`
          : `0 8px 18px -14px ${color}30`,
        border: iconUrl
          ? "1px solid color-mix(in srgb, var(--theme-border) 82%, transparent)"
          : "none",
      }}
    >
      {iconUrl ? (
        <img
          src={iconUrl}
          alt={meta?.display_name || provider}
          width={imageSizes[size]}
          height={imageSizes[size]}
          className={mono ? "dark:invert" : ""}
        />
      ) : (
        <span className="text-white">{provider.charAt(0).toUpperCase()}</span>
      )}
    </div>
  );
}
