import { parseEvalWireResult } from "../evalWireResult.ts";

test("parses a plain result value with its kind", () => {
  expect(parseEvalWireResult('<result kind="number">121932631112635269</result>')).toEqual({
    kind: "number",
    value: "121932631112635269",
  });
});

test("parses result without a kind attribute", () => {
  expect(parseEvalWireResult("<result>\"hello\"</result>")).toEqual({
    kind: undefined,
    value: '"hello"',
  });
});

test("maps a missing result body to undefined", () => {
  expect(parseEvalWireResult("<result>undefined</result>")).toEqual({
    kind: undefined,
    value: "undefined",
  });
});

test("parses stdout and result together", () => {
  expect(
    parseEvalWireResult(
      "<stdout>\nfirst\nsecond\n</stdout>\n<result kind=\"string\">\"done\"</result>",
    ),
  ).toEqual({
    stdout: "first\nsecond",
    kind: "string",
    value: '"done"',
  });
});

test("parses an error outcome with its type", () => {
  expect(
    parseEvalWireResult('<error type="SyntaxError">unexpected token in expression: &lt;div&gt;</error>'),
  ).toEqual({
    error: {
      type: "SyntaxError",
      message: "unexpected token in expression: <div>",
    },
  });
});

test("unescapes xml entities in the result body", () => {
  expect(parseEvalWireResult("<result>a &amp; b &lt; c</result>")).toEqual({
    kind: undefined,
    value: "a & b < c",
  });
});

test("returns null for plain text without wire tags", () => {
  expect(parseEvalWireResult("just some output")).toBeNull();
  expect(parseEvalWireResult("")).toBeNull();
});
