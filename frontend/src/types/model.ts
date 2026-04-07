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

// Built-in provider metadata
export const PROVIDER_META: Record<string, ProviderMeta> = {
  anthropic: {
    name: "anthropic",
    display_name: "Anthropic",
    icon: "anthropic",
    color: "#FF6B6B",
    website: "https://anthropic.com",
    description:
      "Claude models - best for reasoning, analysis, and creative tasks",
  },
  google: {
    name: "google",
    display_name: "Google AI",
    icon: "google",
    color: "#4285F4",
    website: "https://ai.google.dev",
    description: "Gemini models - Google's most capable AI model",
  },
  openai: {
    name: "openai",
    display_name: "OpenAI",
    icon: "openai",
    color: "#10A37F",
    website: "https://openai.com",
    description: "GPT models - industry standard for general purpose",
  },
  azure: {
    name: "azure",
    display_name: "Azure OpenAI",
    icon: "azure",
    color: "#0078D4",
    website:
      "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
    description: "Microsoft Azure-hosted OpenAI models - enterprise ready",
  },
  bedrock: {
    name: "bedrock",
    display_name: "AWS Bedrock",
    icon: "aws",
    color: "#FF9900",
    website: "https://aws.amazon.com/bedrock",
    description:
      "Amazon's managed service for AI models - Claude, Llama, Mistral",
  },
  groq: {
    name: "groq",
    display_name: "Groq",
    icon: "groq",
    color: "#FF4B4B",
    website: "https://console.groq.com",
    description: "Fast inference - Llama, Mixtral, Gemma at lightning speed",
  },
  deepseek: {
    name: "deepseek",
    display_name: "DeepSeek",
    icon: "deepseek",
    color: "#0055FF",
    website: "https://deepseek.com",
    description: "DeepSeek V3 & Coder - powerful and cost-effective",
  },
  mistral: {
    name: "mistral",
    display_name: "Mistral AI",
    icon: "mistral",
    color: "#FF6B35",
    website: "https://mistral.ai",
    description: "Mistral and Mixtral - efficient open models",
  },
  cohere: {
    name: "cohere",
    display_name: "Cohere",
    icon: "cohere",
    color: "#FF6B35",
    website: "https://cohere.com",
    description: "Command R series - optimized for RAG and tool use",
  },
  ollama: {
    name: "ollama",
    display_name: "Ollama (Local)",
    icon: "ollama",
    color: "#800000",
    website: "https://ollama.com",
    description: "Local LLM inference - run models on your own hardware",
  },
};

export const ALL_PROVIDER_NAMES = Object.keys(PROVIDER_META);

export function getProviderMeta(name: string): ProviderMeta | undefined {
  return PROVIDER_META[name];
}
