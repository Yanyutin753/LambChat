import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ToolSelector.tsx", import.meta.url),
  "utf8",
);
const skillSelectorSource = readFileSync(
  new URL("../SkillSelector.tsx", import.meta.url),
  "utf8",
);
const agentModeSelectorSource = readFileSync(
  new URL("../AgentModeSelector.tsx", import.meta.url),
  "utf8",
);

test("tool selector exposes an editing-safe search module for all tool categories", () => {
  expect(source).toMatch(/Search,/);
  expect(source).toMatch(/import \{ PanelSearchInput \}/);
  expect(source).toMatch(
    /const \[searchQuery, setSearchQuery\] = useState\(""\)/,
  );
  expect(source).toMatch(/placeholder=\{t\("tools\.searchPlaceholder"\)\}/);
  expect(source).toMatch(/value=\{searchQuery\}/);
  expect(source).toMatch(/onValueChange=\{setSearchQuery\}/);
  expect(source).not.toMatch(
    /onChange=\{\(e\) => setSearchQuery\(e\.target\.value\)\}/,
  );
  expect(source).toMatch(/const renderModalContent = \(\) =>/);
  expect(source).not.toMatch(/const ModalContent = \(\) =>/);
  expect(source).not.toMatch(/<ModalContent \/>/);
});

test("skill selector search uses the same editing-safe input", () => {
  expect(skillSelectorSource).toMatch(/Search,/);
  expect(skillSelectorSource).toMatch(/import \{ PanelSearchInput \}/);
  expect(skillSelectorSource).toMatch(
    /const \[searchQuery, setSearchQuery\] = useState\(""\)/,
  );
  expect(skillSelectorSource).toMatch(
    /placeholder=\{t\("skills\.searchPlaceholder"\)\}/,
  );
  expect(skillSelectorSource).toMatch(/value=\{searchQuery\}/);
  expect(skillSelectorSource).toMatch(/onValueChange=\{setSearchQuery\}/);
  expect(skillSelectorSource).not.toMatch(
    /onChange=\{\(e\) => setSearchQuery\(e\.target\.value\)\}/,
  );
  expect(skillSelectorSource).toMatch(/const renderModalContent = \(\) =>/);
  expect(skillSelectorSource).not.toMatch(/const ModalContent = \(\) =>/);
  expect(skillSelectorSource).not.toMatch(/<ModalContent \/>/);
});

test("tool selector filters tools before grouping and pagination", () => {
  expect(source).toMatch(/const filteredTools = useMemo/);
  expect(source).toMatch(/tool\.name/);
  expect(source).toMatch(/tool\.description/);
  expect(source).toMatch(/tool\.server/);
  expect(source).toMatch(/t\(`tools\.categories\.\$\{tool\.category\}`\)/);
  expect(source).toMatch(/tool\.parameters\?\.flatMap/);
  expect(source).toMatch(/total: filteredTools\.length/);
  expect(source).toMatch(/createPagedGroups\(filteredTools/);
  expect(source).toMatch(/total=\{filteredTools\.length\}/);
});

test("tool selector shows an empty search result state", () => {
  expect(source).toMatch(/filteredTools\.length === 0/);
  expect(source).toMatch(/t\("tools\.noMatchingTools"\)/);
});

test("selector modal contents are not remounted on local state changes", () => {
  for (const file of [source, skillSelectorSource, agentModeSelectorSource]) {
    expect(file).toMatch(/const renderModalContent = \(\) =>/);
    expect(file).not.toMatch(/const ModalContent = \(\) =>/);
    expect(file).not.toMatch(/<ModalContent \/>/);
  }
});
