import { MessageCircle, Webhook } from "lucide-react";
import type { ChannelType } from "../../../types/channel";
import bark from "../../../assets/channels/bark.png";
import dingtalk from "../../../assets/channels/dingtalk.svg";
import discord from "../../../assets/channels/discord.png";
import feishu from "../../../assets/channels/feishu.svg";
import gotify from "../../../assets/channels/gotify.png";
import ntfy from "../../../assets/channels/ntfy.svg";
import pushover from "../../../assets/channels/pushover.ico";
import pushplus from "../../../assets/channels/pushplus.ico";
import serverchan from "../../../assets/channels/serverchan.png";
import slack from "../../../assets/channels/slack.png";
import telegram from "../../../assets/channels/telegram.svg";
import wecom from "../../../assets/channels/wecom.png";
import wechat from "../../../assets/channels/wechat.ico";

const CHANNEL_LOGOS: Partial<Record<ChannelType, string>> = {
  bark,
  dingtalk,
  discord,
  feishu,
  gotify,
  ntfy,
  pushover,
  pushplus,
  serverchan,
  slack,
  telegram,
  wecom,
  wechat,
  weixin: wechat,
};

/** Channel identity comes from its stable type, not a backend Lucide hint. */
export function ChannelIcon({
  channelType,
  size = 20,
}: {
  channelType: string;
  size?: number;
}) {
  if (channelType === "webhook") {
    return <Webhook size={size} aria-hidden="true" className="shrink-0 text-theme-text-secondary" />;
  }
  const src = Object.hasOwn(CHANNEL_LOGOS, channelType)
    ? CHANNEL_LOGOS[channelType as ChannelType]
    : undefined;
  return src ? (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      className="shrink-0 object-contain"
      draggable={false}
    />
  ) : (
    <MessageCircle
      size={size}
      aria-hidden="true"
      className="shrink-0 text-theme-text-secondary"
    />
  );
}
