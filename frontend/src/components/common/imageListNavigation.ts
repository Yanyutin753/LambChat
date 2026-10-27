export interface ImageListEntry {
  src: string;
  alt?: string;
}

export interface ImageListNavigation<T extends ImageListEntry> {
  /** -1 when `src` is not part of `items` */
  index: number;
  current: T | null;
  previous: T | null;
  next: T | null;
  /** "n / N", only when the image is found inside a multi-image list */
  positionLabel: string | undefined;
}

/**
 * 灯箱在一组有序图片里的位置与相邻项：会话画廊、工具卡片兜底查看器和
 * 输入框附件预览共用这一套翻页规则。
 */
export function resolveImageListNavigation<T extends ImageListEntry>(
  items: readonly T[],
  src: string | null | undefined,
): ImageListNavigation<T> {
  const index = src ? items.findIndex((item) => item.src === src) : -1;
  if (index < 0) {
    return {
      index,
      current: null,
      previous: null,
      next: null,
      positionLabel: undefined,
    };
  }
  return {
    index,
    current: items[index],
    previous: index > 0 ? items[index - 1] : null,
    next: index < items.length - 1 ? items[index + 1] : null,
    positionLabel:
      items.length > 1 ? `${index + 1} / ${items.length}` : undefined,
  };
}
