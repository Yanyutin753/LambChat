import { useEffect, useState, type ComponentType, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Workflow } from "lucide-react";
import type { CoreChatInputOptionContribution } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";
import { pluginOptionFromValues } from "../../extensions/pluginOptions";
import {
  workflowApi,
  type WorkflowIoContractResponse,
  type WorkflowSummary,
  type WorkflowVersionSummary,
} from "../../plugins/workflow/api";
import { workflowCallableInterfaceLabels } from "../../plugins/workflow/contractUtils";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";
import { ToolbarChip } from "./ToolbarChip";

const WORKFLOW_PLUGIN_SESSION_VERSION_KEY = "SELECTED_WORKFLOW_VERSION_ID";
const WORKFLOW_PLUGIN_SESSION_INPUT_KEY = "SELECTED_WORKFLOW_INPUT_JSON";

function schemaFieldLabels(schema: Record<string, unknown> | null | undefined): string[] {
  const properties = schema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return [];
  }
  return Object.entries(properties as Record<string, unknown>).map(([name, rawSchema]) => {
    const schemaObject = rawSchema && typeof rawSchema === "object" && !Array.isArray(rawSchema)
      ? (rawSchema as Record<string, unknown>)
      : {};
    const type = typeof schemaObject.type === "string" ? schemaObject.type : "unknown";
    return `${name}: ${type}`;
  });
}

function workflowContractSummary(
  contract: WorkflowIoContractResponse | null,
  t: (key: string) => string,
): string {
  if (!contract) return "";
  const interfaceLabels = workflowCallableInterfaceLabels(contract.interface);
  const inputs = schemaFieldLabels(contract.input_schema).slice(0, 3);
  const outputs = schemaFieldLabels(contract.output_schema).slice(0, 3);
  const noneLabel = t("workflowPlugin.chat.none");
  const inputLabel = inputs.length > 0 ? inputs.join(", ") : noneLabel;
  const outputLabel = outputs.length > 0 ? outputs.join(", ") : noneLabel;
  return `${t("workflowPlugin.chat.entry")} ${interfaceLabels.entry} -> ${t(
    "workflowPlugin.chat.exit",
  )} ${interfaceLabels.exit} | ${t("workflowPlugin.chat.inputs")} ${inputLabel} -> ${t(
    "workflowPlugin.chat.outputs",
  )} ${outputLabel}`;
}

export interface ChatInputSelectedRendererProps {
  option: CoreChatInputOptionContribution;
  activePanel: string | null;
  onActivePanelChange: (panel: string | null) => void;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  fallbackLabel: string;
}

export interface ChatInputSelectedRendererEntry {
  hasSelection: (props: ChatInputSelectedRendererProps) => boolean;
  Component: ComponentType<ChatInputSelectedRendererProps>;
}

function AgentTeamSelectedChip({
  option,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
  fallbackLabel,
}: ChatInputSelectedRendererProps): ReactElement | null {
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const optionPath = option.optionBinding;
  const pluginSelectedTeamId =
    optionPath
      ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
      : null;
  const effectiveSelectedTeamId =
    typeof pluginSelectedTeamId === "string" && pluginSelectedTeamId
      ? pluginSelectedTeamId
      : null;
  const clearSelection = () => {
    if (!optionPath) return;
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, null);
  };

  useEffect(() => {
    if (!effectiveSelectedTeamId) {
      setSelectedTeam(null);
      return;
    }
    let cancelled = false;
    teamApi
      .get(effectiveSelectedTeamId)
      .then((team) => {
        if (!cancelled) setSelectedTeam(team);
      })
      .catch(() => {
        if (!cancelled) setSelectedTeam(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectedTeamId]);

  if (!optionPath || !effectiveSelectedTeamId || !onPluginOptionChange) return null;
  const label = selectedTeam?.name ?? fallbackLabel;
  return (
    <ToolbarChip
      icon={
        <TeamAvatar
          avatar={selectedTeam?.avatar}
          fallbackAvatar={selectedTeam ? getTeamFallbackAvatar(selectedTeam) : null}
          fallbackTag={selectedTeam ? getTeamFallbackTag(selectedTeam) : ""}
          label={label}
          className="team-toolbar-avatar transition-opacity group-hover:opacity-0"
          iconSize={18}
        />
      }
      label={label}
      onClick={() => option.panel && onActivePanelChange(option.panel)}
      onClear={clearSelection}
    />
  );
}

function WorkflowPluginSelectedChip({
  option,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
}: ChatInputSelectedRendererProps): ReactElement | null {
  const { t } = useTranslation();
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowSummary | null>(
    null,
  );
  const [selectedVersion, setSelectedVersion] = useState<WorkflowVersionSummary | null>(
    null,
  );
  const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null);
  const optionPath = option.optionBinding;
  const pluginSelectedWorkflowId = optionPath
    ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
    : null;
  const effectiveSelectedWorkflowId =
    typeof pluginSelectedWorkflowId === "string" && pluginSelectedWorkflowId
      ? pluginSelectedWorkflowId
      : null;
  const pluginSelectedVersionId = optionPath
    ? pluginOptionFromValues(
        pluginOptionValues,
        optionPath.pluginId,
        WORKFLOW_PLUGIN_SESSION_VERSION_KEY,
      )
    : null;
  const effectiveSelectedVersionId =
    typeof pluginSelectedVersionId === "string" && pluginSelectedVersionId
      ? pluginSelectedVersionId
      : null;
  const pluginSelectedInput = optionPath
    ? pluginOptionFromValues(
        pluginOptionValues,
        optionPath.pluginId,
        WORKFLOW_PLUGIN_SESSION_INPUT_KEY,
      )
    : null;
  const hasSelectedInput =
    Boolean(pluginSelectedInput) &&
    (typeof pluginSelectedInput !== "object" ||
      (!Array.isArray(pluginSelectedInput) &&
        Object.keys(pluginSelectedInput as Record<string, unknown>).length > 0));
  const clearSelection = () => {
    if (!optionPath) return;
    onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_VERSION_KEY, null);
    onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_INPUT_KEY, null);
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, null);
  };

  useEffect(() => {
    if (!effectiveSelectedWorkflowId) {
      setSelectedWorkflow(null);
      setIoContract(null);
      return;
    }
    let cancelled = false;
    workflowApi
      .get(effectiveSelectedWorkflowId)
      .then((workflow) => {
        if (!cancelled) setSelectedWorkflow(workflow);
      })
      .catch(() => {
        if (!cancelled) setSelectedWorkflow(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectedWorkflowId]);

  useEffect(() => {
    if (!effectiveSelectedWorkflowId) {
      setIoContract(null);
      return;
    }
    let cancelled = false;
    workflowApi
      .ioContract(effectiveSelectedWorkflowId, effectiveSelectedVersionId)
      .then((contract) => {
        if (!cancelled) setIoContract(contract);
      })
      .catch(() => {
        if (!cancelled) setIoContract(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectedVersionId, effectiveSelectedWorkflowId]);

  useEffect(() => {
    if (!effectiveSelectedWorkflowId || !effectiveSelectedVersionId) {
      setSelectedVersion(null);
      return;
    }
    let cancelled = false;
    workflowApi
      .versions(effectiveSelectedWorkflowId)
      .then((response) => {
        if (!cancelled) {
          setSelectedVersion(
            response.versions.find(
              (version) => version.version_id === effectiveSelectedVersionId,
            ) ?? null,
          );
        }
      })
      .catch(() => {
        if (!cancelled) setSelectedVersion(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectedVersionId, effectiveSelectedWorkflowId]);

  if (!optionPath || !effectiveSelectedWorkflowId || !onPluginOptionChange) {
    return null;
  }
  const workflowLabel = selectedWorkflow?.name ?? effectiveSelectedWorkflowId;
  const versionLabel = effectiveSelectedVersionId
    ? selectedVersion
      ? `v${selectedVersion.version_number}`
      : effectiveSelectedVersionId
    : null;
  const label = versionLabel ? `${workflowLabel} / ${versionLabel}` : workflowLabel;
  const contractSummary = workflowContractSummary(ioContract, t);
  const inputSummary = hasSelectedInput ? t("workflowPlugin.chat.inputOverrideSet") : "";
  const summaryParts = [contractSummary, inputSummary].filter(Boolean);
  const chipLabel = summaryParts.length > 0 ? `${label} - ${summaryParts.join(" | ")}` : label;
  const chipTitle = summaryParts.length > 0 ? `${label}\n${summaryParts.join("\n")}` : label;
  return (
    <ToolbarChip
      icon={
        <Workflow
          size={18}
          className="text-[var(--theme-primary)] transition-opacity group-hover:opacity-0"
        />
      }
      label={chipLabel}
      title={chipTitle}
      onClick={() => option.panel && onActivePanelChange(option.panel)}
      onClear={clearSelection}
    />
  );
}

export const CHAT_INPUT_SELECTED_RENDERERS: Record<
  string,
  ChatInputSelectedRendererEntry
> = {
  "agent_team.SelectedTeamChip": {
    hasSelection: ({ option, pluginOptionValues, onPluginOptionChange }) => {
      const optionPath = option.optionBinding;
      const pluginSelectedTeamId = optionPath
        ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
        : null;
      return Boolean(
        onPluginOptionChange &&
          typeof pluginSelectedTeamId === "string" &&
          pluginSelectedTeamId,
      );
    },
    Component: AgentTeamSelectedChip,
  },
  "workflow.SelectedWorkflowChip": {
    hasSelection: ({ option, pluginOptionValues, onPluginOptionChange }) => {
      const optionPath = option.optionBinding;
      const pluginSelectedWorkflowId = optionPath
        ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
        : null;
      return Boolean(
        onPluginOptionChange &&
          typeof pluginSelectedWorkflowId === "string" &&
          pluginSelectedWorkflowId,
      );
    },
    Component: WorkflowPluginSelectedChip,
  },
};
