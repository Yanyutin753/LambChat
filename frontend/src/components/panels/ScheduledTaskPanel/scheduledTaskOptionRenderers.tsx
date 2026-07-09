import { useEffect, useState } from "react";
import type { ComponentType } from "react";
import { teamApi } from "../../../services/api/team";
import type { ExtensionScopedOption } from "../../../types";
import {
  AgentTeamScheduledTaskTeamSelect,
  type ScheduledTaskOptionRendererProps,
} from "./scheduledTaskOptionRendererComponents";

type ScheduledTaskOptionRenderer = ComponentType<ScheduledTaskOptionRendererProps>;

type ScheduledTaskOptionLabelResolver = (
  values: readonly string[],
) => Promise<Record<string, string>>;

const SCHEDULED_TASK_OPTION_RENDERERS: Record<string, ScheduledTaskOptionRenderer> = {
  "agent_team.TeamSelectOption": AgentTeamScheduledTaskTeamSelect,
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
  if (!renderer) return null;
  const Renderer = renderer;
  return <Renderer {...props} />;
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

export type { ScheduledTaskOptionRendererProps };
