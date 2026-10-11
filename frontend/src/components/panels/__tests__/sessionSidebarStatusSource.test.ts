import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  new URL("../SessionSidebar.tsx", import.meta.url),
  "utf8",
);
const updater = source.slice(
  source.indexOf("const updateSessionMetadata = useCallback("),
  source.indexOf("useImperativeHandle("),
);

describe("sidebar task status fan-out", () => {
  it("updates scheduled task lists as well as chat, pinned and project lists", () => {
    expect(updater).toContain("scheduledTaskRefs.current");
    expect(updater).toContain("uncategorizedList");
    expect(updater).toContain("pinnedList");
    expect(updater).toContain("projectRefs.current");
  });

  it("does not stop after updating the first copy of a session", () => {
    expect(updater).not.toMatch(/return;/);
  });
});
