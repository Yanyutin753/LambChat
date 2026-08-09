// ============================================
// Usage Types
// ============================================

export interface UsageLog {
  trace_id: string;
  session_id: string;
  user_id: string;
  username: string;
  agent_name: string;
  team_id: string;
  team_name: string;
  persona_preset_id: string;
  persona_preset_name: string;
  source: string;
  scheduled_task_id: string;
  scheduled_task_run_id: string;
  scheduled_task_trigger_type: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  duration: number;
  started_at: string | null;
  completed_at: string | null;
  status: string;
  step_count?: number;
  tool_calls?: number;
}

export interface UsageStats {
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cache_creation_tokens: number;
  total_cache_read_tokens: number;
  total_duration: number;
}

export interface UsageLogListResponse {
  items: UsageLog[];
  total: number;
  stats: UsageStats;
}

export interface UsageDashboardSummary {
  total_requests: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_duration: number;
  total_tool_calls: number;
  scheduled_runs: number;
  failed_requests: number;
  success_rate: number;
  avg_tokens_per_request: number;
  avg_duration_per_request: number;
  scheduled_share: number;
  cache_read_share: number;
  tool_calls_per_request: number;
  max_duration: number;
  peak_day: UsageDailyPoint | null;
}

export interface UsageDailyPoint {
  date: string;
  requests: number;
  tokens: number;
  duration: number;
  scheduled_runs: number;
  failed_requests: number;
  tool_calls: number;
}

export interface UsageRankingItem {
  id: string;
  name: string;
  requests: number;
  tokens: number;
  duration: number;
  input_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cache_read_share: number;
  zero_cache_requests: number;
}

export interface UsageDashboardResponse {
  summary: UsageDashboardSummary;
  daily: UsageDailyPoint[];
  top_agents: UsageRankingItem[];
  top_teams: UsageRankingItem[];
  top_personas: UsageRankingItem[];
  top_models: UsageRankingItem[];
  top_users: UsageRankingItem[];
  sources: UsageRankingItem[];
  triggers: UsageRankingItem[];
}
