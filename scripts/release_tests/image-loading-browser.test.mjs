import test from "node:test";
import assert from "node:assert/strict";
import { assertImageCase } from "./image-loading-browser.mjs";
const direct = () => ({
  blocked: false,
  publicLoaded: true,
  privateLoaded: true,
  privateBlob: true,
  directRequests: 1,
  storageRequests: 1,
  proxyUrls: [],
  privateRequests: [{ authorized: true }],
  privateStorageRequests: 0,
  credentialLeaks: 0,
  errors: [],
});
test("successful storage images use zero proxies and keep private images authenticated", () =>
  assert.doesNotThrow(() => assertImageCase(direct())));
test("blocked storage recovers with exactly one small-image proxy", () =>
  assert.doesNotThrow(() =>
    assertImageCase({
      ...direct(),
      blocked: true,
      proxyUrls: [
        "https://app.example/api/upload/file/a.png?thumb=1&proxy=true",
      ],
    }),
  ));
for (const [name, change, pattern] of [
  [
    "failed images cannot pass merely because no proxy was used",
    { publicLoaded: false },
    /public image/,
  ],
  [
    "normal loads cannot silently use a proxy",
    { proxyUrls: ["https://app.example/api/upload/file/a.png?proxy=true"] },
    /zero proxies/,
  ],
  [
    "the client must attempt a direct request before falling back",
    { directRequests: 0 },
    /direct request/,
  ],
  [
    "normal loads must actually reach storage",
    { storageRequests: 0 },
    /storage request/,
  ],
  [
    "old redirecting thumbnail proxies fail the regression",
    {
      blocked: true,
      proxyUrls: [
        "https://app.example/api/upload/file/a.png?thumb=1&proxy=true",
        "https://app.example/api/upload/file/a.png?proxy=true",
      ],
    },
    /exactly one/,
  ],
  [
    "proxying the original first fails the small-image requirement",
    {
      blocked: true,
      proxyUrls: ["https://app.example/api/upload/file/a.png?proxy=true"],
    },
    /small-image/,
  ],
  [
    "private images must render a blob",
    { privateBlob: false },
    /authenticated blob/,
  ],
  [
    "private requests must carry authentication",
    { privateRequests: [{ authorized: false }] },
    /private request/,
  ],
  [
    "private images must not redirect to storage",
    { privateStorageRequests: 1 },
    /private storage/,
  ],
  [
    "account credentials must not reach storage",
    { credentialLeaks: 1 },
    /credentials/,
  ],
  [
    "browser exceptions fail the case",
    { errors: ["fixture exception"] },
    /browser exception/,
  ],
])
  test(name, () =>
    assert.throws(() => assertImageCase({ ...direct(), ...change }), pattern),
  );
