import { SubagentControlItem } from "./SubagentControlItem";
import type { ToolDetailProps } from "./ToolLivePanelContent";

export function ListSubagentsItem(props: ToolDetailProps & { id?: string }) {
  return <SubagentControlItem {...props} toolName="list_subagents" />;
}
