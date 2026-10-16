import { getEmojiAssetUrl, getEmojiFallbackUrls } from "../emojiAssets";

describe("getEmojiAssetUrl", () => {
  test("returns the npmmirror upstream as primary (China-friendly)", () => {
    expect(getEmojiAssetUrl("🤖", "anim")).toBe(
      "https://registry.npmmirror.com/@lobehub/fluent-emoji-anim-3/latest/files/assets/1f916.webp",
    );
    expect(getEmojiAssetUrl("📄", "3d")).toBe(
      "https://registry.npmmirror.com/@lobehub/fluent-emoji-3d/latest/files/assets/1f4c4.webp",
    );
  });

  test.each([
    ["👨", "anim", "anim-1", "1f468.webp"],
    ["👩", "anim", "anim-2", "1f469.webp"],
    ["😟", "anim", "anim-2", "1f61f.webp"],
    ["😠", "anim", "anim-3", "1f620.webp"],
    ["🦟", "anim", "anim-3", "1f99f.webp"],
    ["🦠", "anim", "anim-4", "1f9a0.webp"],
    ["❤️", "anim", "anim-4", "2764-fe0f.webp"],
    ["👩🏽‍💻", "anim", "anim-2", "1f469-1f3fd-200d-1f4bb.webp"],
    ["🇨🇳", "3d", "3d", "1f1e8-1f1f3.webp"],
    ["🤖", "flat", "flat", "1f916.svg"],
    ["🤖", "modern", "modern", "1f916.svg"],
    ["🤖", "mono", "mono", "1f916.svg"],
  ] as const)(
    "preserves CDN asset mapping for %s (%s)",
    (emoji, type, suffix, asset) => {
      expect(getEmojiAssetUrl(emoji, type)).toBe(
        `https://registry.npmmirror.com/@lobehub/fluent-emoji-${suffix}/latest/files/assets/${asset}`,
      );
    },
  );

  test("uses 3d assets by default", () => {
    expect(getEmojiAssetUrl("🤖")).toBe(
      "https://registry.npmmirror.com/@lobehub/fluent-emoji-3d/latest/files/assets/1f916.webp",
    );
  });
});

describe("getEmojiFallbackUrls", () => {
  test("derives jsdelivr then unpkg alternatives for npmmirror emoji urls", () => {
    expect(
      getEmojiFallbackUrls(
        "https://registry.npmmirror.com/@lobehub/fluent-emoji-anim-2/latest/files/assets/1f4c4.webp",
      ),
    ).toEqual([
      "https://cdn.jsdelivr.net/npm/@lobehub/fluent-emoji-anim-2@latest/assets/1f4c4.webp",
      "https://unpkg.com/@lobehub/fluent-emoji-anim-2@latest/assets/1f4c4.webp",
    ]);
  });

  test("works for 3d package urls too", () => {
    expect(
      getEmojiFallbackUrls(
        "https://registry.npmmirror.com/@lobehub/fluent-emoji-3d/latest/files/assets/1f916.webp",
      ),
    ).toEqual([
      "https://cdn.jsdelivr.net/npm/@lobehub/fluent-emoji-3d@latest/assets/1f916.webp",
      "https://unpkg.com/@lobehub/fluent-emoji-3d@latest/assets/1f916.webp",
    ]);
  });

  test("returns empty list for non-emoji urls", () => {
    expect(getEmojiFallbackUrls("https://app.example/api/files/a.jpg")).toEqual(
      [],
    );
    expect(
      getEmojiFallbackUrls(
        "https://unpkg.com/@lobehub/fluent-emoji-3d@latest/assets/1f916.webp",
      ),
    ).toEqual([]);
    expect(getEmojiFallbackUrls("/api/upload/file/a.png")).toEqual([]);
  });
});
