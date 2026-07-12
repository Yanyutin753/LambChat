import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ChannelPanel.tsx", import.meta.url),
  "utf8",
);

test("generic channel panel consumes plugin-declared channel options", () => {
  expect(source).toMatch(/useChannelPluginOptions\(channelType,\s*\{[\s\S]*includeInactive: true/);
  expect(source).toMatch(/ChannelPluginOptions/);
  expect(source).toMatch(/channelPluginOptionValues/);
  expect(source).toMatch(/setChannelPluginOption/);
});

test("generic channel panel persists plugin_options on create and update", () => {
  expect(source).toMatch(/setChannelPluginOptionValues\(configResponse\.plugin_options \|\| \{\}\)/);
  expect(source).toMatch(/plugin_options:\s*channelPluginOptionValues/);
  expect(source).toMatch(/channelApi\.update[\s\S]*plugin_options:\s*channelPluginOptionValues/);
  expect(source).toMatch(/channelApi\.create[\s\S]*plugin_options:\s*channelPluginOptionValues/);
});
