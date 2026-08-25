import { readFileSync } from "node:fs";
const toolbarSource = readFileSync(
  new URL("../ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);
const selectorsSource = readFileSync(
  new URL("../ChatInputSelectors.tsx", import.meta.url),
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
const chatMessageSource = readFileSync(
  new URL("../ChatMessage/index.tsx", import.meta.url),
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
  expect(toolbarSource).toMatch(
    /selectedPersonaName && currentAgent !== "team"/,
  );
  expect(toolbarSource).toMatch(
    /currentAgent === "team" && onSelectTeam && selectedTeamId/,
  );
  expect(toolbarSource).toMatch(/onActivePanelChange\("team"\)/);
  expect(toolbarSource).toMatch(/chat\.teamSelected/);
  expect(toolbarSource).not.toMatch(/Select team/);
  expect(toolbarSource).toMatch(/color:\s*"var\(--theme-primary\)"/);
  expect(toolbarSource).not.toMatch(/text-amber-500/);
  expect(selectorsSource).toMatch(/TeamPickerModal/);
  expect(selectorsSource).toMatch(/isOpen=\{activePanel === "team"\}/);
  expect(selectorsSource).toMatch(
    /selectedTeamId=\{selectedTeamId \?\? null\}/,
  );
  expect(chatInputSource).toMatch(
    /selectedTeamId=\{selectedTeamId\}[\s\S]*onSelectTeam=\{onSelectTeam\}/,
  );
});

test("team selector uses the persona selector interaction surfaces", () => {
  expect(toolbarSource).toMatch(
    /hasTeamSelector=\{currentAgent === "team" && !!onSelectTeam\}/,
  );
  expect(toolbarSource).toMatch(
    /hasPersonaSelector=\{hasPersonaSelector && currentAgent !== "team"\}/,
  );
  expect(toolbarSource).toMatch(/onSelectTeam\?\.\(null\)/);
  expect(toolbarSource).toMatch(/group-hover:opacity-0/);
  expect(featureMenuSource).toMatch(/hasTeamSelector/);
  expect(featureMenuSource).toMatch(
    /label=\{t\("featureMenu\.team", "团队"\)\}/,
  );
  expect(featureMenuSource).toMatch(/onClick=\{\(\) => onOpen\("team"\)\}/);
  expect(teamPickerSource).toMatch(
    /z-\[290\][\s\S]*sm:max-w-3xl[\s\S]*xl:max-w-6xl/,
  );
  expect(teamPickerSource).toMatch(/grid auto-grid-cols gap-3/);
  expect(teamPickerSource).toMatch(/pps-card__action/);
  expect(teamPickerSource).toMatch(/handleSelect\(team\.id\)/);
  expect(teamPickerSource).toMatch(/onSelect\(teamId\)/);
  expect(teamPickerSource).not.toMatch(/sm:w-\[420px\]/);
});

test("assistant message header shows the selected team in team mode", () => {
  expect(chatViewPropsSource).toMatch(/import \{ teamApi \} from/);
  expect(chatViewPropsSource).toMatch(/function useCurrentTeam/);
  expect(chatViewPropsSource).toMatch(/function resolveChatAssistantIdentity/);
  expect(chatViewPropsSource).toMatch(/getTeamFallbackAvatar/);
  expect(chatViewSource).toMatch(/const assistantIdentity = useMemo\(/);
  expect(chatViewSource).toMatch(/personaAvatar=\{assistantIdentity\.avatar\}/);
  expect(chatViewSource).toMatch(/personaName=\{assistantIdentity\.name\}/);
  expect(chatMessageSource).toMatch(
    /\{personaName \|\| t\("chat\.message\.assistant"\)\}/,
  );
});
