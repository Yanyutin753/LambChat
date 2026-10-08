import { describe, expect, test } from "vitest";
import { parseComputerUseResult } from "../computerUseResult";

describe("computer use results", () => {
  test("uses persisted screenshot file URLs", () => {
    const parsed = parseComputerUseResult({
      screenshot: {
        mime: "image/jpeg",
        url: "/api/upload/file/tool_binaries/test.jpg",
      },
    });
    expect(parsed.screenshotSrc).toBe(
      "/api/upload/file/tool_binaries/test.jpg",
    );
  });
  test("reads structured JSON without dropping zero-valued window metadata", () => {
    const parsed = parseComputerUseResult(
      '{"pid":42,"window":{"window_id":0},"element_count":0,"state":"window: Main"}',
    );
    expect(parsed.data.window).toEqual({ window_id: 0 });
    expect(parsed.data.element_count).toBe(0);
    expect(parsed.text).toContain("window: Main");
  });

  test("reads historical Python status dictionaries without evaluating them", () => {
    const parsed = parseComputerUseResult(
      "{'platform': 'darwin', 'ready': False, 'accessibility': 'denied', 'screen_recording': 'unknown', 'message': None}",
    );
    expect(parsed.data).toEqual({
      platform: "darwin",
      ready: false,
      accessibility: "denied",
      screen_recording: "unknown",
    });
  });

  test("preserves original guidance in historical status results", () => {
    const parsed = parseComputerUseResult(
      "{'ready': False, 'message': 'Enable toolkit accessibility'}",
    );
    expect(parsed.text).toContain("Enable toolkit accessibility");
  });

  test("keeps historical accessibility trees as text", () => {
    const parsed = parseComputerUseResult(
      "window: Main (id=0)\n[0] AXButton 'OK'",
    );
    expect(parsed.data).toEqual({});
    expect(parsed.text).toContain("[0] AXButton 'OK'");
    expect(parsed.error).toBe("");
  });

  test("recognizes textual and structured errors despite a successful transport", () => {
    expect(parseComputerUseResult("ERROR dispatch_failed: offline").error).toBe(
      "dispatch_failed",
    );
    expect(
      parseComputerUseResult({ error: "stale_state", detail: "observe again" })
        .error,
    ).toBe("stale_state");
  });

  test("renders raster screenshots while excluding base64 from raw result text", () => {
    const parsed = parseComputerUseResult({
      state: "window: Main",
      screenshot: {
        mime: "image/jpeg",
        width: 800,
        height: 600,
        data_b64: "YWJjZA==",
      },
    });
    expect(parsed.screenshotSrc).toBe("data:image/jpeg;base64,YWJjZA==");
    expect(parsed.text).not.toContain("YWJjZA==");
    expect(parsed.text).toContain('"width": 800');
  });

  test("rejects active-content image formats", () => {
    expect(
      parseComputerUseResult({
        screenshot: { mime: "image/svg+xml", data_b64: "YWJjZA==" },
      }).screenshotSrc,
    ).toBeUndefined();
  });

  test.each([undefined, "", "{incomplete", "null", "[]", "42"])(
    "tolerates empty or malformed results: %s",
    (result) => {
      expect(parseComputerUseResult(result).data).toEqual({});
    },
  );
});
