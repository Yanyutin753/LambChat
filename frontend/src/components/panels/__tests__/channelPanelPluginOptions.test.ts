import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../ChannelPanel.tsx", import.meta.url),
  "utf8",
);

test("generic channel panel consumes plugin-declared channel options", () => {
  assert.match(source, /useChannelPluginOptions\(channelType,\s*\{[\s\S]*includeInactive: true/);
  assert.match(source, /ChannelPluginOptions/);
  assert.match(source, /channelPluginOptionValues/);
  assert.match(source, /setChannelPluginOption/);
});

test("generic channel panel persists plugin_options on create and update", () => {
  assert.match(source, /setChannelPluginOptionValues\(configResponse\.plugin_options \|\| \{\}\)/);
  assert.match(source, /plugin_options:\s*channelPluginOptionValues/);
  assert.match(source, /channelApi\.update[\s\S]*plugin_options:\s*channelPluginOptionValues/);
  assert.match(source, /channelApi\.create[\s\S]*plugin_options:\s*channelPluginOptionValues/);
});
