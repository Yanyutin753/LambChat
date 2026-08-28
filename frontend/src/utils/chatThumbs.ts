/**
 * 聊天消息缩略图 URL 构造。
 *
 * 对话里的图片/文件卡片只加载小图，点击放大才取原图：
 * - 应用代理 URL（/api/upload/file/…）→ ?thumb=1（等比 m_lfit 小图）
 * - 阿里云直链 → x-oss-process 等比缩放参数
 * - 其余 URL（外链/数据 URI/不能缩的格式）返回 undefined，调用方直接用原图
 */

const THUMB_LFIT_PROCESS = "image/resize,m_lfit,w_560,h_560";

/** 这些格式保持原样：动图丢动画、矢量图本身很小 */
const SKIP_THUMB_EXT = new Set(["gif", "svg", "svgz", "apng"]);

const OSS_DIRECT_HOST_RE = /^([a-z0-9-]+\.)*aliyuncs\.com$/i;

function parseUrl(url: string): URL | null {
  try {
    return new URL(url, "https://placeholder.invalid");
  } catch {
    return null;
  }
}

function extFromUrl(url: string): string {
  const parsed = parseUrl(url);
  if (!parsed) return "";
  const dot = parsed.pathname.lastIndexOf(".");
  return dot >= 0 ? parsed.pathname.slice(dot + 1).toLowerCase() : "";
}

function isAppProxyUploadUrl(url: string): boolean {
  const parsed = parseUrl(url);
  return Boolean(parsed && parsed.pathname.includes("/api/upload/file/"));
}

function isOssDirectUrl(url: string): boolean {
  const parsed = parseUrl(url);
  return Boolean(
    parsed &&
      parsed.hostname !== "placeholder.invalid" &&
      OSS_DIRECT_HOST_RE.test(parsed.hostname),
  );
}

/** 等比缩略图 URL；不适用时返回 undefined（调用方直接加载原图）。 */
export function buildChatThumbUrl(
  url: string | undefined | null,
): string | undefined {
  if (!url) return undefined;
  if (SKIP_THUMB_EXT.has(extFromUrl(url))) return undefined;
  const joiner = url.includes("?") ? "&" : "?";
  if (isAppProxyUploadUrl(url)) {
    return `${url}${joiner}thumb=1`;
  }
  if (isOssDirectUrl(url)) {
    return `${url}${joiner}x-oss-process=${encodeURIComponent(THUMB_LFIT_PROCESS)}`;
  }
  return undefined;
}

/** 文件封面 URL（16:9，PDF 首页/表格前几行/图片裁剪/视频首帧）；不适用返回 undefined。 */
export function buildFileCoverUrl(
  url: string | undefined | null,
  opts: { t?: number } = {},
): string | undefined {
  if (!url || !isAppProxyUploadUrl(url)) return undefined;
  const joiner = url.includes("?") ? "&" : "?";
  let out = `${url}${joiner}cover=1`;
  if (opts.t !== undefined) out += `&t=${opts.t}`;
  return out;
}

/** 聊天附件卡片可展示服务端封面的文件类型（视频封面仅 Aliyun 生效，失败回退图标）。 */
export const CHAT_FILE_COVER_EXTS = new Set([
  "pdf",
  "xlsx",
  "xlsm",
  "mp4",
  "webm",
  "mov",
  "m4v",
]);

export function isChatCoverableFile(ext: string | undefined | null): boolean {
  return Boolean(ext && CHAT_FILE_COVER_EXTS.has(ext.toLowerCase()));
}
