import { describe, expect, test } from "vitest";

import { parseRequestHeadersInput } from "../requestHeadersInput";

describe("parseRequestHeadersInput", () => {
  test("empty input clears the override", () => {
    expect(parseRequestHeadersInput("")).toEqual({ ok: true, headers: undefined });
    expect(parseRequestHeadersInput("   ")).toEqual({
      ok: true,
      headers: undefined,
    });
  });

  test("parses a JSON object of headers", () => {
    expect(
      parseRequestHeadersInput('{"User-Agent": "my-agent/1.0", "x-app": "cli"}'),
    ).toEqual({
      ok: true,
      headers: { "User-Agent": "my-agent/1.0", "x-app": "cli" },
    });
  });

  test("coerces non-string values to strings", () => {
    expect(parseRequestHeadersInput('{"X-Retry": 3}')).toEqual({
      ok: true,
      headers: { "X-Retry": "3" },
    });
  });

  test("rejects malformed JSON", () => {
    expect(parseRequestHeadersInput("{not json")).toEqual({
      ok: false,
      error: "invalidJson",
    });
  });

  test("rejects non-object JSON", () => {
    expect(parseRequestHeadersInput('["User-Agent"]')).toEqual({
      ok: false,
      error: "notObject",
    });
    expect(parseRequestHeadersInput('"UA"')).toEqual({
      ok: false,
      error: "notObject",
    });
  });
});
