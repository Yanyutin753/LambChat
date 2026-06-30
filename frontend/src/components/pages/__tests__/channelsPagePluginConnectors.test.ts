import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const channelsPageSource = readFileSync(
  new URL("../ChannelsPage.tsx", import.meta.url),
  "utf8",
);

test("ChannelsPage filters plugin-owned channel types through runtime connector contributions", () => {
  assert.match(channelsPageSource, /hasRuntimeManagedChannelConnector/);
  assert.match(channelsPageSource, /hasChannelConnectorContribution/);
  assert.match(channelsPageSource, /findChannelConnectorContribution/);
  assert.match(channelsPageSource, /getChannelConnectorPanelRenderer/);
  assert.doesNotMatch(
    channelsPageSource,
    /ct\.channel_type\s*={2,3}\s*["']feishu["']/,
  );
  assert.doesNotMatch(
    channelsPageSource,
    /selectedChannel\s*={2,3}\s*["']feishu["']/,
  );
  assert.doesNotMatch(channelsPageSource, /<FeishuPanel/);
});
