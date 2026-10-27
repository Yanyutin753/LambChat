import { useCallback, useState } from "react";
import { ImageViewer } from "../../../common";
import {
  resolveImageListNavigation,
  type ImageListEntry,
} from "../../../common/imageListNavigation";
import { useSessionImageGallery } from "../sessionImageGallery";

interface LocalPreview {
  src: string;
  alt?: string;
  siblings: readonly ImageListEntry[];
}

/**
 * 工具卡片内的图片点击预览：优先进会话图片画廊（可跨消息翻页），
 * 画廊上下文不可用（如侧边快照渲染、面板）时回退独立 ImageViewer。
 *
 * `siblings` 是本卡片的有序图片列表：画廊没有收录该图时在列表内翻页，
 * 回退查看器也按它翻页；调用方应 useMemo 保持引用稳定。
 *
 * 用法：const { openImage, viewer } = useImagePreviewFallback(siblings);
 * 缩略图 onClick={() => openImage(url, name)}，组件树末尾渲染 {viewer}。
 */
export function useImagePreviewFallback(
  defaultSiblings?: readonly ImageListEntry[],
): {
  openImage: (
    src: string,
    alt?: string,
    options?: { siblings?: readonly ImageListEntry[] },
  ) => void;
  viewer: React.ReactNode;
} {
  const sessionImageGallery = useSessionImageGallery();
  const [preview, setPreview] = useState<LocalPreview | null>(null);

  const openImage = useCallback(
    (
      src: string,
      alt?: string,
      options?: { siblings?: readonly ImageListEntry[] },
    ) => {
      const siblings = options?.siblings ?? defaultSiblings ?? [];
      if (sessionImageGallery) {
        sessionImageGallery.openImage(src, alt, { siblings });
        return;
      }
      setPreview({ src, alt, siblings });
    },
    [defaultSiblings, sessionImageGallery],
  );

  const navigation = preview
    ? resolveImageListNavigation(preview.siblings, preview.src)
    : null;
  const goTo = (entry: ImageListEntry | null) => {
    if (entry && preview) setPreview({ ...preview, ...entry });
  };

  const viewer =
    preview && navigation ? (
      <ImageViewer
        src={preview.src}
        alt={navigation.current?.alt ?? preview.alt ?? ""}
        isOpen
        onClose={() => setPreview(null)}
        onPrevious={() => goTo(navigation.previous)}
        onNext={() => goTo(navigation.next)}
        hasPrevious={!!navigation.previous}
        hasNext={!!navigation.next}
        positionLabel={navigation.positionLabel}
      />
    ) : null;

  return { openImage, viewer };
}
