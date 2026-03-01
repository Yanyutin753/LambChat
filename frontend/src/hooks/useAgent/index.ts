// Re-export types
export type {
  EventType,
  StreamEvent,
  EventData,
  UseAgentOptions,
  SubagentStackItem,
  HistoryEventData,
  HistoryEvent,
  UseAgentReturn,
  BackendSession,
} from "./types";

export { API_BASE, DEFAULT_AGENT } from "./types";

// Re-export message parts utilities
export {
  addPartToDepth,
  findAndAddToSubagent,
  updateSubagentResult,
  updateSubagentResultInParts,
  updateToolResultInDepth,
  updateToolResultInParts,
  createToolPart,
  createThinkingPart,
  createSubagentPart,
} from "./messageParts";

// Re-export history loader utilities
export {
  convertAttachments,
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
} from "./historyLoader";
