// Model Config Types

export interface ModelConfig {
  value: string;
  label: string;
  description: string;
  enabled: boolean;
  provider?: string;
}

export interface ModelProviderConfig {
  provider: string;
  label: string;
  base_url?: string;
  api_key?: string;
  has_api_key?: boolean;
  clear_api_key?: boolean;
  // Per-provider defaults (can be overridden per-request)
  temperature?: number;
  max_tokens?: number;
  max_retries?: number;
  retry_delay?: number;
  models: ModelConfig[];
}

export interface ProviderModelConfigResponse {
  providers: ModelProviderConfig[];
  flat_models: ModelConfig[];
  available_models: string[];
  legacy_migration_applied: boolean;
  legacy_inherited_providers: string[];
}

export interface ProviderModelConfigUpdate {
  providers: ModelProviderConfig[];
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
// Provider UI Metadata
// ============================================

export interface ProviderMeta {
  name: string;
  display_name: string;
  icon: string;
  color: string;
  website: string;
  description: string;
}

export const UNIFIED_PROVIDER_COLOR = "#78716C";

// Built-in provider metadata
export const PROVIDER_META: Record<string, ProviderMeta> = {
  anthropic: {
    name: "anthropic",
    display_name: "Anthropic",
    icon: "anthropic",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://anthropic.com",
    description:
      "Claude models - best for reasoning, analysis, and creative tasks",
  },
  google: {
    name: "google",
    display_name: "Google AI",
    icon: "google",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://ai.google.dev",
    description: "Gemini models - Google's most capable AI model",
  },
  openai: {
    name: "openai",
    display_name: "OpenAI",
    icon: "openai",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://openai.com",
    description: "GPT models - industry standard for general purpose",
  },
  azure: {
    name: "azure",
    display_name: "Azure OpenAI",
    icon: "azure",
    color: UNIFIED_PROVIDER_COLOR,
    website:
      "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
    description: "Microsoft Azure-hosted OpenAI models - enterprise ready",
  },
  bedrock: {
    name: "bedrock",
    display_name: "AWS Bedrock",
    icon: "aws",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://aws.amazon.com/bedrock",
    description:
      "Amazon's managed service for AI models - Claude, Llama, Mistral",
  },
  groq: {
    name: "groq",
    display_name: "Groq",
    icon: "groq",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://console.groq.com",
    description: "Fast inference - Llama, Mixtral, Gemma at lightning speed",
  },
  deepseek: {
    name: "deepseek",
    display_name: "DeepSeek",
    icon: "deepseek",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://deepseek.com",
    description: "DeepSeek V3 & Coder - powerful and cost-effective",
  },
  mistral: {
    name: "mistral",
    display_name: "Mistral AI",
    icon: "mistral",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://mistral.ai",
    description: "Mistral and Mixtral - efficient open models",
  },
  cohere: {
    name: "cohere",
    display_name: "Cohere",
    icon: "cohere",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://cohere.com",
    description: "Command R series - optimized for RAG and tool use",
  },
  ollama: {
    name: "ollama",
    display_name: "Ollama (Local)",
    icon: "ollama",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://ollama.com",
    description: "Local LLM inference - run models on your own hardware",
  },
  zai: {
    name: "zai",
    display_name: "ChatGLM",
    icon: "zhipu",
    color: UNIFIED_PROVIDER_COLOR,
    website: "https://open.bigmodel.cn",
    description: "ChatGLM models - GLM family models from Zhipu AI",
  },
};

export const ALL_PROVIDER_NAMES = Object.keys(PROVIDER_META);

export function getProviderMeta(name: string): ProviderMeta | undefined {
  return PROVIDER_META[name];
}

export function areModelValuesCompatible(
  modelA?: string | null,
  modelB?: string | null,
): boolean {
  if (!modelA || !modelB) return false;
  if (modelA === modelB) return true;
  if (modelA.includes("/") && !modelB.includes("/")) {
    return modelA.endsWith(`/${modelB}`);
  }
  if (modelB.includes("/") && !modelA.includes("/")) {
    return modelB.endsWith(`/${modelA}`);
  }
  return false;
}

export function resolveAvailableModelValue<
  TModel extends { value: string },
>(
  preferred: string | null | undefined,
  models: readonly TModel[] | null | undefined,
  fallback = "",
): string {
  const available = models ?? [];

  if (available.length === 0) {
    return preferred || fallback;
  }

  const matchValue = (candidate?: string | null) => {
    if (!candidate) return null;
    return (
      available.find((model) => model.value === candidate) ||
      available.find((model) =>
        areModelValuesCompatible(model.value, candidate),
      ) ||
      null
    );
  };

  return (
    matchValue(preferred)?.value ||
    matchValue(fallback)?.value ||
    available[0]?.value ||
    ""
  );
}
