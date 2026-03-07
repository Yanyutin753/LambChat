// ============================================
// Agent Types
// ============================================

export interface AgentOption {
  type: "boolean" | "string" | "number";
  default: boolean | string | number;
  label: string;
  label_key?: string; // i18n translation key for label
  description?: string;
  description_key?: string; // i18n translation key for description
  icon?: string; // lucide-react icon name (e.g., "Brain", "Zap", "Settings")
  options?: { value: string | number; label: string }[]; // For select/dropdown type options
}

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  sort_order?: number;
  options?: Record<string, AgentOption>;
}

export interface AgentListResponse {
  agents: AgentInfo[];
  count: number;
  default_agent?: string;
}

// Workflow event types
export interface WorkflowStepData {
  step_id: string;
  step_name: string;
  agent_id?: string;
  status?: "running" | "completed" | "failed";
  result?: string;
}
