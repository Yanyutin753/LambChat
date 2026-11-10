import { AgentAvatar } from "../../../common/AgentAvatar";
import { Users, ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CopyButton } from "../../../common/CopyButton";
import { TagBadge } from "../../../common/TagBadge";
import { parseSubagentControlResult } from "../subagentPanelState";
import { ToolResultContent } from "./McpBlockPreview";
import type { ToolDetailProps } from "./ToolLivePanelContent";

function isAssistant(
  value: unknown,
): value is Record<string, unknown> & { name: string; id: string } {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as Record<string, unknown>).name === "string" &&
    typeof (value as Record<string, unknown>).id === "string"
  );
}

export function AssistantToolResult({
  result,
}: Pick<ToolDetailProps, "result">) {
  const { t } = useTranslation();
  const data = parseSubagentControlResult(result);
  const items = Array.isArray(data?.assistants)
    ? data.assistants
    : isAssistant(data)
      ? [data]
      : null;
  if (!items || !items.every(isAssistant)) {
    return <ToolResultContent result={result} />;
  }
  const raw =
    typeof result === "string" ? result : JSON.stringify(result, null, 2);
  return (
    <div className="assistant-tool-results space-y-3 min-w-0">
      <div className="flex items-center justify-between gap-3">
        <span className="text-12 text-theme-text-tertiary">
          {t("chat.message.toolAssistantCount", { count: items.length })}
        </span>
        <CopyButton text={raw ?? ""} size={14} />
      </div>
      {items.length === 0 && (
        <p className="text-13 text-theme-text-secondary py-4">
          {t("assistants.empty")}
        </p>
      )}
      {items.map((item, index) => {
        const group = item.kind === "group";
        const members = Array.isArray(item.member_ids)
          ? item.member_ids.filter((id): id is string => typeof id === "string")
          : [];
        const knownMembers = members
          .map((id) => items.find((entry) => entry.id === id))
          .filter(isAssistant);
        const instructions =
          typeof item.instructions === "string" ? item.instructions : "";
        return (
          <article
            key={`${item.id}:${index}`}
            className="tool-result-card assistant-tool-card"
          >
            <div className="assistant-tool-card__heading">
              <AgentAvatar
                seed={item.name}
                avatar={
                  typeof item.avatar === "string" ? item.avatar : undefined
                }
                size={36}
              />
              <div className="min-w-0 flex-1">
                <h4 className="text-14 font-semibold text-theme-text [overflow-wrap:anywhere]">
                  {item.name}
                </h4>
                <div className="flex items-center flex-wrap gap-x-2 gap-y-1 mt-1 text-12 text-theme-text-tertiary">
                  <span>
                    {group
                      ? t("assistants.groupCount", { count: members.length })
                      : t("assistants.channelBinding")}
                  </span>
                  {typeof item.status === "string" && (
                    <TagBadge>
                      {t(`assistants.${item.status}`, {
                        defaultValue: item.status,
                      })}
                    </TagBadge>
                  )}
                </div>
              </div>
              <a
                className="assistant-tool-card__open"
                href={`/assistants/${encodeURIComponent(item.id)}`}
                aria-label={t("assistants.chatWith", { name: item.name })}
                title={t("assistants.openConversation")}
              >
                <ArrowUpRight size={16} />
              </a>
            </div>
            {instructions.length > 160 ? (
              <details className="assistant-tool-instructions">
                <summary>
                  <span className="line-clamp-3">{instructions}</span>
                  <span className="assistant-tool-instructions__more">
                    {t("chat.message.expandAll")}
                  </span>
                  <span className="assistant-tool-instructions__less">
                    {t("chat.message.collapse")}
                  </span>
                </summary>
                <p>{instructions}</p>
              </details>
            ) : (
              <p className="assistant-tool-card__description">
                {instructions || t("assistants.noInstructions")}
              </p>
            )}
            {knownMembers.length > 0 && (
              <div className="assistant-tool-card__members">
                <Users size={13} className="shrink-0" />
                <span>
                  {knownMembers.map((member) => member.name).join(" · ")}
                </span>
              </div>
            )}
          </article>
        );
      })}
      <details className="tool-result-raw assistant-tool-raw">
        <summary>{t("chat.message.toolResultRaw")}</summary>
        <pre className="text-12 text-theme-text-secondary whitespace-pre-wrap [overflow-wrap:anywhere] overflow-auto p-3">
          {raw}
        </pre>
      </details>
    </div>
  );
}
