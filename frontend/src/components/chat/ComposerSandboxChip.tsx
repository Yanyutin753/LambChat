import { Cloud, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import type { AgentOption } from "../../types";
import { ToolbarChip } from "./ToolbarChip";
import { resolveSandboxPresentation } from "./sandboxOption";

export function ComposerSandboxChip({
  options,
  values,
  expanded = false,
  onClick,
}: {
  options?: Record<string, AgentOption>;
  values: Record<string, boolean | string | number>;
  expanded?: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  const { has, label: tierLabel } = resolveSandboxPresentation(
    options,
    values,
    t,
  );
  const tier = values.sandbox ?? options?.sandbox?.default;
  const local = tier === "local";
  const { online } = useSandboxStatus({ enabled: has && local });
  if (!has) return null;
  const label = tierLabel || "";
  return (
    <ToolbarChip
      icon={local ? <Monitor size={16} /> : <Cloud size={16} />}
      iconBadge={
        local ? (
          <span
            data-sandbox-status-dot
            title={t(
              online
                ? "profile.localSandbox.statusOnline"
                : "profile.localSandbox.statusOffline",
            )}
            className="absolute -bottom-0.5 -right-0.5 block size-1.5 rounded-full ring-2 ring-[var(--theme-bg-card)]"
            style={{
              background: online
                ? "var(--theme-success)"
                : "var(--theme-text-muted)",
            }}
          />
        ) : undefined
      }
      label={label}
      title={`${t("agentOptions.sandbox.label")} · ${label}`}
      labelClassName="composer-sandbox-label"
      expanded={expanded}
      onClick={onClick}
    />
  );
}
