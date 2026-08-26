import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../UserMessageBubble.tsx", import.meta.url),
  "utf8",
);
const chatCss = readFileSync(
  new URL("../../../../styles/chat.css", import.meta.url),
  "utf8",
);
const skillChipSource = readFileSync(
  new URL("../../SkillChip.tsx", import.meta.url),
  "utf8",
);
const fileReferenceSource = readFileSync(
  new URL("../../richComposer/FileReferenceChip.tsx", import.meta.url),
  "utf8",
);

test("user message skill chips and text share the same inline flow", () => {
  expect(source).toMatch(/className="inline leading-relaxed/);
  expect(source).toMatch(/className="skill-chip-row align-baseline/);
  expect(source).toMatch(/FileReferenceChip/);
  expect(source).toMatch(/splitUserMessageFileReferences/);
  expect(source).not.toMatch(/className="skill-chip-row shrink-0"/);
  expect(source).not.toMatch(/flex-1/);
  expect(chatCss).toMatch(
    /\.skill-chip-node-name\s*\{[^}]*font-size:\s*inherit/s,
  );
  // 名称节点随全局 serif 特性使用 font-serif；字号/字重仍由 CSS inherit 保持内联一致
  expect(skillChipSource).toMatch(/skill-chip-node-name[^"]*font-serif/);
  expect(fileReferenceSource).toMatch(/skill-chip-node-name[^"]*font-serif/);
  expect(skillChipSource).not.toMatch(/font-semibold/);
  expect(fileReferenceSource).not.toMatch(/font-semibold/);
  expect(chatCss).toMatch(
    /\.skill-chip-node\s*\{[^}]*align-items:\s*baseline[^}]*vertical-align:\s*baseline[^}]*line-height:\s*inherit/s,
  );
  expect(chatCss).not.toMatch(/\.skill-chip-node\s*\{[^}]*\n\s*height:/s);
  expect(chatCss).toMatch(
    /\.composer-skill-reference\s*\{[^}]*display:\s*inline[^}]*vertical-align:\s*baseline/s,
  );
  expect(chatCss).not.toMatch(
    /\.composer-reference-chip\s*\{[^}]*min-height:/s,
  );
  expect(fileReferenceSource).toMatch(/Paperclip/);
  expect(fileReferenceSource).not.toMatch(/composer-file-reference__avatar/);
  expect(chatCss).toMatch(
    /\.user-message-inline-markdown \.markdown-preview > p:first-child\s*\{[^}]*line-height:\s*inherit[^}]*color:\s*inherit/s,
  );
  expect(chatCss).toMatch(
    /\.skill-chip-node-name\s*\{[^}]*font-size:\s*inherit[^}]*font-weight:\s*inherit[^}]*line-height:\s*inherit/s,
  );
});
