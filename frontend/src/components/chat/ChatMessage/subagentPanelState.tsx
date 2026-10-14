import type { CollapsibleStatus } from "../../common";
import type {
  Message,
  MessagePart,
  SubagentPart,
  ToolPart,
} from "../../../types";
import type { SubagentPanelData } from "./subagentPanelStore";
import { subagentPanelStore } from "./subagentPanelStore";
import {
  createSubagentPanelKey,
  createSubagentAnchorOwnerId,
} from "./messagePartAnchors";
import { formatDateTime } from "../../../utils/datetime";
import { formatSubagentName } from "./subagentRoleMeta";
import { extractText } from "./items/toolUtils";
import { splitRunTailGroups } from "./runStepsCollapseUtils";

export function parseSubagentControlResult(
  result: ToolPart["result"],
): Record<string, unknown> | null {
  try {
    const value = JSON.parse(extractText(result));
    return value && typeof value === "object" && !Array.isArray(value)
      ? value
      : null;
  } catch {
    return null;
  }
}

export function buildSubagentConversation(data: SubagentPanelData): Message[] {
  const history = data.history?.length
    ? data.history
    : [
        {
          type: "subagent",
          agent_id: data.agentId,
          agent_name: data.agentName,
          depth: 1,
          input: data.input,
          result: data.result,
          error: data.error,
          success: data.success,
          parts: data.parts,
          status: data.status,
          isPending: data.isPending,
          startedAt: data.startedAt,
          completedAt: data.completedAt,
        } satisfies SubagentPart,
      ];
  const messages: Message[] = [];
  const live = new Map<SubagentPart, ToolPart[]>();
  const attached = new Set<ToolPart>();
  let run: SubagentPart | undefined;
  for (const part of history) {
    if (part.type === "subagent") run = part;
    if (part.type !== "tool" || !run?.startedAt) continue;
    const sentAt = Date.parse(part.startedAt ?? "");
    if (
      sentAt >= run.startedAt &&
      (run.isPending || (run.completedAt && sentAt <= run.completedAt))
    ) {
      const followups = live.get(run) ?? [];
      followups.push(part);
      live.set(run, followups);
      attached.add(part);
    }
  }
  const seenInputs = new Set<string>();
  const addFollowup = (part: ToolPart, index: number) => {
    if (typeof part.args.message !== "string") return;
    const parsed = parseSubagentControlResult(part.result);
    const failed =
      !part.isPending &&
      !part.cancelled &&
      (part.success === false ||
        parsed?.status === "failed" ||
        parsed?.status === "error");
    const id = `${data.agentId}-message-${part.id ?? index}`;
    const timestamp = new Date(part.startedAt ?? 0);
    messages.push({
      id,
      role: "user",
      content: part.args.message,
      timestamp,
      metadata: failed ? { steerStatus: "failed" } : undefined,
    });
    const error =
      part.error ??
      parsed?.error ??
      (failed && !parsed ? extractText(part.result) : undefined);
    if (failed && typeof error === "string" && error) {
      messages.push({
        id: `${id}-error`,
        role: "assistant",
        content: error,
        timestamp,
      });
    }
    if (part.cancelled) {
      messages.push({
        id: `${id}-cancelled`,
        role: "assistant",
        content: "",
        timestamp,
        cancelled: true,
        parts: [{ type: "cancelled" }],
      });
    }
  };
  history.forEach((part, index) => {
    if (part.type === "tool") {
      if (!attached.has(part)) addFollowup(part, index);
      return;
    }
    if (part.type !== "subagent") return;
    const id = `${data.agentId}-run-${index}`;
    const timestamp = new Date(part.startedAt ?? 0);
    const previous = history[index - 1];
    if (
      part.input &&
      !seenInputs.has(part.input) &&
      !(previous?.type === "tool" && previous.args.message === part.input)
    ) {
      messages.push({
        id: `${id}-task`,
        role: "user",
        content: part.input,
        timestamp,
      });
    }
    seenInputs.add(part.input);
    const status =
      part.status ??
      (part.isPending ? "running" : part.success ? "complete" : "error");
    const isStreaming = status === "pending" || status === "running";
    const parts = [...(part.parts ?? [])];
    let streamedPrefix: MessagePart | undefined;
    if (part.result && ["complete", "timed_out", "error"].includes(status)) {
      let lastText = -1;
      for (let i = parts.length - 1; i >= 0; i--) {
        if (parts[i].type === "text") {
          lastText = i;
          break;
        }
      }
      const result: MessagePart = { type: "text", content: part.result };
      const last = parts[lastText];
      if (last?.type === "text" && part.result.startsWith(last.content))
        parts[lastText] = result;
      else if (last?.type === "text" && last.content.endsWith(part.result)) {
        // A late instruction can produce consecutive model replies in one text part.
        streamedPrefix = {
          ...last,
          content: last.content.slice(0, -part.result.length),
        };
        parts[lastText] = streamedPrefix;
        // Append the report so following tools keep their native anchor indices.
        parts.push(result);
      } else parts.push(result);
    }
    if (part.error && (status === "error" || status === "timed_out"))
      parts.push({ type: "text", content: part.error });
    if (status === "cancelled" && !parts.some((p) => p.type === "cancelled"))
      parts.push({ type: "cancelled" });
    const assistant: Message = {
      id,
      role: "assistant",
      content: "",
      timestamp,
      parts,
      isStreaming,
      cancelled: status === "cancelled",
      duration:
        part.completedAt && part.startedAt
          ? part.completedAt - part.startedAt
          : undefined,
      metadata:
        part === run
          ? { partAnchorOwnerId: createSubagentAnchorOwnerId(data.agentId) }
          : undefined,
    };
    const followups = live.get(part);
    if (followups?.length) {
      let remaining = parts;
      let offset = 0;
      let resumedAt = part.startedAt!;
      const ordered = [...followups].sort(
        (a, b) => Date.parse(a.startedAt!) - Date.parse(b.startedAt!),
      );
      ordered.forEach((message, followupIndex) => {
        const sentAt = Date.parse(message.startedAt!);
        const { head, tail } = splitRunTailGroups(
          remaining.map((p, partIndex) => ({
            type: "single" as const,
            part: p,
            partIndex,
          })),
          { enabled: true },
        );
        // shortcut: text has no timestamps; use tool boundaries until parts carry timing.
        let firstLaterTool = remaining.findIndex(
          (p) => p.type === "tool" && Date.parse(p.startedAt ?? "") >= sentAt,
        );
        while (
          firstLaterTool > 0 &&
          remaining[firstLaterTool - 1].type !== "tool" &&
          remaining[firstLaterTool - 1] !== streamedPrefix
        ) {
          firstLaterTool--;
        }
        while (firstLaterTool >= 0 && head.length > firstLaterTool) {
          tail.unshift(head.pop()!);
        }
        if (head.length)
          messages.push({
            ...assistant,
            id: `${id}-process-${followupIndex}`,
            parts: head.map((group) => group.part),
            timestamp: new Date(resumedAt),
            isStreaming: false,
            cancelled: false,
            duration: sentAt - resumedAt,
            metadata: { ...assistant.metadata, partIndexOffset: offset },
          });
        addFollowup(message, history.indexOf(message));
        remaining = tail.map((group) => group.part);
        offset += head.length;
        resumedAt = sentAt;
      });
      messages.push({
        ...assistant,
        parts: remaining,
        timestamp: new Date(resumedAt),
        duration: part.completedAt ? part.completedAt - resumedAt : undefined,
        metadata: { ...assistant.metadata, partIndexOffset: offset },
      });
    } else {
      messages.push(assistant);
    }
  });
  return messages;
}

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
        : effectiveStatus === "error" || effectiveStatus === "timed_out"
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
  const latest = new Map<string, SubagentPanelData>();
  const history = new Map<string, MessagePart[]>();
  function collect(parts: readonly MessagePart[]): void {
    parts.forEach((part) => {
      const agentId =
        part.type === "subagent"
          ? part.agent_id
          : part.type === "tool" &&
              part.name === "send_subagent_message" &&
              typeof part.args.subagent_id === "string"
            ? part.args.subagent_id
            : undefined;
      if (agentId) {
        const activity = history.get(agentId) ?? [];
        activity.push(part);
        history.set(agentId, activity);
      }
      if (part.type !== "subagent") return;
      latest.set(part.agent_id, {
        agentId: part.agent_id,
        agentName: part.agent_name,
        agentAvatar: part.agent_avatar,
        input: part.input,
        result: part.result,
        success: part.success,
        error: part.error,
        isPending: part.isPending,
        parts: part.parts,
        startedAt: part.startedAt,
        completedAt: part.completedAt,
        status:
          part.status ||
          (part.isPending ? "running" : part.success ? "complete" : "error"),
      });
      if (part.parts) collect(part.parts);
    });
  }
  messages.forEach((message) => collect(message.parts ?? []));
  latest.forEach((data, agentId) =>
    subagentPanelStore.set({ ...data, history: history.get(agentId) }),
  );
}
