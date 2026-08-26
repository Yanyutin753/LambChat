import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Message, MessagePart, ToolPart } from "../../../types";
import { getFullUrl } from "../../../services/api/config";
import { isImageFile } from "../../documents/utils";
import { ImageViewer } from "../../common/ImageViewer";
import { extractGeneratedImageResults } from "./items/toolImageResults";

export interface SessionImageGalleryItem {
  id: string;
  src: string;
  alt?: string;
  group: SessionImageGalleryGroup;
}

export type SessionImageGalleryGroup = "conversation" | "reveal-file";

interface SessionImageGalleryContextValue {
  openImage: (
    src: string,
    alt?: string,
    options?: { group?: SessionImageGalleryGroup },
  ) => void;
}

const SessionImageGalleryContext =
  createContext<SessionImageGalleryContextValue | null>(null);

function resolveImageSrc(src: string | undefined | null): string | null {
  if (!src) return null;
  return getFullUrl(src) || src;
}

function getExtension(nameOrUrl: string): string {
  const clean = nameOrUrl.split("?")[0].split("#")[0];
  return clean.split(".").pop()?.toLowerCase() || "";
}

function parseJsonishResult(
  result: string | Record<string, unknown> | undefined,
): Record<string, unknown> | null {
  if (!result) return null;
  if (typeof result === "object") return result;

  try {
    let jsonStr = result;
    const contentMatch = result.match(/content='(.+?)'(\s|$)/);
    if (contentMatch) jsonStr = contentMatch[1].replace(/\\'/g, "'");
    return JSON.parse(jsonStr) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function collectMarkdownImages(
  content: string | undefined,
  idPrefix: string,
): SessionImageGalleryItem[] {
  if (!content) return [];

  const items: SessionImageGalleryItem[] = [];
  const markdownImagePattern = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
  for (const match of content.matchAll(markdownImagePattern)) {
    const src = resolveImageSrc(match[2]);
    if (!src) continue;
    items.push({
      id: `${idPrefix}:image:${items.length}`,
      src,
      alt: match[1] || undefined,
      group: "conversation",
    });
  }

  const htmlImagePattern = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  for (const match of content.matchAll(htmlImagePattern)) {
    const src = resolveImageSrc(match[1]);
    if (!src) continue;
    items.push({
      id: `${idPrefix}:html-image:${items.length}`,
      src,
      group: "conversation",
    });
  }

  return items;
}

function collectRevealFileImage(
  part: ToolPart,
  idPrefix: string,
): SessionImageGalleryItem | null {
  if (part.name !== "reveal_file" || part.success !== true) return null;
  const parsed = parseJsonishResult(part.result);
  if (!parsed) return null;

  if (typeof parsed.url === "string") {
    const type = typeof parsed.type === "string" ? parsed.type : "";
    const mimeType = typeof parsed.mimeType === "string" ? parsed.mimeType : "";
    const name = typeof parsed.name === "string" ? parsed.name : "";
    const isImage =
      type === "image" ||
      mimeType.startsWith("image/") ||
      isImageFile(getExtension(name || parsed.url));
    const src = resolveImageSrc(parsed.url);
    if (isImage && src) {
      return {
        id: `${idPrefix}:reveal-file`,
        src,
        alt: name || undefined,
        group: "reveal-file",
      };
    }
  }

  if (parsed.type === "file_reveal" && typeof parsed.file === "object") {
    const file = parsed.file as Record<string, unknown>;
    const path = typeof file.path === "string" ? file.path : "";
    const s3Url = typeof file.s3_url === "string" ? file.s3_url : "";
    const src = resolveImageSrc(s3Url);
    if (src && isImageFile(getExtension(path || s3Url))) {
      return {
        id: `${idPrefix}:reveal-file`,
        src,
        alt: path.split("/").pop() || undefined,
        group: "reveal-file",
      };
    }
  }

  return null;
}

function collectGeneratedImageResults(
  part: ToolPart,
  idPrefix: string,
): SessionImageGalleryItem[] {
  if (part.name !== "image_generate" || part.success !== true) return [];

  const parsed = parseJsonishResult(part.result);
  return extractGeneratedImageResults(parsed).map((image, index) => ({
    id: `${idPrefix}:generated-image:${index}`,
    src: image.url,
    alt: image.name,
    group: "conversation",
  }));
}

function collectPartImages(
  part: MessagePart,
  idPrefix: string,
): SessionImageGalleryItem[] {
  if (part.type === "text" || part.type === "summary") {
    return collectMarkdownImages(part.content, idPrefix);
  }

  if (part.type === "tool") {
    const revealImage = collectRevealFileImage(part, idPrefix);
    return [
      ...(revealImage ? [revealImage] : []),
      ...collectGeneratedImageResults(part, idPrefix),
    ];
  }

  if (part.type === "subagent") {
    return [
      ...collectMarkdownImages(part.input, `${idPrefix}:input`),
      ...collectMarkdownImages(part.result, `${idPrefix}:result`),
      ...(part.parts || []).flatMap((child, index) =>
        collectPartImages(child, `${idPrefix}:part:${index}`),
      ),
    ];
  }

  return [];
}

function dedupeSessionImageGalleryItems(
  items: SessionImageGalleryItem[],
): SessionImageGalleryItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.group}:${item.src}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function collectMessageGalleryItems(
  message: Message,
): SessionImageGalleryItem[] {
  const attachmentItems = (message.attachments || []).flatMap(
    (attachment): SessionImageGalleryItem[] => {
      const isImage =
        attachment.type === "image" ||
        attachment.mimeType?.startsWith("image/");
      const src = resolveImageSrc(attachment.url);
      if (!isImage || !src) return [];
      return [
        {
          id: `${message.id}:attachment:${attachment.id}`,
          src,
          alt: attachment.name,
          group: "conversation",
        },
      ];
    },
  );

  const contentItems = collectMarkdownImages(
    message.content,
    `${message.id}:content`,
  );
  const partItems = (message.parts || []).flatMap((part, index) =>
    collectPartImages(part, `${message.id}:part:${index}`),
  );

  return [...attachmentItems, ...contentItems, ...partItems];
}

// 消息对象不可变替换：未变消息保持引用，按引用缓存可跳过对历史消息的
// markdown 图片正则与工具结果 JSON.parse 重扫（流式期间每次 chunk 都会重算）
const messageGalleryItemsCache = new WeakMap<
  Message,
  SessionImageGalleryItem[]
>();

// eslint-disable-next-line react-refresh/only-export-components
export function collectSessionImageGalleryItems(
  messages: Message[],
): SessionImageGalleryItem[] {
  const items = messages.flatMap((message) => {
    let cached = messageGalleryItemsCache.get(message);
    if (!cached) {
      cached = collectMessageGalleryItems(message);
      messageGalleryItemsCache.set(message, cached);
    }
    return cached;
  });

  return dedupeSessionImageGalleryItems(items);
}

export function useSessionImageGallery(): SessionImageGalleryContextValue | null {
  return useContext(SessionImageGalleryContext);
}

export function SessionImageGalleryProvider({
  messages,
  children,
}: {
  messages: Message[];
  children: ReactNode;
}) {
  const items = useMemo(
    () => collectSessionImageGalleryItems(messages),
    [messages],
  );
  const [activeImage, setActiveImage] =
    useState<SessionImageGalleryItem | null>(null);
  const activeIndex = activeImage
    ? items
        .filter((item) => item.group === activeImage.group)
        .findIndex((item) => item.src === activeImage.src)
    : -1;
  const activeGalleryItems = activeImage
    ? items.filter((item) => item.group === activeImage.group)
    : [];
  const currentItem =
    activeIndex >= 0 ? activeGalleryItems[activeIndex] : activeImage;
  const previousItem =
    activeIndex > 0 ? activeGalleryItems[activeIndex - 1] : null;
  const nextItem =
    activeIndex >= 0 && activeIndex < activeGalleryItems.length - 1
      ? activeGalleryItems[activeIndex + 1]
      : null;
  const positionLabel =
    activeIndex >= 0 && activeGalleryItems.length > 1
      ? `${activeIndex + 1} / ${activeGalleryItems.length}`
      : undefined;

  const openImage = useCallback(
    (
      src: string,
      alt?: string,
      options?: { group?: SessionImageGalleryGroup },
    ) => {
      const resolvedSrc = resolveImageSrc(src);
      if (!resolvedSrc) return;
      setActiveImage({
        id: `ad-hoc:${resolvedSrc}`,
        src: resolvedSrc,
        alt,
        group: options?.group || "conversation",
      });
    },
    [],
  );

  const value = useMemo(() => ({ openImage }), [openImage]);

  return (
    <SessionImageGalleryContext.Provider value={value}>
      {children}
      {currentItem && (
        <ImageViewer
          src={currentItem.src}
          alt={currentItem.alt || ""}
          isOpen={!!currentItem}
          onClose={() => setActiveImage(null)}
          onPrevious={() => previousItem && setActiveImage(previousItem)}
          onNext={() => nextItem && setActiveImage(nextItem)}
          hasPrevious={!!previousItem}
          hasNext={!!nextItem}
          positionLabel={positionLabel}
        />
      )}
    </SessionImageGalleryContext.Provider>
  );
}
