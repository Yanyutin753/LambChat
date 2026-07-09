import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  getSelectedPersonaStarterPrompts,
  getSelectedTeamStarterPrompts,
  getWelcomePersonaCards,
  getWelcomePersonaCardClass,
  getWelcomePersonaSkeletonCount,
  getWelcomeSuggestionsContainerClass,
  getWelcomeSuggestionButtonClass,
} from "../welcomeLayout.ts";

const currentDir = dirname(fileURLToPath(import.meta.url));
const welcomeCss = readFileSync(
  resolve(currentDir, "../../../styles/welcome.css"),
  "utf8",
);
const welcomePageSource = readFileSync(
  resolve(currentDir, "../WelcomePage.tsx"),
  "utf8",
);
const chatSkeletonsSource = readFileSync(
  resolve(currentDir, "../../skeletons/ChatSkeletons.tsx"),
  "utf8",
);

test("keeps every welcome persona card reachable on mobile", () => {
  const className = getWelcomePersonaCardClass(3);

  expect(className.includes("welcome-persona-card")).toBe(true);
  expect(className.includes("hidden sm:flex")).toBe(false);
});

test("keeps later starter prompt pills reachable on narrow screens", () => {
  const className = getWelcomeSuggestionButtonClass(2);

  expect(className.includes("welcome-suggestion-pill")).toBe(true);
  expect(className.includes("hidden sm:flex")).toBe(false);
});

test("caps welcome suggestion prompts to two rows with vertical scrolling", () => {
  expect(welcomeCss).toMatch(
    /\.welcome-suggestions-grid-wrapper\s*\{[\s\S]*--welcome-suggestion-row-height: 2\.5rem;/,
  );
  expect(welcomeCss).toMatch(
    /\.welcome-suggestions-grid-wrapper\s*\{[\s\S]*var\(--welcome-suggestion-row-height\) \* 2 \+[\s\S]*var\(--welcome-suggestion-row-gap\)[\s\S]*overflow-y: auto;/,
  );
});

test("caps welcome persona choices to two rows with vertical scrolling", () => {
  expect(welcomeCss).toMatch(
    /@media \(min-width: 640px\) \{[\s\S]*\.welcome-persona-gallery\s*\{[\s\S]*--welcome-persona-card-height: 6rem;/,
  );
  expect(welcomeCss).toMatch(
    /@media \(min-width: 640px\) \{[\s\S]*\.welcome-persona-gallery\s*\{[\s\S]*var\(--welcome-persona-card-height\) \* 2 \+ var\(--welcome-persona-row-gap\)[\s\S]*overflow-y: auto;/,
  );
});

test("keeps welcome content centered on mobile when suggestions are visible", () => {
  expect(welcomeCss).toMatch(
    /\.welcome-root\s*\{[\s\S]*justify-content: safe center;/,
  );
  expect(welcomeCss).not.toMatch(
    /@media \(max-width: 639px\) \{[\s\S]*\.welcome-root\s*\{[\s\S]*justify-content: flex-start;/,
  );
});

test("keeps mobile welcome cards readable with stable touch targets", () => {
  expect(welcomeCss).toMatch(
    /@media \(max-width: 639px\) \{[\s\S]*\.welcome-persona-gallery\s*\{[\s\S]*--welcome-persona-card-height: 4\.75rem;/,
  );
  expect(welcomeCss).toMatch(
    /@media \(max-width: 639px\) \{[\s\S]*\.welcome-suggestions-grid-wrapper\s*\{[\s\S]*max-height: min\(\s*35dvh,/,
  );
});

test("keeps starter prompt container narrower than persona gallery", () => {
  expect(getWelcomeSuggestionsContainerClass("prompts")).toMatch(
    /sm:max-w-\[44rem\]/,
  );
  expect(getWelcomeSuggestionsContainerClass("personas")).toMatch(
    /sm:max-w-\[44rem\]/,
  );
});

test("shows persona cards before a welcome persona is selected", () => {
  const cards = getWelcomePersonaCards(
    [
      { id: "writer", name: "Writer", starter_prompts: [] },
      { id: "coder", name: "Coder", starter_prompts: [] },
      { id: "planner", name: "Planner", starter_prompts: [] },
    ],
    null,
    2,
  );

  expect(cards.map((card) => card.id)).toEqual(["writer", "coder"]);
});

test("shows all welcome persona cards with pinned and favorite cards first", () => {
  const cards = getWelcomePersonaCards(
    [
      { id: "normal", name: "Normal", starter_prompts: [], usage_count: 10 },
      {
        id: "favorite",
        name: "Favorite",
        starter_prompts: [],
        is_favorite: true,
      },
      {
        id: "pinned",
        name: "Pinned",
        starter_prompts: [],
        is_pinned: true,
      },
    ],
    null,
  );

  expect(cards.map((card) => card.id)).toEqual([
    "pinned",
    "favorite",
    "normal",
  ]);
});

test("shows welcome choice skeletons only while the first page is loading", () => {
  expect(getWelcomePersonaSkeletonCount(true, 0)).toBe(12);
  expect(getWelcomePersonaSkeletonCount(true, 2)).toBe(0);
  expect(getWelcomePersonaSkeletonCount(false, 0)).toBe(0);
});

test("renders twelve welcome skeleton cards in shared chat loading state", () => {
  expect(chatSkeletonsSource).toMatch(/Array\.from\(\{\s*length:\s*12\s*\}\)/);
});

test("expands welcome choice gallery while skeleton cards are loading", () => {
  expect(welcomePageSource).toMatch(/welcome-persona-gallery--loading/);
  expect(chatSkeletonsSource).toMatch(/welcome-persona-gallery--loading/);
});

test("uses only the selected persona starter prompts after a welcome persona is selected", () => {
  const prompts = getSelectedPersonaStarterPrompts(
    [
      {
        id: "writer",
        name: "Writer",
        starter_prompts: [{ icon: "✍️", text: "写一段开场白" }],
      },
      {
        id: "coder",
        name: "Coder",
        starter_prompts: [
          { text: { zh: "帮我审查这段代码", en: "Review this code" } },
        ],
      },
    ],
    "coder",
    "zh-CN",
  );

  expect(prompts).toEqual([{ icon: null, text: "帮我审查这段代码" }]);
});

test("falls back to default suggestions when selected persona has no starter prompts", () => {
  const prompts = getSelectedPersonaStarterPrompts(
    [{ id: "coder", name: "Coder", starter_prompts: [] }],
    "coder",
    "zh-CN",
    [{ icon: "🐍", text: "创建一个 Python 脚本" }],
  );

  expect(prompts).toEqual([{ icon: "🐍", text: "创建一个 Python 脚本" }]);
});

test("uses selected team starter prompts before default suggestions", () => {
  const prompts = getSelectedTeamStarterPrompts(
    [
      {
        id: "team-1",
        name: "Research Team",
        starter_prompts: [
          {
            icon: "🧭",
            text: { zh: "组织一次研究评审", en: "Review research" },
          },
        ],
      },
    ],
    "team-1",
    "zh-CN",
    [{ icon: "✨", text: "默认建议" }],
  );

  expect(prompts).toEqual([{ icon: "🧭", text: "组织一次研究评审" }]);
});
