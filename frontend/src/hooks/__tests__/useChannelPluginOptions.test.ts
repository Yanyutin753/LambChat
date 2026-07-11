import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../useChannelPluginOptions.ts", import.meta.url),
  "utf8",
);

test("channel plugin option hook loads extension host channel option schemas", () => {
  expect(source).toMatch(/pluginRuntimeApi\.listChannelOptions/);
  expect(source).toMatch(/listenPluginRuntimeUpdated/);
  expect(source).toMatch(/includeInactive/);
});

test("channel plugin option hook filters declarations by visible route", () => {
  expect(source).toMatch(/routeForChannel/);
  expect(source).toMatch(/`\/channels\/\$\{channelType\}`/);
  expect(source).toMatch(/option\.visible_when\?\.route/);
  expect(source).toMatch(/matchesChannelRoute/);
});
