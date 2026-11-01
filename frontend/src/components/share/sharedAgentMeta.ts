import type { AgentInfo } from "../../types";
import type { SharedAgentMeta } from "../../types/share";

/**
 * 把分享接口下发的 agent_meta 字典转成目录条目；页头名称与消息内
 * 名称/头像共用同一份，保证公开页两处展示一致。
 */
export function sharedAgentMetaToEntry(
  meta: SharedAgentMeta | undefined,
  agentId: string | undefined,
): AgentInfo | undefined {
  const id = meta?.id || agentId;
  if (!id) return undefined;
  if (!meta) return { id, name: `agents.${id}.name`, description: "", version: "" };
  const labels = meta.labels
    ? Object.fromEntries(
        Object.entries(meta.labels).map(([locale, label]) => [
          locale,
          { name: label.name, description: "" },
        ]),
      )
    : undefined;
  return {
    id,
    name: meta.name || `agents.${id}.name`,
    description: "",
    version: "",
    icon: meta.icon ?? undefined,
    labels,
  };
}
