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
  supports_sandbox?: boolean;
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

// ============================================
// Agent Config Types
// ============================================

// Agent configuration (global)
export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

// Global agent config response
export interface GlobalAgentConfigResponse {
  agents: AgentConfig[];
  available_agents: string[];
}

// Role's accessible agents
export interface RoleAgentAssignment {
  role_id: string;
  role_name: string;
  allowed_agents: string[];
}

// Response after updating role's accessible agents
export interface RoleAgentAssignmentResponse {
  role_id: string;
  role_name: string;
  allowed_agents: string[];
}

// User's default agent preference
export interface UserAgentPreference {
  default_agent_id: string | null;
}

// Response for user agent preference operations
export interface UserAgentPreferenceResponse {
  default_agent_id: string | null;
}
