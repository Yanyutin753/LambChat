import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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
  assert.match(source, /Search,/);
  assert.match(source, /import \{ PanelSearchInput \}/);
  assert.match(
    source,
    /const \[searchQuery, setSearchQuery\] = useState\(""\)/,
  );
  assert.match(source, /placeholder=\{t\("tools\.searchPlaceholder"\)\}/);
  assert.match(source, /value=\{searchQuery\}/);
  assert.match(source, /onValueChange=\{setSearchQuery\}/);
  assert.doesNotMatch(
    source,
    /onChange=\{\(e\) => setSearchQuery\(e\.target\.value\)\}/,
  );
  assert.match(source, /const renderModalContent = \(\) =>/);
  assert.doesNotMatch(source, /const ModalContent = \(\) =>/);
  assert.doesNotMatch(source, /<ModalContent \/>/);
});

test("skill selector search uses the same editing-safe input", () => {
  assert.match(skillSelectorSource, /Search,/);
  assert.match(skillSelectorSource, /import \{ PanelSearchInput \}/);
  assert.match(
    skillSelectorSource,
    /const \[searchQuery, setSearchQuery\] = useState\(""\)/,
  );
  assert.match(
    skillSelectorSource,
    /placeholder=\{t\("skills\.searchPlaceholder"\)\}/,
  );
  assert.match(skillSelectorSource, /value=\{searchQuery\}/);
  assert.match(skillSelectorSource, /onValueChange=\{setSearchQuery\}/);
  assert.doesNotMatch(
    skillSelectorSource,
    /onChange=\{\(e\) => setSearchQuery\(e\.target\.value\)\}/,
  );
  assert.match(skillSelectorSource, /const renderModalContent = \(\) =>/);
  assert.doesNotMatch(skillSelectorSource, /const ModalContent = \(\) =>/);
  assert.doesNotMatch(skillSelectorSource, /<ModalContent \/>/);
});

test("tool selector filters tools before grouping and pagination", () => {
  assert.match(source, /const filteredTools = useMemo/);
  assert.match(source, /tool\.name/);
  assert.match(source, /tool\.description/);
  assert.match(source, /tool\.server/);
  assert.match(source, /t\(`tools\.categories\.\$\{tool\.category\}`\)/);
  assert.match(source, /tool\.parameters\?\.flatMap/);
  assert.match(source, /total: filteredTools\.length/);
  assert.match(source, /createPagedGroups\(filteredTools/);
  assert.match(source, /total=\{filteredTools\.length\}/);
});

test("tool selector shows an empty search result state", () => {
  assert.match(source, /filteredTools\.length === 0/);
  assert.match(source, /t\("tools\.noMatchingTools"\)/);
});

test("selector modal contents are not remounted on local state changes", () => {
  for (const file of [source, skillSelectorSource, agentModeSelectorSource]) {
    assert.match(file, /const renderModalContent = \(\) =>/);
    assert.doesNotMatch(file, /const ModalContent = \(\) =>/);
    assert.doesNotMatch(file, /<ModalContent \/>/);
  }
});
