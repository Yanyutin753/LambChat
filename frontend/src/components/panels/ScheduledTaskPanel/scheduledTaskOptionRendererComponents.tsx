import { useEffect, useState } from "react";
import { UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Select } from "../../common";
import { teamApi } from "../../../services/api/team";
import type { ExtensionScopedOption } from "../../../types";
import type { Team } from "../../../types/team";

export interface ScheduledTaskOptionRendererProps {
  option: ExtensionScopedOption;
  value: unknown;
  disabled?: boolean;
  inactive?: boolean;
  triggerClassName?: string;
  onChange: (value: unknown) => void;
}

function labelWithIcon(label: string) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <UsersRound size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{label}</span>
    </span>
  );
}

export function AgentTeamScheduledTaskTeamSelect({
  value,
  disabled,
  inactive,
  triggerClassName,
  onChange,
}: ScheduledTaskOptionRendererProps) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<Team[]>([]);

  useEffect(() => {
    if (inactive) {
      setTeams([]);
      return;
    }
    let cancelled = false;
    teamApi
      .list({ limit: 100 })
      .then((response) => {
        if (!cancelled) setTeams(response.teams);
      })
      .catch(() => {
        if (!cancelled) setTeams([]);
      });
    return () => {
      cancelled = true;
    };
  }, [inactive]);

  const options = [
    {
      value: "",
      label: labelWithIcon(t("scheduledTask.teamPlaceholder")),
    },
    ...teams.map((team) => ({
      value: team.id,
      label: labelWithIcon(team.name),
    })),
  ];
  const stringValue = typeof value === "string" ? value : "";
  if (stringValue && !options.some((option) => option.value === stringValue)) {
    options.push({
      value: stringValue,
      label: labelWithIcon(stringValue),
    });
  }

  return (
    <Select
      value={stringValue}
      onChange={onChange}
      disabled={disabled}
      triggerClassName={triggerClassName}
      options={options}
    />
  );
}
