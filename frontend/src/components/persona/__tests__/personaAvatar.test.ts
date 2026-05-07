import test from "node:test";
import assert from "node:assert/strict";

import {
  getPersonaAvatarIcon,
  getPersonaAvatarIconValue,
  isPersonaImageAvatar,
} from "../personaAvatar.ts";

test("stores built-in persona avatars as compact icon keys", () => {
  const value = getPersonaAvatarIconValue("sparkles");

  assert.equal(value, "icon:sparkles");
  assert.equal(getPersonaAvatarIcon(value)?.key, "sparkles");
  assert.equal(isPersonaImageAvatar(value), false);
});

test("treats uploaded avatar urls as image avatars", () => {
  assert.equal(isPersonaImageAvatar("/api/upload/file/avatar.png"), true);
  assert.equal(getPersonaAvatarIcon("/api/upload/file/avatar.png"), null);
});
