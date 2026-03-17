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

export { API_BASE } from "./types";

// Re-export message parts utilities
export {
  addPartToDepth,
  findAndAddToSubagent,
  updateSubagentResult,
  updateSubagentResultInParts,
  updateToolResultInDepth,
  updateToolResultInPartsById,
  createToolPart,
  createThinkingPart,
  createSubagentPart,
  clearAllLoadingStates,
} from "./messageParts";

// Re-export event processor
export { convertAttachments, processMessageEvent } from "./eventProcessor";
export type { ProcessMessageEventResult } from "./eventProcessor";

// Re-export history loader utilities
export {
  reconstructMessagesFromEvents,
  getLastEventTimestamp,
} from "./historyLoader";
