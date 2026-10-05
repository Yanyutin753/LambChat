import type {
  ChannelConfigResponse,
  ChannelConfigStatus,
} from "../../../../types/channel";

export type FeishuConfigResponse = ChannelConfigResponse["config"] & {
  app_id: string;
  platform?: "feishu" | "lark";
  encrypt_key: string;
  verification_token: string;
  react_emoji: string;
  group_policy: "open" | "mention";
  stream_reply?: boolean;
  auto_transcribe_audio?: boolean;
  audio_transcribe_prompt?: string;
};

export type FeishuConfigStatus = ChannelConfigStatus;

export interface FeishuPanelProps {
  instanceId: string;
  initialConfig?: ChannelConfigResponse | null;
  initialStatus?: ChannelConfigStatus | null;
  isLoading?: boolean;
  onClose?: () => void;
}
