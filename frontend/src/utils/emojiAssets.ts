/**
 * Fluent Emoji 静态资源统一出口。
 *
 * 所有 emoji 图标 URL 一律经由本模块产出：主源用 npmmirror（国内友好），
 * 加载失败时由 ImageWithSkeleton 按本模块派生的备用 CDN 链（jsdelivr →
 * unpkg）自动换源重试，避免单一 CDN 抖动导致头像/图标裂图。
 */

import { getFluentEmojiCDN } from "@lobehub/fluent-emoji";

export type EmojiAssetType = "anim" | "3d" | "flat" | "modern" | "mono";

const NPM_MIRROR_EMOJI_RE =
  /^https:\/\/registry\.npmmirror\.com\/(@lobehub\/fluent-emoji-[a-z0-9-]+)\/latest\/files\/(assets\/[0-9a-f-]+\.(?:webp|svg))$/;

/** 取 emoji 图标主源 URL（npmmirror，国内访问最稳）。 */
export function getEmojiAssetUrl(
  emoji: string,
  type: EmojiAssetType = "3d",
): string {
  return getFluentEmojiCDN(emoji, { type });
}

/** 由 npmmirror 形态的 emoji URL 派生备用 CDN 链；非 emoji URL 返回空。 */
export function getEmojiFallbackUrls(url: string): string[] {
  const match = url.match(NPM_MIRROR_EMOJI_RE);
  if (!match) return [];
  const [, pkg, assetPath] = match;
  return [
    `https://cdn.jsdelivr.net/npm/${pkg}@latest/${assetPath}`,
    `https://unpkg.com/${pkg}@latest/${assetPath}`,
  ];
}
