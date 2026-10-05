import {
  getEmojiAvatarUrl,
  getPersonaAvatarIcon,
  getPersonaAvatarIconValue,
  isPersonaImageAvatar,
} from "../personaAvatar.ts";

test("emoji avatars use the npmmirror primary CDN url", () => {
  expect(getEmojiAvatarUrl("🤖")).toBe(
    "https://registry.npmmirror.com/@lobehub/fluent-emoji-anim-3/latest/files/assets/1f916.webp",
  );
});

test("stores built-in persona avatars as compact icon keys", () => {
  const value = getPersonaAvatarIconValue("sparkles");

  expect(value).toBe("icon:sparkles");
  expect(getPersonaAvatarIcon(value)?.key).toBe("sparkles");
  expect(isPersonaImageAvatar(value)).toBe(false);
});

test("treats uploaded avatar urls as image avatars", () => {
  expect(isPersonaImageAvatar("/api/upload/file/avatar.png")).toBe(true);
  expect(getPersonaAvatarIcon("/api/upload/file/avatar.png")).toBe(null);
});
