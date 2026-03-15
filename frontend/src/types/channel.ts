/**
 * Channel types and interfaces for multi-platform support.
 */

export type ChannelType =
  | "feishu"
  | "wechat"
  | "dingtalk"
  | "slack"
  | "telegram"
  | "discord";

export type ChannelCapability =
  | "websocket"
  | "webhook"
  | "send_message"
  | "send_image"
  | "send_file"
  | "reactions"
  | "group_chat"
  | "direct_message";

export interface ChannelMetadata {
  channel_type: ChannelType;
  display_name: string;
  description: string;
  icon: string;
  capabilities: ChannelCapability[];
  config_schema: Record<string, unknown>;
  requires_webhook: boolean;
  requires_websocket: boolean;
  setup_guide: string[];
  config_fields: ConfigField[];
}

export interface ConfigField {
  name: string;
  type: "text" | "password" | "select" | "toggle";
  title: string;
  description?: string;
  required?: boolean;
  sensitive?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  default?: string | boolean;
}

export interface ChannelConfigResponse {
  channel_type: ChannelType;
  user_id: string;
  enabled: boolean;
  config: Record<string, unknown>;
  capabilities: ChannelCapability[];
  created_at?: string;
  updated_at?: string;
}

export interface ChannelConfigStatus {
  channel_type: ChannelType;
  enabled: boolean;
  connected: boolean;
  error_message?: string;
  last_connected_at?: string;
}

export interface ChannelConfigCreate {
  channel_type: ChannelType;
  config: Record<string, unknown>;
}

export interface ChannelConfigUpdate {
  config: Record<string, unknown>;
  enabled?: boolean;
}

export interface ChannelTypeListResponse {
  types: ChannelMetadata[];
}

export interface ChannelListResponse {
  channels: ChannelConfigResponse[];
}
