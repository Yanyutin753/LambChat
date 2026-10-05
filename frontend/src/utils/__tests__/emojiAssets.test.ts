import { getFluentEmojiCDN } from "@lobehub/fluent-emoji";
import {
  getEmojiAssetUrl,
  getEmojiFallbackUrls,
} from "../emojiAssets";

describe("getEmojiAssetUrl", () => {
  test("returns the npmmirror upstream as primary (China-friendly)", () => {
    expect(getEmojiAssetUrl("🤖", "anim")).toBe(
      "https://registry.npmmirror.com/@lobehub/fluent-emoji-anim-3/latest/files/assets/1f916.webp",
    );
    expect(getEmojiAssetUrl("📄", "3d")).toBe(
      "https://registry.npmmirror.com/@lobehub/fluent-emoji-3d/latest/files/assets/1f4c4.webp",
    );
  });

  test("stays equivalent to the package CDN output for preset emojis", () => {
    for (const emoji of ["✨", "🤖", "🎓", "💻", "✍️", "🛡️", "📊", "⚡", "📦", "🎨", "🎵", "📚", "🧠", "🔬", "💬", "🌟"]) {
      expect(getEmojiAssetUrl(emoji, "anim")).toBe(
        getFluentEmojiCDN(emoji, { type: "anim" }),
      );
    }
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
      getEmojiFallbackUrls("https://unpkg.com/@lobehub/fluent-emoji-3d@latest/assets/1f916.webp"),
    ).toEqual([]);
    expect(getEmojiFallbackUrls("/api/upload/file/a.png")).toEqual([]);
  });
});
