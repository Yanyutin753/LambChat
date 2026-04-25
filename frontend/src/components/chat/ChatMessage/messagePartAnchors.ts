export function createToolPartAnchorId(
  ownerId: string,
  partIndex: number,
): string {
  return `tool-part:${ownerId}:${partIndex}`;
}

export function createSubagentAnchorOwnerId(agentId: string): string {
  return `subagent:${agentId}`;
}

export function createSubagentPanelKey(agentId: string): string {
  return `subagent-${agentId}`;
}
