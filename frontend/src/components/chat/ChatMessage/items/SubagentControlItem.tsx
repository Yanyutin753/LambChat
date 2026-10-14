import { memo, useCallback, useMemo, useSyncExternalStore } from "react";
import { Ban, Hourglass, List, MessageCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { openSubagentPanelByAgentId } from "../SubagentBlock";
import { subagentPanelStore } from "../subagentPanelStore";
import { formatSubagentName } from "../subagentRoleMeta";
import { parseSubagentControlResult } from "../subagentPanelState";
import { ToolResultContent } from "./McpBlockPreview";
import { ToolDurationFooter } from "./ToolDurationFooter";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { extractText } from "./toolUtils";

const stateKeys: Record<string, string> = {
  queued: "chat.message.toolSubagentQueued",
  running: "chat.message.toolSubagentRunning",
  completed: "chat.message.toolSubagentCompleted",
  waiting_human: "chat.message.toolSubagentWaitingHuman",
  failed: "chat.message.toolSubagentFailed",
  error: "chat.message.toolSubagentFailed",
  timed_out: "chat.message.toolSubagentTimedOut",
  cancelled: "chat.cancelled",
};

function SubagentControlDetail({
  args,
  result,
  isPending,
  cancelled,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const parsed = parseSubagentControlResult(result);
  const state = cancelled
    ? "cancelled"
    : !isPending && typeof parsed?.status === "string"
      ? parsed.status
      : "";
  const reply =
    !isPending && !cancelled
      ? parsed
        ? [parsed.result, parsed.error]
            .filter((value): value is string => typeof value === "string" && !!value)
            .join("\n\n")
        : extractText(result)
      : undefined;
  return (
    <div className="min-w-0 space-y-4 overflow-y-auto p-3 sm:p-4">
      {typeof args.message === "string" && (
        <div className="space-y-2">
          <div className="text-12 font-medium text-theme-text-tertiary">
            {t("chat.message.subagentMessage")}
          </div>
          <ToolResultContent result={args.message} />
        </div>
      )}
      {(isPending || stateKeys[state]) && (
        <p className="text-12 text-theme-text-secondary">
          {isPending ? t("chat.message.executing") : t(stateKeys[state])}
        </p>
      )}
      {typeof reply === "string" && reply.trim() && (
        <ToolResultContent result={reply} />
      )}
      {Array.isArray(parsed?.subagents) && (
        parsed.subagents.length ? (
          <ul className="space-y-2 text-12 text-theme-text-secondary">
            {parsed.subagents.map((entry, index) => {
              if (!entry || typeof entry !== "object") return null;
              const item = entry as Record<string, unknown>;
              const agent = subagentPanelStore.get(String(item.subagent_id || ""));
              return (
                <li key={String(item.subagent_id || index)} className="flex min-w-0 justify-between gap-3">
                  <span className="min-w-0 break-words">{formatSubagentName(agent?.agentName || String(item.subagent_type || ""))}</span>
                  <span className="shrink-0">{t(stateKeys[String(item.status)] || "chat.message.toolSubagentFailed")}</span>
                </li>
              );
            })}
          </ul>
        ) : <p className="text-12 text-theme-text-secondary">{t("chat.message.toolSubagentEmpty")}</p>
      )}
    </div>
  );
}

export const SubagentControlItem = memo(function SubagentControlItem({
  id,
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: ToolDetailProps & { id?: string; toolName: string }) {
  const { t } = useTranslation();
  const parsed = useMemo(() => parseSubagentControlResult(result), [result]);
  const isWait = toolName === "wait_subagent";
  const isParentMessage = toolName === "send_parent_message";
  const isCancel = toolName === "cancel_subagent";
  const isList = toolName === "list_subagents";
  const title = t(
    isCancel ? "chat.message.toolCancelSubagent"
      : isList ? "chat.message.toolListSubagents"
      : isParentMessage
      ? args.direction === "received"
        ? "chat.message.toolReceiveSubagentMessage"
        : "chat.message.toolSendParentMessage"
      : isWait
        ? "chat.message.toolWaitSubagent"
        : "chat.message.toolSendSubagentMessage",
  );
  const Icon = isCancel ? Ban : isList ? List : isWait ? Hourglass : MessageCircle;
  const subagentId = String(parsed?.subagent_id || args.subagent_id || "");
  const subscribe = useCallback(
    (listener: () => void) =>
      subagentPanelStore.subscribe(subagentId, listener),
    [subagentId],
  );
  const agent = useSyncExternalStore(subscribe, () =>
    subagentPanelStore.get(subagentId),
  );
  const state = typeof parsed?.status === "string" ? parsed.status : "";
  const messageQueued = !isWait && !isCancel && !isList && state === "running";
  const mailReceived = isWait && parsed?.messages_pending === true;
  const stateLabel = isPending
    ? ""
    : cancelled
      ? t("chat.cancelled")
      : mailReceived
        ? t("chat.message.toolReceiveSubagentMessage")
        : messageQueued
          ? t("chat.message.toolSubagentMessageQueued")
          : stateKeys[state]
            ? t(stateKeys[state])
            : "";
  const status = isPending
    ? "loading"
    : cancelled || state === "cancelled"
      ? "cancelled"
      : success === false || state === "failed" || state === "error" || state === "timed_out"
        ? "error"
        : (messageQueued || mailReceived) && success
          ? "success"
          : state === "running" || state === "waiting_human" || state === "queued"
            ? "idle"
            : success
              ? "success"
              : "idle";
  const label = [
    title,
    agent ? formatSubagentName(agent.agentName) : "",
    stateLabel,
  ]
    .filter(Boolean)
    .join(" · ");
  const detailProps = {
    args,
    result,
    success,
    isPending,
    cancelled,
    startedAt,
    completedAt,
  };
  const canExpand = !!subagentId || result !== undefined || !!isPending;
  const reply =
    !isPending && !cancelled && (state === "error" || state === "failed")
      ? parsed?.error
      : !isPending && !cancelled && success !== false
        ? isParentMessage
          ? args.message
          : state === "completed"
            ? parsed?.result
            : undefined
        : undefined;

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Icon size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isPending}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          if (openSubagentPanelByAgentId(subagentId)) return;
          openToolLivePanel({
            id,
            title,
            status,
            icon: <Icon size={16} />,
            fallback: <SubagentControlDetail {...detailProps} />,
            buildDetail: (data) => (
              <SubagentControlDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: (
              <ToolDurationFooter
                startedAt={startedAt}
                completedAt={completedAt}
              />
            ),
          });
        }}
      />
      {(!agent || isParentMessage || state === "failed" || state === "error") &&
        typeof reply === "string" &&
        reply.trim() && (
          <div className="my-2 min-w-0 max-w-full text-14 text-theme-text-secondary">
            <ToolResultContent result={reply} hideCopyButton />
          </div>
        )}
    </>
  );
});
