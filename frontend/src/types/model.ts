// Model Config Types

export interface ModelConfig {
  id: string;
  name: string;
  description: string;
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
