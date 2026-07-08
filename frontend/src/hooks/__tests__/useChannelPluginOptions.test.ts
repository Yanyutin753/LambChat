import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../useChannelPluginOptions.ts", import.meta.url),
  "utf8",
);

test("channel plugin option hook loads extension host channel option schemas", () => {
  assert.match(source, /pluginRuntimeApi\.listChannelOptions/);
  assert.match(source, /listenPluginRuntimeUpdated/);
  assert.match(source, /includeInactive/);
});

test("channel plugin option hook filters declarations by visible route", () => {
  assert.match(source, /routeForChannel/);
  assert.match(source, /`\/channels\/\$\{channelType\}`/);
  assert.match(source, /option\.visible_when\?\.route/);
  assert.match(source, /matchesChannelRoute/);
});
