import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  PWA_SKIP_WAITING_MESSAGE,
  isPwaSkipWaitingMessage,
  isPwaUpdateReady,
  shouldRegisterPwa,
} from "../pwaGuards.ts";

test("registers the PWA only for production browsers with service worker support", () => {
  expect(
    shouldRegisterPwa({ isProduction: true, hasServiceWorker: true }),
  ).toBe(true);
  expect(
    shouldRegisterPwa({ isProduction: false, hasServiceWorker: true }),
  ).toBe(false);
  expect(
    shouldRegisterPwa({ isProduction: true, hasServiceWorker: false }),
  ).toBe(false);
});

test("reports an installed worker as an update only when a controller exists", () => {
  expect(
    isPwaUpdateReady({ hasController: true, workerState: "installed" }),
  ).toBe(true);
  expect(
    isPwaUpdateReady({ hasController: false, workerState: "installed" }),
  ).toBe(false);
  expect(
    isPwaUpdateReady({ hasController: true, workerState: "installing" }),
  ).toBe(false);
});

test("recognizes the skip waiting message without accepting arbitrary payloads", () => {
  expect(isPwaSkipWaitingMessage(PWA_SKIP_WAITING_MESSAGE)).toBe(true);
  expect(isPwaSkipWaitingMessage({ type: PWA_SKIP_WAITING_MESSAGE })).toBe(
    true,
  );
  expect(isPwaSkipWaitingMessage({ type: "OTHER_MESSAGE" })).toBe(false);
  expect(isPwaSkipWaitingMessage(null)).toBe(false);
});

function readManifest() {
  return JSON.parse(
    readFileSync(resolve(import.meta.dirname, "../../public/manifest.json"), {
      encoding: "utf8",
    }),
  );
}

test("manifest launch colors match the light app shell background", () => {
  const manifest = readManifest() as {
    background_color?: string;
    theme_color?: string;
  };

  expect(manifest.background_color).toBe("#f5f5f4");
  expect(manifest.theme_color).toBe("#f5f5f4");
});

test("manifest exposes install metadata for desktop, tablet, and phone PWAs", () => {
  const manifest = JSON.parse(
    readFileSync(resolve(import.meta.dirname, "../../public/manifest.json"), {
      encoding: "utf8",
    }),
  ) as {
    id?: string;
    scope?: string;
    display?: string;
    display_override?: string[];
    screenshots?: Array<{ form_factor?: string; sizes?: string }>;
    icons?: Array<{ sizes?: string; purpose?: string }>;
  };

  expect(manifest.id).toBe("/");
  expect(manifest.scope).toBe("/");
  expect(manifest.display).toBe("standalone");
  expect(manifest.display_override).toEqual([
    "window-controls-overlay",
    "standalone",
    "minimal-ui",
    "browser",
  ]);
  expect(
    manifest.icons?.some(
      (icon) => icon.sizes === "512x512" && icon.purpose === "maskable",
    ),
  ).toBeTruthy();
  expect(
    manifest.screenshots?.some(
      (screenshot) => screenshot.form_factor === "wide",
    ),
  ).toBeTruthy();
  expect(
    manifest.screenshots?.some(
      (screenshot) => screenshot.form_factor === "narrow",
    ),
  ).toBeTruthy();
});
