import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { UsersRound } from "lucide-react";
import { Select } from "../../common";
import { teamApi } from "../../../services/api/team";
import {
  WorkflowPluginInputOption,
  WorkflowPluginSelectOption,
  WorkflowPluginVersionSelectOption,
  resolveWorkflowPluginLabels,
  resolveWorkflowPluginVersionLabels,
} from "../../../plugins/workflow/WorkflowSelectOption";
import type { ExtensionScopedOption } from "../../../types";
import type { Team } from "../../../types/team";

interface ScheduledTaskOptionRendererProps {
  option: ExtensionScopedOption;
  value: unknown;
  pluginValues?: Record<string, unknown>;
  disabled?: boolean;
  inactive?: boolean;
  triggerClassName?: string;
  onChange: (value: unknown) => void;
  onPluginValueChange?: (key: string, value: unknown) => void;
}

type ScheduledTaskOptionRenderer = (
  props: ScheduledTaskOptionRendererProps,
) => ReactNode;

type ScheduledTaskOptionLabelResolver = (
  values: readonly string[],
) => Promise<Record<string, string>>;

function labelWithIcon(label: string) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <UsersRound size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{label}</span>
    </span>
  );
}

function AgentTeamScheduledTaskTeamSelect({
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

const SCHEDULED_TASK_OPTION_RENDERERS: Record<string, ScheduledTaskOptionRenderer> = {
  "agent_team.TeamSelectOption": AgentTeamScheduledTaskTeamSelect,
  "workflow.WorkflowSelectOption": (props) => (
    <WorkflowPluginSelectOption
      {...props}
      placeholder="No workflow"
    />
  ),
  "workflow.WorkflowVersionSelectOption": (props) => (
    <WorkflowPluginVersionSelectOption
      {...props}
      placeholder="No version"
    />
  ),
  "workflow.WorkflowInputOption": (props) => (
    <WorkflowPluginInputOption {...props} />
  ),
};

const SCHEDULED_TASK_OPTION_LABEL_RESOLVERS: Record<
  string,
  ScheduledTaskOptionLabelResolver
> = {
  "agent_team.TeamSelectOption": async (values) => {
    const wanted = new Set(values.filter(Boolean));
    if (wanted.size === 0) return {};
    const response = await teamApi.list({ limit: 100 });
    return Object.fromEntries(
      response.teams
        .filter((team) => wanted.has(team.id))
        .map((team) => [team.id, team.name]),
    );
  },
  "workflow.WorkflowSelectOption": resolveWorkflowPluginLabels,
  "workflow.WorkflowVersionSelectOption": resolveWorkflowPluginVersionLabels,
};

export function findScheduledTaskOptionRenderer(
  options: readonly ExtensionScopedOption[],
): ExtensionScopedOption | null {
  return (
    options.find(
      (option) => option.renderer && SCHEDULED_TASK_OPTION_RENDERERS[option.renderer],
    ) ?? null
  );
}

export function renderScheduledTaskOptionField(
  props: ScheduledTaskOptionRendererProps,
) {
  const renderer = props.option.renderer
    ? SCHEDULED_TASK_OPTION_RENDERERS[props.option.renderer]
    : null;
  return renderer ? renderer(props) : null;
}

export function useScheduledTaskOptionValueLabels(
  option: ExtensionScopedOption | null,
  values: readonly string[],
): Record<string, string> {
  const [labels, setLabels] = useState<Record<string, string>>({});
  const renderer = option?.renderer || "";
  const valuesKey = values.filter(Boolean).sort().join("\u0000");

  useEffect(() => {
    const resolver = renderer ? SCHEDULED_TASK_OPTION_LABEL_RESOLVERS[renderer] : null;
    if (!resolver || option?.effective === false || !valuesKey) {
      setLabels({});
      return;
    }

    let cancelled = false;
    resolver(valuesKey.split("\u0000"))
      .then((nextLabels) => {
        if (!cancelled) setLabels(nextLabels);
      })
      .catch(() => {
        if (!cancelled) setLabels({});
      });
    return () => {
      cancelled = true;
    };
  }, [option?.effective, renderer, valuesKey]);

  return labels;
}
