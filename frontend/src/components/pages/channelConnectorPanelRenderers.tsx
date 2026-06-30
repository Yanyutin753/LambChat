import { FeishuPanel } from "../panels/channel/feishu/FeishuPanel";
import type { ReactElement } from "react";
import type {
  ChannelConfigResponse,
  ChannelConfigStatus,
} from "../../types/channel";

export interface ChannelConnectorPanelRendererProps {
  instanceId: string;
  initialConfig?: ChannelConfigResponse;
  initialStatus?: ChannelConfigStatus | null;
  isLoading?: boolean;
  onClose: () => void;
}

export type ChannelConnectorPanelRenderer = (
  props: ChannelConnectorPanelRendererProps,
) => ReactElement;

export const CHANNEL_CONNECTOR_PANEL_RENDERERS: Record<
  string,
  ChannelConnectorPanelRenderer
> = {
  "feishu_connector.FeishuPanel": (props) => <FeishuPanel {...props} />,
};

export function getChannelConnectorPanelRenderer(
  rendererId?: string | null,
): ChannelConnectorPanelRenderer | null {
  if (!rendererId) return null;
  return CHANNEL_CONNECTOR_PANEL_RENDERERS[rendererId] ?? null;
}
