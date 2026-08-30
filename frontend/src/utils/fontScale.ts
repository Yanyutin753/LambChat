/**
 * 全局字体大小档位。
 *
 * 全站字号已 token 化为 rem 刻度（tailwind.config.js），因此只需缩放
 * <html> 根字号即可整体等比缩放，无需逐组件适配。
 */
export type FontScale = "small" | "standard" | "large" | "xlarge";

export const FONT_SCALE_STORAGE_KEY = "lambchat-font-scale";
export const FONT_SCALE_EXTERNAL_CHANGE_EVENT = "font-scale-external-change";

const FONT_SCALE_ROOT_VALUES: Record<FontScale, string> = {
  small: "87.5%",
  standard: "100%",
  large: "112.5%",
  xlarge: "125%",
};

type StorageReader = Pick<Storage, "getItem">;

interface FontScaleDocument {
  documentElement: {
    style?: Pick<CSSStyleDeclaration, "setProperty" | "removeProperty">;
  };
}

interface FontScaleSyncEnvironment {
  localStorage?: StorageReader;
  document?: FontScaleDocument;
  addEventListener?: (
    type: string,
    listener: (event: { detail?: unknown }) => void,
  ) => void;
}

export function isFontScale(value: unknown): value is FontScale {
  return (
    value === "small" ||
    value === "standard" ||
    value === "large" ||
    value === "xlarge"
  );
}

export function parseFontScale(stored: string | null | undefined): FontScale {
  return isFontScale(stored) ? stored : "standard";
}

export function readFontScale(
  storage: StorageReader = localStorage,
): FontScale {
  return parseFontScale(storage.getItem(FONT_SCALE_STORAGE_KEY));
}

export function fontScaleRootValue(scale: FontScale): string {
  return FONT_SCALE_ROOT_VALUES[scale];
}

export function applyFontScaleToDocument(
  scale: FontScale,
  doc: FontScaleDocument = document,
): void {
  if (scale === "standard") {
    // 标准档移除内联样式，回到 UA 默认根字号
    doc.documentElement.style?.removeProperty("font-size");
    return;
  }
  doc.documentElement.style?.setProperty(
    "font-size",
    FONT_SCALE_ROOT_VALUES[scale],
  );
}

/**
 * 应用已保存的档位，并监听登录后端偏好回灌派发的事件，
 * 让根字号在会话内即时更新而无需刷新。
 */
export function installFontScaleSync(
  env: FontScaleSyncEnvironment = globalThis,
): void {
  if (env.document) {
    applyFontScaleToDocument(readFontScale(env.localStorage), env.document);
  }

  env.addEventListener?.(FONT_SCALE_EXTERNAL_CHANGE_EVENT, (event) => {
    if (!env.document) return;
    const scale = event.detail;
    applyFontScaleToDocument(
      isFontScale(scale) ? scale : "standard",
      env.document,
    );
  });
}
