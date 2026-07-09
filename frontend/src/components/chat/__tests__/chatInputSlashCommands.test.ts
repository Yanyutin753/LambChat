import {
  CHAT_INPUT_SLASH_COMMANDS,
  applySlashCommandSelection,
  clearSlashCommandInput,
  getMatchingSlashCommands,
  getMatchingSlashDropdownItems,
  getSlashDropdownSections,
  getSlashCommandQuery,
} from "../chatInputSlashCommands.ts";
import type { SkillResponse } from "../../../types";

const mockSkills: SkillResponse[] = [
  {
    name: "deep-research",
    description: "Deep research harness",
    tags: [],
    enabled: true,
    source: "marketplace",
    file_count: 0,
    files: {},
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: false,
  },
  {
    name: "code-review",
    description: "Code review assistant",
    tags: [],
    enabled: true,
    source: "manual",
    file_count: 0,
    files: {},
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: false,
  },
  {
    name: "team-builder",
    description: "Build teams easily",
    tags: [],
    enabled: true,
    source: "marketplace",
    file_count: 0,
    files: {},
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: false,
  },
];

// ── Legacy getMatchingSlashCommands ────────────────────────────────

test("finds the goal command while typing a slash command prefix", () => {
  expect(getSlashCommandQuery("/go", 3)).toBe("go");
  expect(getMatchingSlashCommands("/go", 3)).toEqual([
    CHAT_INPUT_SLASH_COMMANDS[0],
  ]);
});

test("finds panel commands while typing a slash command prefix", () => {
  expect(
    getMatchingSlashCommands("/to", 3).map((command) => command.id),
  ).toEqual(["tools"]);
  expect(
    getMatchingSlashCommands("/t", 2).map((command) => command.id),
  ).toEqual(["tools", "team"]);
});

test("does not show slash commands after text content has started", () => {
  expect(getSlashCommandQuery("please /go", 10)).toBe(null);
  expect(getMatchingSlashCommands("/goal write docs", 16)).toEqual([]);
});

test("selecting goal command inserts a trailing space for direct goal text", () => {
  expect(
    applySlashCommandSelection("/go", 3, CHAT_INPUT_SLASH_COMMANDS[0]),
  ).toEqual({
    input: "/goal ",
    cursorPosition: 6,
  });
});

// ── clearSlashCommandInput ────────────────────────────────────────

test("clears slash prefix from input", () => {
  expect(clearSlashCommandInput("/deep-research", 14)).toEqual({
    input: "",
    cursorPosition: 0,
  });
  expect(clearSlashCommandInput("/go", 3)).toEqual({
    input: "",
    cursorPosition: 0,
  });
  expect(clearSlashCommandInput("hello", 5)).toEqual({
    input: "hello",
    cursorPosition: 5,
  });
});

// ── getMatchingSlashDropdownItems ──────────────────────────────────

test("matches enabled skills by name prefix", () => {
  const items = getMatchingSlashDropdownItems("/deep", 5, mockSkills);
  expect(items.length).toBe(1);
  expect(items[0].type).toBe("skill");
  if (items[0].type === "skill") {
    expect(items[0].skill.name).toBe("deep-research");
    expect(items[0].skill.description).toBe("Deep research harness");
  }
});

test("does not match skills when not provided", () => {
  const items = getMatchingSlashDropdownItems("/code", 5, undefined);
  const skills = items.filter((i) => i.type === "skill");
  expect(skills.length).toBe(0);
});

test("returns both commands and skills mixed", () => {
  const items = getMatchingSlashDropdownItems("/t", 2, mockSkills);
  // Should match /tools, /team (commands) and team-builder (skill)
  expect(items.length).toBe(3);
  expect(items[0].type).toBe("command");
  expect(items[1].type).toBe("command");
  expect(items[2].type).toBe("skill");
  if (items[2].type === "skill") {
    expect(items[2].skill.name).toBe("team-builder");
  }
});

test("returns only commands when no skills match", () => {
  const items = getMatchingSlashDropdownItems("/p", 2, mockSkills);
  expect(items.length).toBe(1);
  expect(items[0].type).toBe("command");
  if (items[0].type === "command") {
    expect(items[0].command.id).toBe("persona");
  }
});

test("returns only skills when no commands match", () => {
  const items = getMatchingSlashDropdownItems("/code", 5, mockSkills);
  expect(items.length).toBe(1);
  expect(items[0].type).toBe("skill");
  if (items[0].type === "skill") {
    expect(items[0].skill.name).toBe("code-review");
  }
});

test("empty array when no match", () => {
  expect(getMatchingSlashDropdownItems("/xyz", 4, mockSkills)).toEqual([]);
});

// ── getSlashDropdownSections ───────────────────────────────────────

test("groups items into commands and skills sections", () => {
  const items = [
    { type: "command" as const, command: CHAT_INPUT_SLASH_COMMANDS[0] },
    {
      type: "skill" as const,
      skill: { name: "test", description: "Test skill", tags: ["code"] },
    },
  ];
  const sections = getSlashDropdownSections(items);
  expect(sections.length).toBe(2);
  expect(sections[0].kind).toBe("commands");
  expect(sections[0].items.length).toBe(1);
  expect(sections[1].kind).toBe("skills");
  expect(sections[1].items.length).toBe(1);
});

test("only returns commands section when no skills", () => {
  const items = [
    { type: "command" as const, command: CHAT_INPUT_SLASH_COMMANDS[0] },
  ];
  const sections = getSlashDropdownSections(items);
  expect(sections.length).toBe(1);
  expect(sections[0].kind).toBe("commands");
});

test("only returns skills section when no commands", () => {
  const items = [
    {
      type: "skill" as const,
      skill: { name: "test", description: "Test skill", tags: [] },
    },
  ];
  const sections = getSlashDropdownSections(items);
  expect(sections.length).toBe(1);
  expect(sections[0].kind).toBe("skills");
});

test("returns empty array when no items", () => {
  const sections = getSlashDropdownSections([]);
  expect(sections).toEqual([]);
});
