import { readFileSync } from "node:fs";
const channelsPageSource = readFileSync(
  new URL("../ChannelsPage.tsx", import.meta.url),
  "utf8",
);

test("ChannelsPage filters plugin-owned channel types through runtime connector contributions", () => {
  expect(channelsPageSource).toMatch(/hasRuntimeManagedChannelConnector/);
  expect(channelsPageSource).toMatch(/hasChannelConnectorContribution/);
  expect(channelsPageSource).toMatch(/findChannelConnectorContribution/);
  expect(channelsPageSource).toMatch(/getChannelConnectorPanelRenderer/);
  expect(channelsPageSource).not.toMatch(/ct\.channel_type\s*={2,3}\s*["']feishu["']/);
  expect(channelsPageSource).not.toMatch(/selectedChannel\s*={2,3}\s*["']feishu["']/);
  expect(channelsPageSource).not.toMatch(/<FeishuPanel/);
});
