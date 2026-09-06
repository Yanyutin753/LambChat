import type { CollapsibleStatus } from "../../common";
import type { Message, MessagePart } from "../../../types";
import type { SubagentPanelData } from "./subagentPanelStore";
import { subagentPanelStore } from "./subagentPanelStore";
import { createSubagentPanelKey } from "./messagePartAnchors";
import { formatDateTime } from "../../../utils/datetime";
import { formatSubagentName } from "./subagentRoleMeta";

export function createSubagentPanelFooter(subtitle: string | undefined) {
  if (!subtitle) return undefined;
  return (
    <div className="flex justify-end border-t border-theme-border bg-theme-bg-card px-3 py-2 sm:px-4">
      <span
        className="shrink-0 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-theme-bg-subtle px-1 text-10 font-semibold leading-none text-theme-text-secondary"
        title={subtitle}
      >
        {subtitle}
      </span>
    </div>
  );
}

export function buildSubagentPanelState(data: SubagentPanelData) {
  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");
  const panelStatus: CollapsibleStatus =
    effectiveStatus === "running"
      ? "loading"
      : effectiveStatus === "complete"
        ? "success"
        : effectiveStatus === "error"
          ? "error"
          : effectiveStatus === "cancelled"
            ? "cancelled"
            : "idle";
  const subtitle = data.startedAt ? formatDateTime(data.startedAt) : undefined;

  return {
    effectiveStatus,
    panelStatus,
    subtitle: subtitle || undefined,
    panelKey: createSubagentPanelKey(data.agentId),
    formattedAgentName: formatSubagentName(data.agentName),
  };
}

/**
 * 把消息列表中的全部 subagent part（含嵌套）同步进 subagentPanelStore。
 *
 * 数据生命周期挂在 ChatView 而非 SubagentBlock：虚拟列表滚动会卸载消息行，
 * 组件级同步会让已打开的侧边栏停更甚至清空；全量同步与虚拟化无关，
 * 面板内容由此保持实时。
 */
export function syncSubagentPanelStore(messages: readonly Message[]): void {
  messages.forEach((message) => syncSubagentParts(message.parts ?? []));
}

function syncSubagentParts(parts: readonly MessagePart[]): void {
  parts.forEach((part) => {
    if (part.type !== "subagent") return;
    subagentPanelStore.set({
      agentId: part.agent_id,
      agentName: part.agent_name,
      input: part.input,
      result: part.result,
      success: part.success,
      error: part.error,
      isPending: part.isPending,
      parts: part.parts,
      startedAt: part.startedAt,
      completedAt: part.completedAt,
      // 与 buildSubagentPanelState 的 effectiveStatus 派生保持一致
      status: (part.status ||
        (part.isPending
          ? "running"
          : part.success
            ? "complete"
            : "error")) as SubagentPanelData["status"],
    });
    if (part.parts) syncSubagentParts(part.parts);
  });
}
