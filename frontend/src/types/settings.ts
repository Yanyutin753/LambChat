// ============================================
// Settings Types
// ============================================

export type SettingType =
  | "string"
  | "text"
  | "number"
  | "boolean"
  | "json"
  | "select";
export type SettingCategory =
  | "frontend"
  | "agent"
  | "llm"
  | "session"
  | "skills"
  | "mongodb"
  | "redis"
  | "checkpoint"
  | "long_term_storage"
  | "security"
  | "email"
  | "captcha"
  | "s3"
  | "file_upload"
  | "sandbox"
  | "tools"
  | "tracing"
  | "user"
  | "oauth"
  | "memory"
  | "memory_embedding"
  | "memory_search"
  | "memory_storage";

// Setting dependency condition
export interface SettingDependsOn {
  key: string; // Parent setting key
  value: string | number | boolean; // Expected value for visibility
}

// JSON schema field definition
export interface JsonSchemaField {
  name: string;
  type: "text" | "password" | "number" | "toggle" | "select";
  label: string; // i18n key
  placeholder?: string;
  required?: boolean;
  options?: string[];
}

// JSON schema for structured editing of JSON-type settings
export interface JsonSchema {
  type: "array" | "object";
  item_label?: string; // i18n key for array items
  key_label?: string; // i18n key for object keys (object type)
  value_type?: "array"; // for object values that are arrays
  key_options?: string[]; // allowed keys for object type
  fields: JsonSchemaField[];
}

export interface SettingItem {
  key: string;
  value: string | number | boolean | object;
  type: SettingType;
  category: SettingCategory;
  subcategory: string;
  description: string;
  default_value: string | number | boolean | object;
  requires_restart: boolean;
  is_sensitive: boolean;
  frontend_visible: boolean;
  depends_on?: string | SettingDependsOn; // Key of parent setting or condition object
  options?: string[]; // Available options for SELECT type
  json_schema?: JsonSchema; // Schema for JSON-type settings
  updated_at?: string;
  updated_by?: string;
}

export interface SettingsResponse {
  settings: Record<SettingCategory, SettingItem[]>;
}

export interface SettingUpdate {
  value: string | number | boolean | object;
}

export interface SettingResetResponse {
  message: string;
  reset_count: number;
}

// ============================================
// Model Types
// ============================================

export interface ModelProfile {
  max_input_tokens?: number;
}

export interface AvailableModelConfig {
  value: string;
  provider?: string;
  label: string;
  description?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  profile?: ModelProfile;
}

// Backward compatibility alias
export type AvailableModel = AvailableModelConfig;
