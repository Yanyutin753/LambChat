import { useCallback, useEffect } from "react";
import { clsx } from "clsx";
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
        fallbackIcon={
          roleIconMeta.kind === "general" ? undefined : roleIconMeta.icon
        }
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
        "border border-theme-border-subtle transition-colors duration-150 hover:border-theme-border-hover",
        "bg-theme-bg-card",
      )}
    >
      <button
        type="button"
        className="flex w-full min-h-11 items-center gap-3 px-3.5 py-2.5 text-left cursor-pointer transition-colors duration-150 hover:bg-theme-bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--theme-ring)]"
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
            <p className="text-12 text-theme-text-tertiary truncate mt-0.5">
              {input}
            </p>
          )}
        </div>
        <span
          data-status={panelStatus}
          className={clsx(
            "flex max-w-[38%] shrink-0 items-center gap-1.5 text-12",
            panelStatus === "error"
              ? "text-[color-mix(in_srgb,var(--theme-error)_45%,var(--theme-text))]"
              : "text-theme-text-tertiary",
          )}
        >
          <span className="truncate">
            {t(
              effectiveStatus === "running"
                ? "chat.message.toolSubagentRunning"
                : effectiveStatus === "complete"
                  ? "chat.message.toolSubagentCompleted"
                  : effectiveStatus === "error"
                    ? "chat.message.toolSubagentFailed"
                    : effectiveStatus === "timed_out"
                      ? "chat.message.toolSubagentTimedOut"
                      : effectiveStatus === "cancelled"
                        ? "chat.cancelled"
                        : effectiveStatus === "waiting_human"
                          ? "chat.message.toolSubagentWaitingHuman"
                          : "chat.message.toolSubagentQueued",
            )}
          </span>
        </span>
      </button>
    </div>
  );
}
