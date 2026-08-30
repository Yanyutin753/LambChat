import {
  FONT_SCALE_EXTERNAL_CHANGE_EVENT,
  FONT_SCALE_STORAGE_KEY,
  applyFontScaleToDocument,
  fontScaleRootValue,
  installFontScaleSync,
  isFontScale,
  parseFontScale,
  readFontScale,
} from "../fontScale.ts";

test("parseFontScale accepts every named scale step and falls back to standard", () => {
  expect(parseFontScale("small")).toBe("small");
  expect(parseFontScale("standard")).toBe("standard");
  expect(parseFontScale("large")).toBe("large");
  expect(parseFontScale("xlarge")).toBe("xlarge");
  expect(parseFontScale(null)).toBe("standard");
  expect(parseFontScale("giant")).toBe("standard");
});

test("isFontScale narrows unknown metadata values safely", () => {
  expect(isFontScale("large")).toBe(true);
  expect(isFontScale("medium")).toBe(false);
  expect(isFontScale(undefined)).toBe(false);
});

test("readFontScale reads the persisted value through the injected storage", () => {
  const storage = {
    getItem: (key: string) =>
      key === FONT_SCALE_STORAGE_KEY ? "xlarge" : null,
  };

  expect(readFontScale(storage)).toBe("xlarge");
  expect(readFontScale({ getItem: () => null })).toBe("standard");
});

test("fontScaleRootValue maps steps to proportional root font sizes", () => {
  expect(fontScaleRootValue("small")).toBe("87.5%");
  expect(fontScaleRootValue("standard")).toBe("100%");
  expect(fontScaleRootValue("large")).toBe("112.5%");
  expect(fontScaleRootValue("xlarge")).toBe("125%");
});

function fakeDocument() {
  const properties = new Map<string, string>();
  return {
    properties,
    documentElement: {
      style: {
        setProperty: (name: string, value: string) => {
          properties.set(name, value);
        },
        removeProperty: (name: string) => {
          properties.delete(name);
        },
      },
    },
  };
}

test("applyFontScaleToDocument sets html font-size for non-standard scales", () => {
  const doc = fakeDocument();

  applyFontScaleToDocument("large", doc);

  expect(doc.properties.get("font-size")).toBe("112.5%");
});

test("applyFontScaleToDocument clears the inline font-size for the standard scale", () => {
  const doc = fakeDocument();
  doc.properties.set("font-size", "125%");

  applyFontScaleToDocument("standard", doc);

  expect(doc.properties.has("font-size")).toBe(false);
});

test("installFontScaleSync applies the stored scale and follows external changes", () => {
  const doc = fakeDocument();
  const listeners: Record<string, (event: { detail?: unknown }) => void> = {};

  installFontScaleSync({
    localStorage: {
      getItem: (key: string) =>
        key === FONT_SCALE_STORAGE_KEY ? "small" : null,
    },
    document: doc,
    addEventListener: (type, listener) => {
      listeners[type] = listener;
    },
  });

  expect(doc.properties.get("font-size")).toBe("87.5%");

  const listener = listeners[FONT_SCALE_EXTERNAL_CHANGE_EVENT];
  expect(listener).toBeDefined();

  listener({ detail: "xlarge" });
  expect(doc.properties.get("font-size")).toBe("125%");

  // 非法事件载荷回落标准档，避免把 DOM 留在脏状态
  listener({ detail: 42 });
  expect(doc.properties.has("font-size")).toBe(false);
});
