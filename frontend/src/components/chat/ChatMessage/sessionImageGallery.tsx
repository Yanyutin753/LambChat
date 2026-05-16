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
import { ImageViewer } from "../../common";

export interface SessionImageGalleryItem {
  id: string;
  src: string;
  alt?: string;
}

interface SessionImageGalleryContextValue {
  openImage: (src: string, alt?: string) => void;
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
    });
  }

  const htmlImagePattern = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  for (const match of content.matchAll(htmlImagePattern)) {
    const src = resolveImageSrc(match[1]);
    if (!src) continue;
    items.push({
      id: `${idPrefix}:html-image:${items.length}`,
      src,
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
      };
    }
  }

  return null;
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
    return revealImage ? [revealImage] : [];
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

export function collectSessionImageGalleryItems(
  messages: Message[],
): SessionImageGalleryItem[] {
  return messages.flatMap((message) => {
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
  });
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
    ? items.findIndex((item) => item.src === activeImage.src)
    : -1;
  const currentItem = activeIndex >= 0 ? items[activeIndex] : activeImage;
  const previousItem = activeIndex > 0 ? items[activeIndex - 1] : null;
  const nextItem =
    activeIndex >= 0 && activeIndex < items.length - 1
      ? items[activeIndex + 1]
      : null;
  const positionLabel =
    activeIndex >= 0 && items.length > 1
      ? `${activeIndex + 1} / ${items.length}`
      : undefined;

  const openImage = useCallback((src: string, alt?: string) => {
    const resolvedSrc = resolveImageSrc(src);
    if (!resolvedSrc) return;
    setActiveImage({ id: `ad-hoc:${resolvedSrc}`, src: resolvedSrc, alt });
  }, []);

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
