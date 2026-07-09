import type { ComponentType } from "react";
import {
  AgentTeamDefaultTeamSelect,
  type ProjectOptionRendererProps,
} from "./projectOptionRendererComponents";

const PROJECT_OPTION_RENDERERS: Record<string, ComponentType<ProjectOptionRendererProps>> = {
  "agent_team.TeamSelectOption": AgentTeamDefaultTeamSelect,
};

export function renderProjectOptionField(props: ProjectOptionRendererProps) {
  const renderer = props.option.renderer
    ? PROJECT_OPTION_RENDERERS[props.option.renderer]
    : null;
  if (!renderer) return null;
  const Renderer = renderer;
  return <Renderer {...props} />;
}

export type { ProjectOptionRendererProps };
