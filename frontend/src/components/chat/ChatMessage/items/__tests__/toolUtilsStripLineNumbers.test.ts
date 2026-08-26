import { stripLineNumbers, readFileStartLine } from "../toolUtils.ts";

test("readFileStartLine converts 0-based offset to 1-based first line", () => {
  expect(readFileStartLine(130)).toBe(131);
  expect(readFileStartLine(0)).toBe(1);
});

test("readFileStartLine defaults to line 1 without offset", () => {
  expect(readFileStartLine(undefined)).toBe(1);
});

test("readFileStartLine clamps negative offsets to line 1", () => {
  expect(readFileStartLine(-5)).toBe(1);
});

test("strips two-space separated line numbers from deepagents read output", () => {
  expect(stripLineNumbers("1  # PDF中文商业报告生成器")).toBe(
    "# PDF中文商业报告生成器",
  );
});

test("strips line numbers from a multi-line read_file result", () => {
  const raw = "1  # PDF中文商业报告生成器\n2  \n3  ## name: pdf-cn-biz-report";
  expect(stripLineNumbers(raw)).toBe(
    "# PDF中文商业报告生成器\n\n## name: pdf-cn-biz-report",
  );
});

test("strips right-justified line numbers padded to gutter width", () => {
  expect(stripLineNumbers(" 10  export function foo() {}")).toBe(
    "export function foo() {}",
  );
});

test("strips continuation chunk markers with two-space separator", () => {
  expect(stripLineNumbers("5.1  ...continued chunk")).toBe(
    "...continued chunk",
  );
});

test("still strips legacy cat -n tab separated line numbers", () => {
  expect(stripLineNumbers("     1\told format")).toBe("old format");
});

test("still strips arrow separated line numbers", () => {
  expect(stripLineNumbers("7→arrow format")).toBe("arrow format");
});

test("keeps content lines that only start with a number and single space", () => {
  expect(stripLineNumbers("1 item")).toBe("1 item");
});
