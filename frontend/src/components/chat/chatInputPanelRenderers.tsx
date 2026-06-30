import { type ReactElement } from "react";
import { TeamPickerModal } from "../team/TeamPickerModal";
import { WorkflowPickerModal } from "../../plugins/workflow/WorkflowPickerModal";
import type { CoreChatInputPanelContribution } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";
import { pluginOptionFromValues } from "../../extensions/pluginOptions";

const WORKFLOW_PLUGIN_SESSION_VERSION_KEY = "SELECTED_WORKFLOW_VERSION_ID";
const WORKFLOW_PLUGIN_SESSION_INPUT_KEY = "SELECTED_WORKFLOW_INPUT_JSON";

export interface ChatInputPanelRendererProps {
  contribution: CoreChatInputPanelContribution;
  activePanel: string | null;
  onActivePanelChange: (panel: string | null) => void;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  onNavigate: (path: string) => void;
}

function AgentTeamPickerRenderer({
  contribution,
  activePanel,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
  onNavigate,
}: ChatInputPanelRendererProps): ReactElement | null {
  const optionPath = contribution.optionBinding;
  if (!optionPath || !onPluginOptionChange) return null;
  const pluginSelectedTeamId =
    pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key);
  const effectiveSelectedTeamId =
    typeof pluginSelectedTeamId === "string" ? pluginSelectedTeamId : null;
  const handleSelectTeam = (teamId: string | null) => {
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, teamId);
  };
  const navigateToCreate = contribution.createPath
    ? () => onNavigate(contribution.createPath as string)
    : undefined;
  const navigateToManage = contribution.managePath
    ? () => onNavigate(contribution.managePath as string)
    : navigateToCreate;
  return (
    <TeamPickerModal
      isOpen={activePanel === contribution.id}
      selectedTeamId={effectiveSelectedTeamId ?? null}
      onSelect={handleSelectTeam}
      onClose={() => onActivePanelChange(null)}
      onCreateNew={navigateToCreate}
      onManageTeams={navigateToManage}
    />
  );
}

function WorkflowPluginPickerRenderer({
  contribution,
  activePanel,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
  onNavigate,
}: ChatInputPanelRendererProps): ReactElement | null {
  const optionPath = contribution.optionBinding;
  if (!optionPath || !onPluginOptionChange) return null;
  const pluginSelectedWorkflowId = pluginOptionFromValues(
    pluginOptionValues,
    optionPath.pluginId,
    optionPath.key,
  );
  const effectiveSelectedWorkflowId =
    typeof pluginSelectedWorkflowId === "string" && pluginSelectedWorkflowId
      ? pluginSelectedWorkflowId
      : null;
  const pluginSelectedVersionId = pluginOptionFromValues(
    pluginOptionValues,
    optionPath.pluginId,
    WORKFLOW_PLUGIN_SESSION_VERSION_KEY,
  );
  const effectiveSelectedVersionId =
    typeof pluginSelectedVersionId === "string" && pluginSelectedVersionId
      ? pluginSelectedVersionId
      : null;
  const selectedWorkflowInput = pluginOptionFromValues(
    pluginOptionValues,
    optionPath.pluginId,
    WORKFLOW_PLUGIN_SESSION_INPUT_KEY,
  );
  const handleSelectWorkflow = (workflowId: string | null) => {
    if (!workflowId || workflowId !== effectiveSelectedWorkflowId) {
      onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_VERSION_KEY, null);
      onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_INPUT_KEY, null);
    }
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, workflowId);
  };
  const handleSelectVersion = (versionId: string | null) => {
    onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_VERSION_KEY, versionId);
  };
  const handleWorkflowInputChange = (value: Record<string, unknown> | null) => {
    onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_INPUT_KEY, value);
  };
  const navigateToCreate = contribution.createPath
    ? () => onNavigate(contribution.createPath as string)
    : undefined;
  const navigateToManage = contribution.managePath
    ? () => onNavigate(contribution.managePath as string)
    : contribution.createPath
      ? () => onNavigate(contribution.createPath as string)
      : undefined;
  const navigateToWorkflowEditor = (workflowId: string) => {
    onNavigate(`/workflows/${encodeURIComponent(workflowId)}/editor`);
  };
  return (
    <WorkflowPickerModal
      isOpen={activePanel === contribution.id}
      selectedWorkflowId={effectiveSelectedWorkflowId}
      selectedVersionId={effectiveSelectedVersionId}
      selectedInput={selectedWorkflowInput}
      onSelect={handleSelectWorkflow}
      onSelectVersion={handleSelectVersion}
      onInputChange={handleWorkflowInputChange}
      onClose={() => onActivePanelChange(null)}
      onCreateWorkflow={navigateToCreate}
      onManageWorkflows={navigateToManage}
      onEditWorkflow={navigateToWorkflowEditor}
    />
  );
}

export const CHAT_INPUT_PANEL_RENDERERS: Record<
  string,
  (props: ChatInputPanelRendererProps) => ReactElement | null
> = {
  "agent_team.TeamPickerModal": AgentTeamPickerRenderer,
  "workflow.WorkflowPickerModal": WorkflowPluginPickerRenderer,
};
