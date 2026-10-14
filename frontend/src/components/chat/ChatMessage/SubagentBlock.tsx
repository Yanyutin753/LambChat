import { LoadingSpinner } from "../../common/LoadingSpinner";
import { useCallback, useEffect } from "react";
import { clsx } from "clsx";
import { CheckCircle, XCircle, Ban, ChevronRight, Hourglass } from "lucide-react";
import { useTranslation } from "react-i18next";
import { hasOpenRightPanel } from "../../common/rightPanelCoordinator";
import {
  getRightPanelPresentation,
  shouldAllowAutomaticRightPanel,
} from "../../../hooks/rightPanelLayout";
import { AgentAvatar } from "../../common/AgentAvatar";
import type { MessagePart } from "../../../types";
import {
  openPersistentToolPanel,
  isPersistentToolPanelOpen,
  isPersistentToolPanelActive,
} from "./items/persistentToolPanelState";
import { subagentPanelStore } from "./subagentPanelStore";
import type { SubagentPanelData } from "./subagentPanelStore";
import {
  dismissSubagentPanelAutoOpen,
  hasSubagentPanelAutoOpened,
  isSubagentPanelAutoOpenDismissed,
  markSubagentPanelAutoOpened,
  resetSubagentPanelAutoOpenState,
  shouldAutoOpenSubagentPanel,
} from "./subagentPanelControl";
import { isUserReadingHistory } from "../streamFollowSignal";
import {
  buildSubagentPanelState,
  createSubagentPanelFooter,
} from "./subagentPanelState";
import { getSubagentRoleIconMeta } from "./subagentRoleMeta";
import { DeferredSubagentPanelContent } from "./DeferredSubagentPanelContent";
import { buildPanelSummary } from "./panelSummary";

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
      <LoadingSpinner
        color="text-current"
        size={size}
        className={clsx("text-amber-500 dark:text-amber-400", className)}
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
  if (status === "queued" || status === "waiting_human") {
    return <Hourglass size={size} className={clsx("text-theme-text-tertiary", className)} />;
  }
  if (status === "error" || status === "timed_out") {
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

// eslint-disable-next-line react-refresh/only-export-components
export function openSubagentPanelByAgentId(agentId: string): boolean {
  const data = subagentPanelStore.get(agentId);
  if (!data) {
    return false;
  }

  const { panelStatus, subtitle, panelKey, formattedAgentName } =
    buildSubagentPanelState(data);

  if (isPersistentToolPanelActive(panelKey)) {
    return true;
  }

  resetSubagentPanelAutoOpenState(panelKey);
  const roleIconMeta = getSubagentRoleIconMeta(data.agentName);
  openPersistentToolPanel({
    title: formattedAgentName,
    subtitle: buildPanelSummary(data.input),
    icon: (
      <AgentAvatar
        avatar={data.agentAvatar}
        seed={data.agentName}
        fallbackIcon={roleIconMeta.kind === "general" ? undefined : roleIconMeta.icon}
        size={16}
      />
    ),
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
  status?: SubagentPanelData["status"];
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
  const fallbackIcon =
    roleIconMeta.kind === "general" ? undefined : roleIconMeta.icon;

  // 面板数据由 ChatView 级 syncSubagentPanelStore 全量同步（与虚拟化无关）；
  // 这里只负责自动开启判定，不再直接写 store——组件卸载不应冻结/清空侧边栏。

  useEffect(() => {
    if (isPersistentToolPanelOpen(panelKey)) {
      // 状态/页脚由 PersistentToolPanelHost 订阅 store 实时刷新
      return;
    }
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
        userReadingHistory: isUserReadingHistory(),
      })
    ) {
      markSubagentPanelAutoOpened(panelKey);
      openPersistentToolPanel({
        title: formattedAgentName,
        subtitle: buildPanelSummary(input),
        icon: (
          <AgentAvatar
            avatar={agent_avatar}
            seed={agent_name}
            fallbackIcon={fallbackIcon}
            size={16}
          />
        ),
        status: panelStatus,
        panelKey,
        children: <DeferredSubagentPanelContent agentId={agent_id} />,
        footer: createSubagentPanelFooter(subtitle),
        auto: true,
        onUserClose: () => dismissSubagentPanelAutoOpen(panelKey),
      });
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
    startedAt,
    completedAt,
    effectiveStatus,
    panelStatus,
    subtitle,
    formattedAgentName,
    agent_avatar,
    fallbackIcon,
    panelKey,
  ]);

  const handleOpenInPanel = useCallback(() => {
    resetSubagentPanelAutoOpenState(panelKey);
    openPersistentToolPanel({
      title: formattedAgentName,
      subtitle: buildPanelSummary(input),
      icon: (
          <AgentAvatar
            avatar={agent_avatar}
            seed={agent_name}
            fallbackIcon={fallbackIcon}
            size={16}
          />
        ),
      status: panelStatus,
      panelKey,
      children: <DeferredSubagentPanelContent agentId={agent_id} />,
      footer: createSubagentPanelFooter(subtitle),
      onUserClose: () => dismissSubagentPanelAutoOpen(panelKey),
    });
  }, [
    formattedAgentName,
    agent_avatar,
    agent_name,
    fallbackIcon,
    panelStatus,
    subtitle,
    panelKey,
    agent_id,
    input,
  ]);

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
          (effectiveStatus === "error" || effectiveStatus === "timed_out") &&
            "bg-red-100/80 dark:bg-red-900/30 ring-red-300/70 dark:ring-red-900/45",
          effectiveStatus === "cancelled" &&
            "bg-stone-200/60 dark:bg-stone-700/50 ring-stone-300/60 dark:ring-stone-600/50",
          (!effectiveStatus || effectiveStatus === "pending" || effectiveStatus === "queued" || effectiveStatus === "waiting_human") &&
            "bg-stone-100 dark:bg-stone-800 ring-stone-200 dark:ring-stone-700",
        )}
        aria-label={t("chat.subagentStatus", {
          status: effectiveStatus === "queued"
            ? t("chat.message.toolSubagentQueued")
            : effectiveStatus === "waiting_human"
              ? t("chat.message.toolSubagentWaitingHuman")
              : effectiveStatus === "timed_out"
                ? t("chat.message.toolSubagentTimedOut")
                : effectiveStatus || "pending",
        })}
      >
        <SubagentStatusIcon status={effectiveStatus} size={11} />
      </div>
      <div
        className="flex items-center gap-3 px-3.5 py-2.5 pr-10 cursor-pointer transition-colors duration-150 hover:bg-theme-bg-card/60 dark:hover:bg-theme-bg-card/10"
        onClick={handleOpenInPanel}
      >
        <AgentAvatar
          avatar={agent_avatar}
          seed={agent_name}
          fallbackIcon={fallbackIcon}
          size={32}
          iconSize={15}
          className="rounded-lg shrink-0 overflow-hidden bg-theme-bg-subtle text-theme-text-secondary ring-1 ring-inset ring-black/5 dark:ring-white/10"
        />

        <div className="flex-1 min-w-0">
          <span
            className={clsx(
              "text-13 font-medium font-serif truncate block",
              "text-theme-text",
            )}
          >
            {formattedAgentName}
          </span>
          {input && (
            <p className="text-11 text-theme-text-tertiary truncate font-serif mt-px">
              {input}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
