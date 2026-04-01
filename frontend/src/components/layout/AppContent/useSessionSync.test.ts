import test from "node:test";
import assert from "node:assert/strict";
import { shouldResetExternalNavigateFlag } from "./useSessionSync.ts";


test("resets the external navigation flag only when present", () => {
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: true }),
    true,
  );
  assert.equal(
    shouldResetExternalNavigateFlag({ externalNavigate: false }),
    false,
  );
  assert.equal(shouldResetExternalNavigateFlag({}), false);
  assert.equal(shouldResetExternalNavigateFlag(null), false);
});
