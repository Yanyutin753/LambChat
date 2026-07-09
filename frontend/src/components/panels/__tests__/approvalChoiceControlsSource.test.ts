import { readFileSync } from "node:fs";
function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("approval panel renders radio and multi-select fields as explicit choice controls", () => {
  const source = readSource("../ApprovalPanel.tsx");

  expect(source).toMatch(/case "radio":/);
  expect(source).toMatch(/approval-choice-list/);
  expect(source).toMatch(/approval-choice-option--selected/);
  expect(source).toMatch(/CircleDot/);
  expect(source).toMatch(/SquareCheck/);
});

test("ask human history snapshot mirrors choice controls", () => {
  const source = readSource("../../chat/ChatMessage/items/AskHumanItem.tsx");

  expect(source).toMatch(/field\.type === "radio"/);
  expect(source).toMatch(/approval-choice-option--readonly/);
  expect(source).toMatch(/approval-choice-option--selected/);
});
