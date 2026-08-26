/** 从会话 metadata 提取请求配置（agent/工具/技能/人设/团队）。 */

import type { BackendSession } from "../../services/api";
import type { PersonaPresetSnapshot } from "../../types";

export function extractSessionConfig(sessionData: BackendSession) {
  return {
    agent_id: (sessionData.metadata?.agent_id as string) || undefined,
    agent_options:
      (sessionData.metadata?.agent_options as Record<
        string,
        boolean | string | number
      >) || undefined,
    disabled_tools:
      (sessionData.metadata?.disabled_tools as string[]) || undefined,
    disabled_skills:
      (sessionData.metadata?.disabled_skills as string[]) || undefined,
    enabled_skills:
      (sessionData.metadata?.enabled_skills as string[]) || undefined,
    persona_preset_id:
      (sessionData.metadata?.persona_preset_id as string) || undefined,
    persona_preset_name:
      (sessionData.metadata?.persona_preset_name as string) || undefined,
    persona_snapshot:
      (sessionData.metadata?.persona_snapshot as PersonaPresetSnapshot) ||
      undefined,
    disabled_mcp_tools:
      (sessionData.metadata?.disabled_mcp_tools as string[]) || undefined,
    team_id: (sessionData.metadata?.team_id as string) || undefined,
  };
}
