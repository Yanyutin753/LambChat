import { useCallback, useEffect, useMemo } from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  Ban,
  ChevronRight,
  Loader2,
  Bot,
} from "lucide-react";
import { getFluentEmojiCDN } from "@lobehub/fluent-emoji";
import { useTranslation } from "react-i18next";
import { hasOpenRightPanel } from "../../common/rightPanelCoordinator";
import {
  getRightPanelPresentation,
  shouldAllowAutomaticRightPanel,
} from "../../../hooks/rightPanelLayout";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { PersonaAvatarIcon } from "../../persona/PersonaAvatarIcon";
import type { MessagePart } from "../../../types";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore";
import {
  dismissSubagentPanelAutoOpen,
  hasSubagentPanelAutoOpened,
  isSubagentPanelAutoOpenDismissed,
  markSubagentPanelAutoOpened,
  resetSubagentPanelAutoOpenState,
  shouldAutoOpenSubagentPanel,
} from "./subagentPanelControl";
import { buildSubagentPanelState } from "./subagentPanelState";
import {
  getSubagentAvatarImageUrl,
  getSubagentRoleIconMeta,
} from "./subagentRoleMeta";
import { DeferredSubagentPanelContent } from "./DeferredSubagentPanelContent";

function SubagentStatusIcon({
  status,
  className,
  size = 13,
}: {
  status: SubagentPanelData["status"] | "pending" | undefined;
  className?: string;
  size?: number;
}) {
  if (status === "running") {
    return (
      <Loader2
        size={size}
        className={clsx(
          "text-amber-500 dark:text-amber-400 animate-spin",
          className,
        )}
      />
    );
  }
  if (status === "complete") {
    return (
      <CheckCircle
        size={size}
        className={clsx("text-emerald-500 dark:text-emerald-400", className)}
      />
    );
  }
  if (status === "error") {
    return (
      <XCircle
        size={size}
        className={clsx("text-red-500 dark:text-red-400", className)}
      />
    );
  }
  if (status === "cancelled") {
    return (
      <Ban
        size={size}
        className={clsx("text-stone-400 dark:text-stone-500", className)}
      />
    );
  }
  return (
    <ChevronRight
      size={size}
      className={clsx("text-stone-400 dark:text-stone-500", className)}
    />
  );
}

function createSubagentPanelFooter(subtitle: string | undefined) {
  if (!subtitle) return undefined;
  return (
    <div className="flex justify-end border-t border-theme-border bg-theme-bg-card px-3 py-2 sm:px-4">
      <span
        className="shrink-0 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-theme-bg-subtle px-1.5 text-[10px] font-semibold leading-none text-theme-text-secondary"
        title={subtitle}
      >
        {subtitle}
      </span>
    </div>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function openSubagentPanelByAgentId(agentId: string): boolean {
  const data = subagentPanelStore.get(agentId);
  if (!data) {
    return false;
  }

  const { panelStatus, subtitle, panelKey, formattedAgentName } =
    buildSubagentPanelState(data);

  if (isPersistentToolPanelOpen(panelKey)) {
    return true;
  }

  resetSubagentPanelAutoOpenState(panelKey);
  openPersistentToolPanel({
    title: formattedAgentName,
    icon: <Bot size={16} />,
    status: panelStatus,
    panelKey,
    children: <DeferredSubagentPanelContent agentId={agentId} />,
    footer: createSubagentPanelFooter(subtitle),
    onUserClose: () => dismissSubagentPanelAutoOpen(panelKey),
  });

  return true;
}

// Subagent Block - compact card, content always in sidebar panel
export function SubagentBlock({
  agent_id,
  agent_name,
  agent_avatar,
  input,
  result,
  success,
  isPending,
  parts,
  startedAt,
  completedAt,
  status,
  error,
}: {
  agent_id: string;
  agent_name: string;
  agent_avatar?: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
  error?: string;
}) {
  const {
    effectiveStatus,
    panelStatus,
    subtitle,
    panelKey,
    formattedAgentName,
  } = buildSubagentPanelState({
    agentId: agent_id,
    agentName: agent_name,
    input,
    result,
    success,
    error,
    isPending,
    parts,
    startedAt,
    completedAt,
    status,
  });
  const { t } = useTranslation();
  const roleIconMeta = getSubagentRoleIconMeta(formattedAgentName);
  const RoleIcon = roleIconMeta.icon;
  const agentAvatarUrl = getSubagentAvatarImageUrl(agent_avatar);

  // Stable serialization of parts for effect dependency — array reference
  // changes every render from the parent but content only changes on real updates.
  const partsKey = useMemo(() => JSON.stringify(parts ?? []), [parts]);

  useEffect(() => {
    subagentPanelStore.set({
      agentId: agent_id,
      agentName: agent_name,
      input,
      result,
      success,
      error,
      isPending,
      parts,
      startedAt,
      completedAt,
      status: effectiveStatus as SubagentPanelData["status"],
    });

    // Background activity may surface once, only in an empty docked lane.
    if (isPersistentToolPanelOpen(panelKey)) {
      updatePersistentToolPanel(
        (prev) => ({
          ...prev,
          status: panelStatus,
          footer: createSubagentPanelFooter(subtitle),
        }),
        panelKey,
      );
    } else {
      const laneOccupied = hasOpenRightPanel();
      const allowAutomaticPanel = shouldAllowAutomaticRightPanel({
        presentation: getRightPanelPresentation(window.innerWidth),
        laneOccupied,
      });
      if (
        allowAutomaticPanel &&
        shouldAutoOpenSubagentPanel({
          status: effectiveStatus,
          laneOccupied,
          alreadyAutoOpened: hasSubagentPanelAutoOpened(panelKey),
          autoOpenDismissed: isSubagentPanelAutoOpenDismissed(panelKey),
        })
      ) {
        markSubagentPanelAutoOpened(panelKey);
        openPersistentToolPanel({
          title: formattedAgentName,
          icon: <RoleIcon size={16} />,
          status: panelStatus,
          panelKey,
          children: <DeferredSubagentPanelContent agentId={agent_id} />,
          footer: createSubagentPanelFooter(subtitle),
          auto: true,
          onUserClose: () => dismissSubagentPanelAutoOpen(panelKey),
        });
      }
    }
  }, [
    agent_id,
    agent_name,
    input,
    result,
    success,
    error,
    isPending,
    parts,
    partsKey,
    startedAt,
    completedAt,
    effectiveStatus,
    panelStatus,
    subtitle,
    formattedAgentName,
    RoleIcon,
    panelKey,
  ]);

  useEffect(() => {
    return () => {
      subagentPanelStore.delete(agent_id);
    };
  }, [agent_id]);

  const handleOpenInPanel = useCallback(() => {
    resetSubagentPanelAutoOpenState(panelKey);
    openPersistentToolPanel({
      title: formattedAgentName,
      icon: <RoleIcon size={16} />,
      status: panelStatus,
      panelKey,
      children: <DeferredSubagentPanelContent agentId={agent_id} />,
      footer: createSubagentPanelFooter(subtitle),
      onUserClose: () => dismissSubagentPanelAutoOpen(panelKey),
    });
  }, [formattedAgentName, RoleIcon, panelStatus, subtitle, panelKey, agent_id]);

  return (
    <div
      className={clsx(
        "my-1.5 rounded-xl overflow-hidden min-w-0 group relative",
        "ring-1 ring-stone-300/80 dark:ring-stone-600/60 transition-all duration-250",
        "bg-theme-bg-card",
      )}
    >
      <div
        className={clsx(
          "absolute right-2.5 top-2.5 z-[1] flex h-5 w-5 items-center justify-center rounded-full",
          "shadow-sm ring-1",
          effectiveStatus === "running" &&
            "bg-amber-100/80 dark:bg-amber-900/30 ring-amber-300/70 dark:ring-amber-700/50",
          effectiveStatus === "complete" &&
            "bg-emerald-100/80 dark:bg-emerald-900/30 ring-emerald-300/70 dark:ring-emerald-700/50",
          effectiveStatus === "error" &&
            "bg-red-100/80 dark:bg-red-900/30 ring-red-300/70 dark:ring-red-900/45",
          effectiveStatus === "cancelled" &&
            "bg-stone-200/60 dark:bg-stone-700/50 ring-stone-300/60 dark:ring-stone-600/50",
          (!effectiveStatus || effectiveStatus === "pending") &&
            "bg-stone-100 dark:bg-stone-800 ring-stone-200 dark:ring-stone-700",
        )}
        aria-label={t("chat.subagentStatus", {
          status: effectiveStatus || "pending",
        })}
      >
        <SubagentStatusIcon status={effectiveStatus} size={11} />
      </div>
      <div
        className="flex items-center gap-3 px-3.5 py-2.5 pr-10 cursor-pointer transition-colors duration-150 hover:bg-theme-bg-card/60 dark:hover:bg-theme-bg-card/10"
        onClick={handleOpenInPanel}
      >
        <div
          className={clsx(
            "relative flex h-8 w-8 items-center justify-center rounded-lg shrink-0 overflow-hidden",
            "ring-1 ring-inset ring-black/5 dark:ring-white/10",
            agentAvatarUrl
              ? "bg-white dark:bg-stone-800"
              : roleIconMeta.bgClassName,
          )}
        >
          {!agentAvatarUrl && roleIconMeta.emoji ? (
            <ImageWithSkeleton
              src={getFluentEmojiCDN(roleIconMeta.emoji!, { type: "3d" })}
              alt={roleIconMeta.emoji}
              skipUrlResolve
              inline
              loading="eager"
              style={{ objectFit: "contain" }}
            />
          ) : !agentAvatarUrl ? (
            <RoleIcon size={15} className={roleIconMeta.className} />
          ) : null}
          {agentAvatarUrl && (
            <div className="absolute inset-0 overflow-hidden rounded-full">
              <ImageWithSkeleton
                src={agentAvatarUrl}
                alt=""
                skipUrlResolve
                inline
                loading="lazy"
              />
            </div>
          )}
          {agent_avatar && !agentAvatarUrl && (
            <PersonaAvatarIcon
              avatar={agent_avatar}
              size={15}
              className="absolute"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <span
            className={clsx(
              "text-[13px] font-medium truncate block",
              "text-theme-text",
            )}
          >
            {formattedAgentName}
          </span>
          {input && (
            <p className="text-[11px] text-theme-text-tertiary truncate mt-px">
              {input}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
