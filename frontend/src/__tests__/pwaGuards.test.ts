import test from "node:test";
import assert from "node:assert/strict";
import { shouldRegisterPwa } from "../pwaGuards.ts";

test("registers the PWA only for production browsers with service worker support", () => {
  assert.equal(
    shouldRegisterPwa({ isProduction: true, hasServiceWorker: true }),
    true,
  );
  assert.equal(
    shouldRegisterPwa({ isProduction: false, hasServiceWorker: true }),
    false,
  );
  assert.equal(
    shouldRegisterPwa({ isProduction: true, hasServiceWorker: false }),
    false,
  );
});
