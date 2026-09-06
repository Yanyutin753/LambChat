import { describe, expect, test } from "vitest";

import {
  formatRequestHeaders,
  parseRequestHeadersInput,
} from "../requestHeadersInput";

describe("formatRequestHeaders", () => {
  test("formats stored headers as pretty JSON", () => {
    expect(formatRequestHeaders({ "x-app": "cli" })).toBe(
      '{\n  "x-app": "cli"\n}',
    );
  });

  test("empty or missing headers render as empty string", () => {
    expect(formatRequestHeaders(undefined)).toBe("");
    expect(formatRequestHeaders(null)).toBe("");
    expect(formatRequestHeaders({})).toBe("");
  });

  test("round-trips through the parser", () => {
    const headers = { "User-Agent": "relay/1", "X-Extra": "2" };
    expect(parseRequestHeadersInput(formatRequestHeaders(headers))).toEqual({
      ok: true,
      headers,
    });
  });
});

describe("parseRequestHeadersInput", () => {
  test("empty input clears the override", () => {
    expect(parseRequestHeadersInput("")).toEqual({
      ok: true,
      headers: undefined,
    });
    expect(parseRequestHeadersInput("   ")).toEqual({
      ok: true,
      headers: undefined,
    });
  });

  test("parses a JSON object of headers", () => {
    expect(
      parseRequestHeadersInput(
        '{"User-Agent": "my-agent/1.0", "x-app": "cli"}',
      ),
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
