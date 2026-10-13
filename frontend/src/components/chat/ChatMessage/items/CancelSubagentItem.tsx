import { SubagentControlItem } from "./SubagentControlItem";
import type { ToolDetailProps } from "./ToolLivePanelContent";

export function CancelSubagentItem(props: ToolDetailProps & { id?: string }) {
  return <SubagentControlItem {...props} toolName="cancel_subagent" />;
}
