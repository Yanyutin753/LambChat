import { expect, test } from "vitest";
import { parseChannelEnv, formatChannelEnv } from "../channelRuntimeConfig";

test("environment edits preserve equals, spaces, masked values and explicit empty values", () => {
  expect(parseChannelEnv("TOKEN=***\nURL=https://example.test?a=b\nPAD= value \nEMPTY=\n")).toEqual({
    TOKEN: "***", URL: "https://example.test?a=b", PAD: " value ", EMPTY: "",
  });
  expect(parseChannelEnv("")).toEqual({});
  expect(formatChannelEnv({ TOKEN: "***" })).toBe("TOKEN=***");
});

test.each(["MISSING", "1BAD=value", "KEY=one\nKEY=two", "KEY=bad\0value"])(
  "invalid environment draft cannot silently change variables: %s", (text) => {
    expect(() => parseChannelEnv(text)).toThrow();
  },
);

test("environment input respects bounded variable counts and values", () => {
  expect(() => parseChannelEnv(`${"A".repeat(257)}=value`)).toThrow();
  expect(() => parseChannelEnv(Array.from({ length: 51 }, (_, i) => `K${i}=v`).join("\n"))).toThrow();
  expect(() => parseChannelEnv(`TOKEN=${"x".repeat(16001)}`)).toThrow();
  expect(() => parseChannelEnv(Array.from({ length: 5 }, (_, i) => `K${i}=${"x".repeat(16000)}`).join("\n"))).toThrow();
});

test.each(["LAMBCHAT_WORKSPACE", "LAMBCHAT_SHARED"])("protected sandbox variable %s cannot be overridden", (key) => {
  expect(() => parseChannelEnv(`${key}=/override`)).toThrow("channel.runtime.envProtected");
});
