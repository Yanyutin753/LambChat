// Model Config Types

export interface ModelConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  api_key?: string | null;
  api_base?: string | null;
  // Flat model fields (from provider config)
  value?: string;
  label?: string;
  provider?: string;
}

export interface ModelProviderConfig {
  provider: string;
  label: string;
  base_url?: string;
  api_key?: string | null;
  has_api_key?: boolean;
  clear_api_key?: boolean;
  temperature: number;
  max_tokens: number;
  max_retries: number;
  retry_delay: number;
  models: ModelConfig[];
}

export interface ProviderConfigResponse {
  providers: ModelProviderConfig[];
  flat_models: ModelConfig[];
  legacy_migration_applied: boolean;
  legacy_inherited_providers: string[];
}

export interface ProviderConfig {
  name: string;
  display_name: string;
  api_key?: string | null;
  api_base?: string | null;
  enabled: boolean;
}

export interface GlobalModelConfigResponse {
  models: ModelConfig[];
  available_models: string[];
}

export interface RoleModelAssignment {
  role_id: string;
  role_name: string;
  allowed_models: string[];
}

export interface RoleModelAssignmentResponse {
  role_id: string;
  role_name: string;
  allowed_models: string[];
}

export interface UserAllowedModelsResponse {
  models: string[];
}

// ============================================
// Helper functions
// ============================================

/** Resolve the best available model value given a preferred value and available models. */
export function resolveAvailableModelValue(
  preferred: string | null | undefined,
  availableModels: { value: string }[] | null,
  fallback: string,
): string {
  if (!preferred) return fallback;
  if (!availableModels || availableModels.length === 0) return preferred || fallback;
  if (availableModels.some((m) => m.value === preferred)) return preferred;
  return fallback || availableModels[0].value;
}

// Provider metadata for UI display
const PROVIDER_META: Record<string, { color: string; display_name: string }> = {
  anthropic: { color: "#d4a574", display_name: "Anthropic" },
  openai: { color: "#10a37f", display_name: "OpenAI" },
  google: { color: "#4285f4", display_name: "Google" },
  gemini: { color: "#4285f4", display_name: "Google Gemini" },
  azure: { color: "#0078d4", display_name: "Azure OpenAI" },
  deepseek: { color: "#4f46e5", display_name: "DeepSeek" },
  groq: { color: "#f55036", display_name: "Groq" },
  mistral: { color: "#ff7000", display_name: "Mistral" },
  ollama: { color: "#6366f1", display_name: "Ollama" },
  cohere: { color: "#39594d", display_name: "Cohere" },
  zai: { color: "#3b82f6", display_name: "ZAI" },
  aws_bedrock: { color: "#ff9900", display_name: "AWS Bedrock" },
};

export function getProviderMeta(
  provider: string,
): { color: string; display_name: string } | undefined {
  return PROVIDER_META[provider];
}
