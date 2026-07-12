import { readFileSync } from "node:fs";
const toolbarSource = readFileSync(
  new URL("../ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);
const selectorsSource = readFileSync(
  new URL("../ChatInputSelectors.tsx", import.meta.url),
  "utf8",
);
const chatInputPanelRenderersSource = readFileSync(
  new URL("../chatInputPanelRenderers.tsx", import.meta.url),
  "utf8",
);
const chatInputSelectedRenderersSource = readFileSync(
  new URL("../chatInputSelectedRenderers.tsx", import.meta.url),
  "utf8",
);
const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);
const chatViewPropsSource = readFileSync(
  new URL("../../layout/AppContent/ChatViewProps.tsx", import.meta.url),
  "utf8",
);
const chatAssistantIdentityRenderersSource = readFileSync(
  new URL("../chatAssistantIdentityResolvers.ts", import.meta.url),
  "utf8",
);
const chatMessageSource = readFileSync(
  new URL("../ChatMessage/index.tsx", import.meta.url),
  "utf8",
);
const messagePartRendererSource = readFileSync(
  new URL("../ChatMessage/MessagePartRenderer.tsx", import.meta.url),
  "utf8",
);
const pluginMessageRenderersSource = readFileSync(
  new URL("../ChatMessage/pluginMessageRenderers.tsx", import.meta.url),
  "utf8",
);
const messageActionRenderersSource = readFileSync(
  new URL("../ChatMessage/messageActionRenderers.tsx", import.meta.url),
  "utf8",
);
const featureMenuSource = readFileSync(
  new URL("../../selectors/FeatureMenu.tsx", import.meta.url),
  "utf8",
);
const teamPickerSource = readFileSync(
  new URL("../../team/TeamPickerModal.tsx", import.meta.url),
  "utf8",
);

test("team toolbar chip only renders after a team is selected", () => {
  expect(toolbarSource).not.toMatch(/TeamPickerModal/);
  expect(toolbarSource).not.toMatch(/teamApi/);
  expect(toolbarSource).not.toMatch(/TeamAvatar/);
  expect(toolbarSource).not.toMatch(/getTeamFallbackAvatar/);
  expect(toolbarSource).toMatch(/selectedPersonaName && corePersonaSelectorVisible/);
  expect(toolbarSource).toMatch(/entry\?\.hasSelection\(selectedPluginRendererProps\(option\)\)/);
  expect(toolbarSource).toMatch(/const SelectedRenderer = entry\.Component/);
  expect(toolbarSource).toMatch(/<SelectedRenderer/);
  expect(toolbarSource).not.toMatch(/entry\.render\(/);
  expect(toolbarSource).not.toMatch(/selectedPluginOptions\.length > 0 && !!selectedTeamId/);
  expect(toolbarSource).not.toMatch(/onActivePanelChange\("team"\)/);
  expect(toolbarSource).not.toMatch(/teamPluginPanelId/);
  expect(toolbarSource).toMatch(/chat\.teamSelected/);
  expect(toolbarSource).not.toMatch(/Select team/);
  expect(toolbarSource).not.toMatch(/text-amber-500/);
  expect(chatInputSelectedRenderersSource).toMatch(/"agent_team\.SelectedTeamChip"/);
  expect(chatInputSelectedRenderersSource).toMatch(/hasSelection/);
  expect(chatInputSelectedRenderersSource).toMatch(/Component: AgentTeamSelectedChip/);
  expect(chatInputSelectedRenderersSource).not.toMatch(/render: AgentTeamSelectedChip/);
  expect(chatInputSelectedRenderersSource).toMatch(/teamApi/);
  expect(chatInputSelectedRenderersSource).toMatch(/TeamAvatar/);
  expect(chatInputSelectedRenderersSource).toMatch(/getTeamFallbackAvatar/);
  expect(selectorsSource).not.toMatch(/TeamPickerModal/);
  expect(selectorsSource).toMatch(/CHAT_INPUT_PANEL_RENDERERS/);
  expect(selectorsSource).toMatch(/chatInputPanels\.map/);
  expect(selectorsSource).toMatch(/CHAT_INPUT_PANEL_RENDERERS\[panel\.renderer\]/);
  expect(chatInputPanelRenderersSource).toMatch(/TeamPickerModal/);
  expect(chatInputPanelRenderersSource).toMatch(/"agent_team\.TeamPickerModal"/);
  expect(chatInputPanelRenderersSource).toMatch(/activePanel === contribution\.id/);
  expect(chatInputPanelRenderersSource).toMatch(/const optionPath = contribution\.optionBinding/);
  expect(chatInputPanelRenderersSource).toMatch(/pluginOptionValues/);
  expect(chatInputPanelRenderersSource).toMatch(/onPluginOptionChange/);
  expect(chatInputPanelRenderersSource).toMatch(/pluginOptionFromValues\(pluginOptionValues, optionPath\.pluginId, optionPath\.key\)/);
  expect(chatInputPanelRenderersSource).toMatch(/selectedTeamId=\{effectiveSelectedTeamId \?\? null\}/);
  expect(chatInputPanelRenderersSource).toMatch(/navigateToCreate = contribution\.createPath/);
  expect(chatInputPanelRenderersSource).toMatch(/navigateToManage = contribution\.managePath/);
  expect(chatInputPanelRenderersSource).not.toMatch(/agentTeamSelectedTeamOptionPath/);
  expect(chatInputPanelRenderersSource).not.toMatch(/onOpenTeamBuilder/);
  expect(chatInputSource).not.toMatch(/onOpenTeamBuilder/);
  expect(selectorsSource).not.toMatch(/onOpenTeamBuilder/);
  expect(chatViewSource).not.toMatch(/onOpenTeamBuilder/);
  expect(chatViewPropsSource).not.toMatch(/onOpenTeamBuilder/);
  expect(toolbarSource).not.toMatch(/selectedTeamId\?: string \| null/);
  expect(toolbarSource).not.toMatch(/onSelectTeam\?:/);
  expect(selectorsSource).not.toMatch(/selectedTeamId\?: string \| null/);
  expect(selectorsSource).not.toMatch(/onSelectTeam\?:/);
  expect(chatInputPanelRenderersSource).not.toMatch(/onSelectTeam\?:/);
  expect(chatInputSelectedRenderersSource).not.toMatch(/onSelectTeam\?:/);
  expect(chatInputSource).not.toMatch(/<ChatInputToolbar[\s\S]*selectedTeamId=\{selectedTeamId\}/);
  expect(chatInputSource).not.toMatch(/<ChatInputSelectors[\s\S]*onSelectTeam=\{onSelectTeam\}/);
  expect(chatInputSource).not.toMatch(/onSelectTeam\?\.\(typeof value === "string"/);
  expect(chatInputSource).toMatch(/pluginOptionValues=\{pluginOptionValues\}/);
  expect(chatInputSource).toMatch(/onPluginOptionChange=\{handlePluginOptionChange\}/);
  expect(chatInputSource).toMatch(/return providedPluginOptionValues \?\? \{\}/);
  expect(chatInputSource).not.toMatch(/withSelectedAgentTeamId/);
  expect(chatInputSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("team selector uses the persona selector interaction surfaces", () => {
  expect(toolbarSource).toMatch(/pluginOptions=\{chatInputOptions\}/);
  expect(toolbarSource).not.toMatch(/hasTeamSelector=/);
  expect(toolbarSource).toMatch(/hasPersonaSelector=\{corePersonaSelectorVisible\}/);
  expect(toolbarSource).not.toMatch(/currentAgent !== "team"/);
  expect(toolbarSource).toMatch(/suppressesCorePersonaSelector/);
  expect(toolbarSource).not.toMatch(/onSelectTeam\?\.\(null\)/);
  expect(chatInputSelectedRenderersSource).toMatch(/const optionPath = option\.optionBinding/);
  expect(chatInputSelectedRenderersSource).toMatch(/pluginOptionFromValues\(pluginOptionValues, optionPath\.pluginId, optionPath\.key\)/);
  expect(chatInputSelectedRenderersSource).toMatch(/onPluginOptionChange\?\.\(optionPath\.pluginId, optionPath\.key, null\)/);
  expect(chatInputSelectedRenderersSource).not.toMatch(/agentTeamSelectedTeamOptionPath/);
  expect(chatInputSelectedRenderersSource).not.toMatch(/onSelectTeam\?\.\(null\)/);
  expect(toolbarSource).toMatch(/group-hover:opacity-0/);
  expect(featureMenuSource).not.toMatch(/hasTeamSelector/);
  expect(featureMenuSource).toMatch(/uploadPluginOptions = pluginOptions\.filter/);
  expect(featureMenuSource).toMatch(/settingsPluginOptions = pluginOptions\.filter/);
  expect(featureMenuSource).toMatch(/enhancePluginOptions = pluginOptions\.filter/);
  expect(featureMenuSource).toMatch(/uploadPluginOptions\.map\(renderPluginOption\)/);
  expect(featureMenuSource).toMatch(/enhancePluginOptions\.map\(renderPluginOption\)/);
  expect(featureMenuSource).toMatch(/settingsPluginOptions\.map\(renderPluginOption\)/);
  expect(featureMenuSource).toMatch(/label=\{t\(option\.label\)\}/);
  expect(featureMenuSource).toMatch(/onOpen\(option\.panel \?\? option\.id\)/);
  expect(featureMenuSource).not.toMatch(/onOpen\("team"\)/);
  expect(chatInputSource).toMatch(/matchesPluginShortcut\(option\.shortcut, e\)/);
  expect(chatInputSource).toMatch(/\^mod\\\+\(\[a-z\]\)\$/);
  expect(chatInputSource).not.toMatch(/agent_team:team-picker/);
  expect(teamPickerSource).toMatch(/z-\[250\][\s\S]*sm:max-w-3xl[\s\S]*xl:max-w-6xl/);
  expect(teamPickerSource).toMatch(/grid auto-grid-cols gap-3/);
  expect(teamPickerSource).toMatch(/pps-card__action/);
  expect(teamPickerSource).toMatch(/handleSelect\(team\.id\)/);
  expect(teamPickerSource).toMatch(/onSelect\(teamId\)/);
  expect(teamPickerSource).not.toMatch(/sm:w-\[420px\]/);
});

test("assistant message header shows the selected team in team mode", () => {
  expect(chatViewSource).toMatch(/runtimePlugins/);
  expect(chatViewSource).toMatch(/useChatAssistantIdentity\(\{/);
  expect(chatViewSource).not.toMatch(/useCurrentTeam/);
  expect(chatViewPropsSource).not.toMatch(/teamApi/);
  expect(chatViewPropsSource).not.toMatch(/getTeamFallbackAvatar/);
  expect(chatViewPropsSource).not.toMatch(/selectedAgentTeamIdFromMetadata/);
  expect(chatViewPropsSource).toMatch(/pluginOptionValues: PluginOptionsMetadata/);
  expect(chatViewPropsSource).toMatch(/usePluginChatAssistantIdentity/);
  expect(chatViewSource).not.toMatch(/selectedPluginTeamId/);
  expect(chatViewSource).toMatch(/selectedTeamId=\{selectedTeamId\}/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/CHAT_ASSISTANT_IDENTITY_RESOLVERS/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/buildAssistantIdentityResolverContributions/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/optionBinding/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/pluginOptionFromValues/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/"..\/team\/teamAvatarUtils"/);
  expect(chatAssistantIdentityRenderersSource).not.toMatch(/hasAgentCatalogEntryContribution/);
  expect(chatAssistantIdentityRenderersSource).not.toMatch(/AGENT_TEAM_LEGACY_AGENT_ID/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/contributionAgentId/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/contribution\.agentId !== currentAgent/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/agent_team\.TeamAssistantIdentity/);
  expect(chatAssistantIdentityRenderersSource).toMatch(/const agentTeamIdentity = useAgentTeamIdentity\(context\)/);
  expect(chatAssistantIdentityRenderersSource).not.toMatch(/resolver\?\.useIdentity\(context\)/);
  expect(chatAssistantIdentityRenderersSource).not.toMatch(/selectedTeamId: string \| null/);
  expect(chatViewSource).toMatch(/personaAvatar=\{assistantIdentity\.avatar\}/);
  expect(chatViewSource).toMatch(/personaName=\{assistantIdentity\.name\}/);
  expect(chatMessageSource).toMatch(/\{personaName \|\| t\("chat\.message\.assistant"\)\}/);
});

test("message plugin actions render through the static renderer registry", () => {
  expect(chatMessageSource).toMatch(/MESSAGE_ACTION_RENDERERS/);
  expect(chatMessageSource).toMatch(/buildMessageActionContributions\(runtimePlugins, \{/);
  expect(chatMessageSource).toMatch(/target: "assistant_message"/);
  expect(chatMessageSource).toMatch(/rendererId = contribution\.renderer/);
  expect(chatMessageSource).not.toMatch(/FeedbackButtons/);
  expect(messageActionRenderersSource).toMatch(/"feedback\.FeedbackButtons"/);
  expect(messageActionRenderersSource).toMatch(/FeedbackButtons/);
  expect(chatMessageSource).not.toMatch(/hasMessageActionContribution/);
  expect(chatMessageSource).not.toMatch(/canUseFeedbackAction/);
});

test("plugin message parts render through the generic static renderer registry", () => {
  expect(messagePartRendererSource).toMatch(/part\.type === "plugin_message"/);
  expect(messagePartRendererSource).toMatch(/getPluginMessageRenderer/);
  expect(messagePartRendererSource).toMatch(/PLUGIN_MESSAGE_RENDERERS/);
  expect(messagePartRendererSource).toMatch(/PluginMessageUnavailable/);
  expect(pluginMessageRenderersSource).toMatch(/PLUGIN_MESSAGE_RENDERERS/);
  const legacyDedicatedMessageCardPattern = new RegExp("Workflow" + "Item");
  expect(messagePartRendererSource).not.toMatch(legacyDedicatedMessageCardPattern);
  expect(pluginMessageRenderersSource).not.toMatch(legacyDedicatedMessageCardPattern);
});
