import { useCallback, useState } from "react";
import { ImageViewer } from "../../../common";
import { useSessionImageGallery } from "../sessionImageGallery";

/**
 * 工具卡片内的图片点击预览：优先进会话图片画廊（可跨消息翻页），
 * 画廊上下文不可用（如侧边快照渲染）时回退独立 ImageViewer。
 *
 * 用法：const { openImage, viewer } = useImagePreviewFallback();
 * 缩略图 onClick={() => openImage(url)}，组件树末尾渲染 {viewer}。
 */
export function useImagePreviewFallback(): {
  openImage: (src: string, alt?: string) => void;
  viewer: React.ReactNode;
} {
  const sessionImageGallery = useSessionImageGallery();
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);

  const openImage = useCallback(
    (src: string, alt?: string) => {
      if (sessionImageGallery) {
        sessionImageGallery.openImage(src, alt);
        return;
      }
      setImageViewerSrc(src);
    },
    [sessionImageGallery],
  );

  const viewer = imageViewerSrc ? (
    <ImageViewer
      src={imageViewerSrc}
      alt=""
      isOpen={!!imageViewerSrc}
      onClose={() => setImageViewerSrc(null)}
    />
  ) : null;

  return { openImage, viewer };
}
