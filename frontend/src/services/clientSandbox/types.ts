export interface ClientSandboxCapabilities {
  execute: boolean;
  read_file: boolean;
  write_file: boolean;
  list: boolean;
}

export interface ClientSandboxRegisterMessage {
  type: "client_sandbox:register";
  device_id: string;
  name: string;
  platform: "tauri";
  os: string;
  app_version: string;
  workspace_root: string;
  capabilities: ClientSandboxCapabilities;
}

export interface ClientSandboxRequestMessage {
  type: "client_sandbox:request";
  request_id: string;
  session_id: string;
  operation: string;
  timeout_seconds: number;
  payload: Record<string, unknown>;
}

export interface ClientSandboxResponseMessage {
  type: "client_sandbox:response";
  request_id: string;
  ok: boolean;
  result?: Record<string, unknown>;
  error?: {
    code: string;
    message: string;
  };
}
