import { afterEach, expect, test } from "vitest";
import i18n from "../../../../i18n";
import { formatSubagentInput, formatSubagentName } from "../subagentRoleMeta";

const originalLanguage = i18n.language;
afterEach(async () => {
  await i18n.changeLanguage(originalLanguage);
});

test.each([
  ["zh", "验收评分助手", "验收标准评估"],
  ["en", "Rubric Grader", "Rubric evaluation"],
  ["ja", "評価基準採点アシスタント", "評価基準による評価"],
  ["ko", "평가 기준 채점 도우미", "평가 기준에 따른 평가"],
  ["ru", "Ассистент оценки по критериям", "Оценка по заданным критериям"],
])(
  "uses a status-neutral grader title for both completed and running cards in %s",
  async (language, name, input) => {
    await i18n.changeLanguage(language);
    expect(formatSubagentName("Rubric Grader")).toBe(name);
    expect(formatSubagentName("rubric_grader")).toBe(name);
    expect(
      formatSubagentInput(
        "Rubric Grader",
        "Evaluating against rubric criteria",
      ),
    ).toBe(input);
  },
);

test("preserves custom names and task text", async () => {
  await i18n.changeLanguage("zh");
  expect(formatSubagentName("custom_reviewer")).toBe("Custom Reviewer");
  expect(formatSubagentInput("Rubric Grader", "My own criteria")).toBe(
    "My own criteria",
  );
  expect(
    formatSubagentInput("Custom", "Evaluating against rubric criteria"),
  ).toBe("Evaluating against rubric criteria");
});
