import {
  getPersonaAvatarIcon,
  getPersonaAvatarIconValue,
  isPersonaImageAvatar,
} from "../personaAvatar.ts";

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
