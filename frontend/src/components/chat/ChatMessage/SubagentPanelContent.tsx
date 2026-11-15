import { InteractiveIcon } from "../../common/InteractiveIcon";
import { useCallback, useContext, useSyncExternalStore, useMemo } from "react";
import { RightPanelActiveContext } from "../../common/useRightPanelEntry";
import { ArrowDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ChatMessage } from "./index";
import { formatSubagentName } from "./subagentRoleMeta";
import { buildSubagentConversation } from "./subagentPanelState";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore";
import { usePanelScrollFollow } from "./usePanelScrollFollow";
function useSubagentPanelData(
  agentId: string,
  active: boolean,
): SubagentPanelData | undefined {
  const subscribe = useCallback(
    (listener: () => void) =>
      active ? subagentPanelStore.subscribe(agentId, listener) : () => {},
    [active, agentId],
  );
  return useSyncExternalStore(subscribe, () => subagentPanelStore.get(agentId));
}

export function SubagentPanelContent({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const active = useContext(RightPanelActiveContext);
  const data = useSubagentPanelData(agentId, active);
  const { scrollRef, contentRef, showScrollToBottom, jumpToBottom } =
    usePanelScrollFollow(data);
  const messages = useMemo(
    () => (data ? buildSubagentConversation(data, t) : []),
    [data, t],
  );

  if (!data) return null;
  return (
    <div className="subagent-conversation relative flex h-full min-h-0 flex-col font-sans">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto py-4">
        <div ref={contentRef} className="space-y-6">
          {messages.map((message, index) => (
            <ChatMessage
              key={message.id}
              message={message}
              personaName={formatSubagentName(data.agentName)}
              personaSeed={data.agentName}
              personaAvatar={data.agentAvatar}
              isFirst={index === 0}
              isLastMessage={index === messages.length - 1}
              showFeedbackAndShareActions={false}
            />
          ))}
          <div className="h-px" />
        </div>
      </div>
      {showScrollToBottom && (
        <button
          type="button"
          onClick={jumpToBottom}
          aria-label={t("common.scrollToBottom")}
          className="absolute bottom-3 left-1/2 z-10 inline-flex min-h-9 w-max max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-1.5 rounded-full border border-theme-border bg-theme-bg-card/95 px-3 text-12 font-medium text-theme-text-secondary shadow-lg transition-colors hover:bg-theme-bg-hover hover:text-theme-text"
        >
          <InteractiveIcon>
            <ArrowDown size={13} />
          </InteractiveIcon>
          {t("common.scrollToBottom")}
        </button>
      )}
    </div>
  );
}
