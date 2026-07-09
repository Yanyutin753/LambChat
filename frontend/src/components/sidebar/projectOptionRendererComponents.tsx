import { useEffect, useState } from "react";
import type { CoreScopedPluginOptionContribution } from "../../extensions/coreContributions";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";

export interface ProjectOptionRendererProps {
  option: CoreScopedPluginOptionContribution;
  value: unknown;
  disabled?: boolean;
  onChange: (value: unknown) => void;
}

export function AgentTeamDefaultTeamSelect({
  option,
  value,
  disabled,
  onChange,
}: ProjectOptionRendererProps) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(false);
  const selectedValue = typeof value === "string" ? value : "";

  useEffect(() => {
    if (!option.effective) {
      setTeams([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    teamApi
      .list({ limit: 100 })
      .then((response) => {
        if (!cancelled) setTeams(response.teams);
      })
      .catch(() => {
        if (!cancelled) setTeams([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [option.effective]);

  if (!option.effective) {
    return (
      <input
        type="text"
        value={selectedValue}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        placeholder="Team ID"
        className="w-full rounded-md border border-stone-200 bg-white px-2 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      />
    );
  }

  return (
    <select
      value={selectedValue}
      disabled={disabled || loading}
      onChange={(event) => onChange(event.target.value || null)}
      className="w-full rounded-md border border-stone-200 bg-white px-2 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
    >
      <option value="">No default team</option>
      {teams.map((team) => (
        <option key={team.id} value={team.id}>
          {team.name}
        </option>
      ))}
    </select>
  );
}
