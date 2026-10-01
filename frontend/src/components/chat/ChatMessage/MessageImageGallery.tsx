import { useEffect, useMemo, useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { useSessionImageGallery } from "./sessionImageGallery";
import { buildChatThumbUrl } from "../../../utils/chatThumbs";
import {
  getUiExpansion,
  setUiExpansion,
  useUiExpansionState,
} from "./uiExpansionStore";
import { ImageViewer } from "../../common";
import type { RevealFileImageInfo } from "./revealFileImageUtils";

interface MessageImageGalleryProps {
  images: RevealFileImageInfo[];
  /**
   * 挂载时的默认展开态：消息初次生成（流式中）为 true，历史回看为 false。
   * 仅在会话级 store 尚无该 stateKey 记录时生效，用户手动切换永远优先。
   */
  defaultExpanded?: boolean;
  /** 稳定标识（消息 id + 分组定位）：跨虚拟化卸载复水展开状态 */
  stateKey?: string;
}

export function MessageImageGallery({
  images,
  defaultExpanded = true,
  stateKey,
}: MessageImageGalleryProps) {
  const { t } = useTranslation();
  const sessionImageGallery = useSessionImageGallery();
  // 分享页等未挂 SessionImageGalleryProvider 的场景，用本地灯箱兜底，
  // 避免点击预览变成静默 no-op
  const [fallbackImage, setFallbackImage] =
    useState<RevealFileImageInfo | null>(null);
  const [expanded, toggleExpanded] = useUiExpansionState(
    stateKey,
    defaultExpanded,
  );

  // 挂载时把初次生成态钉进会话级 store：流式结束后 defaultExpanded 翻转
  // false，虚拟列表卸载再复水也不会误收起刚生成的图；换会话时 store 被
  // clearUiExpansions() 统一清空，回落到「历史消息默认收起」
  useEffect(() => {
    if (stateKey !== undefined && getUiExpansion(stateKey) === undefined) {
      setUiExpansion(stateKey, defaultExpanded);
    }
  }, [stateKey, defaultExpanded]);

  const handleImageClick = (image: RevealFileImageInfo) => {
    if (sessionImageGallery) {
      sessionImageGallery.openImage(image.src, image.fileName, {
        group: "reveal-file",
      });
    } else {
      setFallbackImage(image);
    }
  };

  const layoutClass = useMemo(() => {
    const count = images.length;
    if (count === 1) return "";
    if (count <= 3) return "grid grid-cols-2 gap-2";
    return "columns-2 gap-2";
  }, [images.length]);

  if (images.length === 0) return null;

  const firstImage = images[0];

  return (
    <>
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={t("chat.message.imageGalleryToggle")}
        onClick={toggleExpanded}
        className="group/imgtoggle flex w-full cursor-pointer items-center gap-1.5 border-b border-theme-border pb-1.5 text-left"
      >
        <ImageWithSkeleton
          src={firstImage.src}
          thumbSrc={buildChatThumbUrl(firstImage.src)}
          alt=""
          skipUrlResolve
          inline
          className="h-7 w-7 shrink-0 rounded-md border border-theme-border bg-theme-bg-card object-contain"
          loading="lazy"
        />
        <span className="min-w-0 truncate text-[0.9375rem] max-sm:text-16 leading-6 text-gray-700 dark:text-gray-300">
          {t("chat.message.imageGalleryCount", { count: images.length })}
        </span>
        <ChevronRight
          size={16}
          strokeWidth={2}
          className={clsx(
            "self-center shrink-0 text-theme-text-tertiary opacity-70 transition-transform duration-200 group-hover/imgtoggle:opacity-100",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && (
        <div className={layoutClass}>
          {images.map((image, index) => {
            const isFirstOfThree = images.length === 3 && index === 0;
            return (
              <div
                key={image.id}
                className={
                  isFirstOfThree
                    ? "col-span-2"
                    : images.length === 1
                      ? "w-full max-w-md"
                      : "break-inside-avoid"
                }
              >
                <div
                  className="group/img relative cursor-pointer rounded-xl border overflow-hidden transition-shadow hover:shadow-lg border-theme-border bg-theme-bg-card dark:bg-theme-bg"
                  onClick={() => handleImageClick(image)}
                >
                  <ImageWithSkeleton
                    src={image.src}
                    thumbSrc={buildChatThumbUrl(image.src)}
                    alt={image.fileName}
                    skipUrlResolve
                    inline
                    className="w-full h-auto object-contain"
                    loading="lazy"
                  />
                  {/* Hover overlay — top-right icon */}
                  <div className="absolute top-2 right-2 opacity-0 group-hover/img:opacity-100 transition-opacity pointer-events-none z-[2]">
                    <div className="p-1.5 rounded-lg bg-black/40 shadow pointer-events-auto">
                      <ExternalLink size={14} className="text-white" />
                    </div>
                  </div>
                  {/* File name label on hover */}
                  <div className="absolute bottom-0 left-0 right-0 opacity-0 group-hover/img:opacity-100 transition-opacity">
                    <div className="px-2 py-1 bg-gradient-to-t from-black/60 to-transparent">
                      <span className="text-11 text-white/90 truncate block">
                        {image.fileName}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ImageViewer
        src={fallbackImage?.src || ""}
        alt={fallbackImage?.fileName || ""}
        isOpen={!!fallbackImage}
        onClose={() => setFallbackImage(null)}
      />
    </>
  );
}
