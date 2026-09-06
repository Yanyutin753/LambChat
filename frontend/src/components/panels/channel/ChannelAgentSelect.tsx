/**
 * Agent selector for channel configuration.
 * Fetches user's available agents and renders a select dropdown.
 */
import { useState, useEffect } from "react";
import { Bot } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
import { agentApi } from "../../../services/api/agent";
import type { AgentInfo } from "../../../types";
import { GlassSelect } from "../../common/GlassSelect";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../../agent/agentCatalog";

interface ChannelAgentSelectProps {
  value: string | null | undefined;
  onChange: (agentId: string | null) => void;
}

export function ChannelAgentSelect({
  value,
  onChange,
}: ChannelAgentSelectProps) {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    agentApi
      .list()
      .then((res) => {
        setAgents(res.agents || []);
      })
      .catch(() => {
        setAgents([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="es-field">
      <label className="es-label">
        <div className="flex items-center gap-1.5">
          <Bot size={14} />
          {t("channel.agent", "Agent")}
        </div>
      </label>
      <GlassSelect
        value={value || ""}
        onChange={(v) => onChange(v || null)}
        disabled={loading}
        placeholder={
          loading
            ? t("common.loading", "Loading...")
            : t("channel.defaultAgent", "Default Agent")
        }
        options={agents.map((agent) => ({
          value: agent.id,
          label: (
            <>
              <span className="font-serif">
                {resolveAgentDisplayName(agent, i18n.language, t)}
              </span>
              <span className="opacity-60">
                {" — "}
                {resolveAgentDescription(agent, i18n.language, t)}
              </span>
            </>
          ),
        }))}
      />
      <p className="es-hint">
        {t(
          "channel.agentHint",
          "Select which agent handles messages from this channel",
        )}
      </p>
    </div>
  );
}
