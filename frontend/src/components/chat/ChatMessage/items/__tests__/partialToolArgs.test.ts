import { describe, expect, test } from "vitest";

import { parsePartialToolArgs } from "../partialToolArgs";

describe("parsePartialToolArgs — 非法/空前缀", () => {
  test("空字符串返回空对象", () => {
    expect(parsePartialToolArgs("")).toEqual({});
  });

  test("非对象前缀（裸文本、数组）返回空对象", () => {
    expect(parsePartialToolArgs("not json")).toEqual({});
    expect(parsePartialToolArgs('["a",')).toEqual({});
  });

  test("只有开括号返回空对象", () => {
    expect(parsePartialToolArgs("{")).toEqual({});
  });
});

describe("parsePartialToolArgs — 完整键值对", () => {
  test("完整 JSON 对象全部解析", () => {
    expect(
      parsePartialToolArgs('{"file_path":"/tmp/a.py","offset":10,"limit":null}'),
    ).toEqual({ file_path: "/tmp/a.py", offset: 10, limit: null });
  });

  test("支持布尔字面量", () => {
    expect(parsePartialToolArgs('{"force":true,"dry":false}')).toEqual({
      force: true,
      dry: false,
    });
  });

  test("完整嵌套对象与数组按原样解析", () => {
    expect(
      parsePartialToolArgs('{"opts":{"a":1},"tags":["x","y"]}'),
    ).toEqual({ opts: { a: 1 }, tags: ["x", "y"] });
  });

  test("键后缺冒号时保留更早的键值对", () => {
    expect(parsePartialToolArgs('{"a":1,"b"')).toEqual({ a: 1 });
  });
});

describe("parsePartialToolArgs — 生成中的字符串值", () => {
  test("未闭合字符串按当前累积内容输出（路径逐字增长）", () => {
    expect(parsePartialToolArgs('{"file_path":"/tmp/ma')).toEqual({
      file_path: "/tmp/ma",
    });
  });

  test("保留生成中字符串之前的完整键值对", () => {
    expect(parsePartialToolArgs('{"path":"/tmp","content":"line1\nline')).toEqual({
      path: "/tmp",
      content: "line1\nline",
    });
  });

  test("解码生成中字符串里的 JSON 转义", () => {
    expect(parsePartialToolArgs('{"content":"a\\"b\\n\\tc')).toEqual({
      content: 'a"b\n\tc',
    });
  });

  test("解码 \\u 转义", () => {
    expect(parsePartialToolArgs('{"content":"\\u4f60\\u597d')).toEqual({
      content: "你好",
    });
  });

  test("结尾孤立的反斜杠不进值（等下一个转义字符）", () => {
    expect(parsePartialToolArgs('{"content":"abc\\')).toEqual({
      content: "abc",
    });
  });

  test("闭合字符串内的转义正常解码", () => {
    expect(parsePartialToolArgs('{"content":"a\\"b","n":1}')).toEqual({
      content: 'a"b',
      n: 1,
    });
  });
});

describe("parsePartialToolArgs — 截断的键与标量", () => {
  test("截断的键（尚未闭合）被丢弃", () => {
    expect(parsePartialToolArgs('{"file_pa')).toEqual({});
  });

  test("截断的数字取有效数值前缀", () => {
    expect(parsePartialToolArgs('{"offset":12')).toEqual({ offset: 12 });
    expect(parsePartialToolArgs('{"rate":0.5')).toEqual({ rate: 0.5 });
  });

  test("无效数字前缀（如悬空指数）丢弃该键", () => {
    expect(parsePartialToolArgs('{"x":1e')).toEqual({});
  });

  test("截断的布尔/字面量（tru / nul）丢弃该键", () => {
    expect(parsePartialToolArgs('{"a":1,"v":tru')).toEqual({ a: 1 });
    expect(parsePartialToolArgs('{"a":1,"v":nul')).toEqual({ a: 1 });
  });
});

describe("parsePartialToolArgs — 嵌套值截断", () => {
  test("未闭合的嵌套对象丢弃该键、保留更早键值对", () => {
    expect(parsePartialToolArgs('{"path":"/tmp","opts":{"a":1')).toEqual({
      path: "/tmp",
    });
  });

  test("未闭合的数组丢弃该键", () => {
    expect(parsePartialToolArgs('{"tags":["x",')).toEqual({});
  });

  test("值后截断（无逗号无闭括号）保留已解析内容", () => {
    expect(parsePartialToolArgs('{"a":1,"b":2')).toEqual({ a: 1, b: 2 });
  });
});
