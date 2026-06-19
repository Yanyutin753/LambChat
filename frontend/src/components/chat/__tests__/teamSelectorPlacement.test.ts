import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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
  assert.doesNotMatch(toolbarSource, /TeamPickerModal/);
  assert.doesNotMatch(toolbarSource, /teamApi/);
  assert.doesNotMatch(toolbarSource, /TeamAvatar/);
  assert.doesNotMatch(toolbarSource, /getTeamFallbackAvatar/);
  assert.match(toolbarSource, /selectedPersonaName && corePersonaSelectorVisible/);
  assert.match(
    toolbarSource,
    /entry\?\.hasSelection\(selectedPluginRendererProps\(option\)\)/,
  );
  assert.match(toolbarSource, /entry\.render\(/);
  assert.doesNotMatch(toolbarSource, /selectedPluginOptions\.length > 0 && !!selectedTeamId/);
  assert.doesNotMatch(toolbarSource, /onActivePanelChange\("team"\)/);
  assert.doesNotMatch(toolbarSource, /teamPluginPanelId/);
  assert.match(toolbarSource, /chat\.teamSelected/);
  assert.doesNotMatch(toolbarSource, /Select team/);
  assert.doesNotMatch(toolbarSource, /text-amber-500/);
  assert.match(chatInputSelectedRenderersSource, /"agent_team\.SelectedTeamChip"/);
  assert.match(chatInputSelectedRenderersSource, /hasSelection/);
  assert.match(chatInputSelectedRenderersSource, /render: AgentTeamSelectedChip/);
  assert.match(chatInputSelectedRenderersSource, /teamApi/);
  assert.match(chatInputSelectedRenderersSource, /TeamAvatar/);
  assert.match(chatInputSelectedRenderersSource, /getTeamFallbackAvatar/);
  assert.doesNotMatch(selectorsSource, /TeamPickerModal/);
  assert.match(selectorsSource, /CHAT_INPUT_PANEL_RENDERERS/);
  assert.match(selectorsSource, /chatInputPanels\.map/);
  assert.match(selectorsSource, /CHAT_INPUT_PANEL_RENDERERS\[panel\.renderer\]/);
  assert.match(chatInputPanelRenderersSource, /TeamPickerModal/);
  assert.match(chatInputPanelRenderersSource, /"agent_team\.TeamPickerModal"/);
  assert.match(chatInputPanelRenderersSource, /activePanel === contribution\.id/);
  assert.match(chatInputPanelRenderersSource, /const optionPath = contribution\.optionBinding/);
  assert.match(chatInputPanelRenderersSource, /pluginOptionValues/);
  assert.match(chatInputPanelRenderersSource, /onPluginOptionChange/);
  assert.match(chatInputPanelRenderersSource, /pluginOptionFromValues\(pluginOptionValues, optionPath\.pluginId, optionPath\.key\)/);
  assert.match(chatInputPanelRenderersSource, /selectedTeamId=\{effectiveSelectedTeamId \?\? null\}/);
  assert.match(chatInputPanelRenderersSource, /navigateToCreate = contribution\.createPath/);
  assert.match(chatInputPanelRenderersSource, /navigateToManage = contribution\.managePath/);
  assert.doesNotMatch(chatInputPanelRenderersSource, /agentTeamSelectedTeamOptionPath/);
  assert.doesNotMatch(chatInputPanelRenderersSource, /onOpenTeamBuilder/);
  assert.doesNotMatch(chatInputSource, /onOpenTeamBuilder/);
  assert.doesNotMatch(selectorsSource, /onOpenTeamBuilder/);
  assert.doesNotMatch(chatViewSource, /onOpenTeamBuilder/);
  assert.doesNotMatch(chatViewPropsSource, /onOpenTeamBuilder/);
  assert.doesNotMatch(toolbarSource, /selectedTeamId\?: string \| null/);
  assert.doesNotMatch(toolbarSource, /onSelectTeam\?:/);
  assert.doesNotMatch(selectorsSource, /selectedTeamId\?: string \| null/);
  assert.doesNotMatch(selectorsSource, /onSelectTeam\?:/);
  assert.doesNotMatch(chatInputPanelRenderersSource, /onSelectTeam\?:/);
  assert.doesNotMatch(chatInputSelectedRenderersSource, /onSelectTeam\?:/);
  assert.doesNotMatch(chatInputSource, /<ChatInputToolbar[\s\S]*selectedTeamId=\{selectedTeamId\}/);
  assert.doesNotMatch(chatInputSource, /<ChatInputSelectors[\s\S]*onSelectTeam=\{onSelectTeam\}/);
  assert.doesNotMatch(chatInputSource, /onSelectTeam\?\.\(typeof value === "string"/);
  assert.match(chatInputSource, /pluginOptionValues=\{pluginOptionValues\}/);
  assert.match(chatInputSource, /onPluginOptionChange=\{handlePluginOptionChange\}/);
  assert.match(chatInputSource, /return providedPluginOptionValues \?\? \{\}/);
  assert.doesNotMatch(chatInputSource, /withSelectedAgentTeamId/);
  assert.doesNotMatch(chatInputSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("team selector uses the persona selector interaction surfaces", () => {
  assert.match(toolbarSource, /pluginOptions=\{chatInputOptions\}/);
  assert.doesNotMatch(toolbarSource, /hasTeamSelector=/);
  assert.match(
    toolbarSource,
    /hasPersonaSelector=\{corePersonaSelectorVisible\}/,
  );
  assert.doesNotMatch(toolbarSource, /currentAgent !== "team"/);
  assert.match(toolbarSource, /suppressesCorePersonaSelector/);
  assert.doesNotMatch(toolbarSource, /onSelectTeam\?\.\(null\)/);
  assert.match(chatInputSelectedRenderersSource, /const optionPath = option\.optionBinding/);
  assert.match(chatInputSelectedRenderersSource, /pluginOptionFromValues\(pluginOptionValues, optionPath\.pluginId, optionPath\.key\)/);
  assert.match(chatInputSelectedRenderersSource, /onPluginOptionChange\?\.\(optionPath\.pluginId, optionPath\.key, null\)/);
  assert.doesNotMatch(chatInputSelectedRenderersSource, /agentTeamSelectedTeamOptionPath/);
  assert.doesNotMatch(chatInputSelectedRenderersSource, /onSelectTeam\?\.\(null\)/);
  assert.match(toolbarSource, /group-hover:opacity-0/);
  assert.doesNotMatch(featureMenuSource, /hasTeamSelector/);
  assert.match(featureMenuSource, /uploadPluginOptions = pluginOptions\.filter/);
  assert.match(featureMenuSource, /settingsPluginOptions = pluginOptions\.filter/);
  assert.match(featureMenuSource, /enhancePluginOptions = pluginOptions\.filter/);
  assert.match(featureMenuSource, /uploadPluginOptions\.map\(renderPluginOption\)/);
  assert.match(featureMenuSource, /enhancePluginOptions\.map\(renderPluginOption\)/);
  assert.match(featureMenuSource, /settingsPluginOptions\.map\(renderPluginOption\)/);
  assert.match(featureMenuSource, /label=\{t\(option\.label\)\}/);
  assert.match(featureMenuSource, /onOpen\(option\.panel \?\? option\.id\)/);
  assert.doesNotMatch(featureMenuSource, /onOpen\("team"\)/);
  assert.match(chatInputSource, /matchesPluginShortcut\(option\.shortcut, e\)/);
  assert.match(chatInputSource, /\^mod\\\+\(\[a-z\]\)\$/);
  assert.doesNotMatch(chatInputSource, /agent_team:team-picker/);
  assert.match(
    teamPickerSource,
    /z-\[250\][\s\S]*sm:max-w-3xl[\s\S]*xl:max-w-6xl/,
  );
  assert.match(teamPickerSource, /grid auto-grid-cols gap-3/);
  assert.match(teamPickerSource, /pps-card__action/);
  assert.match(teamPickerSource, /handleSelect\(team\.id\)/);
  assert.match(teamPickerSource, /onSelect\(teamId\)/);
  assert.doesNotMatch(teamPickerSource, /sm:w-\[420px\]/);
});

test("assistant message header shows the selected team in team mode", () => {
  assert.match(chatViewSource, /runtimePlugins/);
  assert.match(chatViewSource, /useChatAssistantIdentity\(\{/);
  assert.doesNotMatch(chatViewSource, /useCurrentTeam/);
  assert.doesNotMatch(chatViewPropsSource, /teamApi/);
  assert.doesNotMatch(chatViewPropsSource, /getTeamFallbackAvatar/);
  assert.doesNotMatch(chatViewPropsSource, /selectedAgentTeamIdFromMetadata/);
  assert.match(chatViewPropsSource, /pluginOptionValues: PluginOptionsMetadata/);
  assert.match(chatViewPropsSource, /usePluginChatAssistantIdentity/);
  assert.doesNotMatch(chatViewSource, /selectedPluginTeamId/);
  assert.match(chatViewSource, /selectedTeamId=\{selectedTeamId\}/);
  assert.match(chatAssistantIdentityRenderersSource, /CHAT_ASSISTANT_IDENTITY_RESOLVERS/);
  assert.match(chatAssistantIdentityRenderersSource, /buildAssistantIdentityResolverContributions/);
  assert.match(chatAssistantIdentityRenderersSource, /optionBinding/);
  assert.match(chatAssistantIdentityRenderersSource, /pluginOptionFromValues/);
  assert.match(chatAssistantIdentityRenderersSource, /"..\/team\/teamAvatarUtils"/);
  assert.doesNotMatch(chatAssistantIdentityRenderersSource, /hasAgentCatalogEntryContribution/);
  assert.doesNotMatch(chatAssistantIdentityRenderersSource, /AGENT_TEAM_LEGACY_AGENT_ID/);
  assert.match(chatAssistantIdentityRenderersSource, /contributionAgentId/);
  assert.match(chatAssistantIdentityRenderersSource, /contribution\.agentId !== currentAgent/);
  assert.match(chatAssistantIdentityRenderersSource, /agent_team\.TeamAssistantIdentity/);
  assert.doesNotMatch(chatAssistantIdentityRenderersSource, /selectedTeamId: string \| null/);
  assert.match(chatViewSource, /personaAvatar=\{assistantIdentity\.avatar\}/);
  assert.match(chatViewSource, /personaName=\{assistantIdentity\.name\}/);
  assert.match(
    chatMessageSource,
    /\{personaName \|\| t\("chat\.message\.assistant"\)\}/,
  );
});

test("message plugin actions render through the static renderer registry", () => {
  assert.match(chatMessageSource, /MESSAGE_ACTION_RENDERERS/);
  assert.match(chatMessageSource, /buildMessageActionContributions\(runtimePlugins, \{/);
  assert.match(chatMessageSource, /target: "assistant_message"/);
  assert.match(chatMessageSource, /rendererId = contribution\.renderer/);
  assert.doesNotMatch(chatMessageSource, /FeedbackButtons/);
  assert.match(messageActionRenderersSource, /"feedback\.FeedbackButtons"/);
  assert.match(messageActionRenderersSource, /FeedbackButtons/);
  assert.doesNotMatch(chatMessageSource, /hasMessageActionContribution/);
  assert.doesNotMatch(chatMessageSource, /canUseFeedbackAction/);
});
