import { describe, it, expect } from "vitest";
import { isSessionPinned } from "../sessionPin";
import type { BackendSession } from "../../../services/api/session";

describe("isSessionPinned", () => {
  it("returns true when metadata.is_pinned is true", () => {
    expect(
      isSessionPinned({ metadata: { is_pinned: true } } as BackendSession),
    ).toBe(true);
  });
  it("returns false when metadata.is_pinned is false", () => {
    expect(
      isSessionPinned({ metadata: { is_pinned: false } } as BackendSession),
    ).toBe(false);
  });
  it("returns false when is_pinned is missing", () => {
    expect(isSessionPinned({ metadata: {} } as BackendSession)).toBe(false);
  });
  it("returns false when metadata is missing", () => {
    expect(isSessionPinned({} as BackendSession)).toBe(false);
  });
});
