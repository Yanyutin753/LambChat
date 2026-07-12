import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function readIfExists(path: string): string {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

const appSource = readFileSync(resolve(import.meta.dirname, "../App.tsx"), {
  encoding: "utf8",
});
const componentSource = readIfExists(
  resolve(import.meta.dirname, "../components/pwa/PwaStatusToasts.tsx"),
);

test("App mounts the PWA status toast bridge near the global toaster", () => {
  expect(appSource).toMatch(/PwaStatusToasts/);
  expect(appSource).toMatch(/<Toaster/);
});

test("PWA status toast bridge handles update, offline, and restored-online events", () => {
  expect(componentSource).toMatch(/PWA_UPDATE_AVAILABLE_EVENT/);
  expect(componentSource).toMatch(/activateWaitingLambChatPwaUpdate/);
  expect(componentSource).toMatch(/addEventListener\("offline"/);
  expect(componentSource).toMatch(/addEventListener\("online"/);
  expect(componentSource).toMatch(/toast\.custom/);
});

test("PWA status toast bridge uses i18n for user-facing text", () => {
  expect(componentSource).toMatch(/useTranslation/);
  expect(componentSource).toMatch(/pwaStatus\.offlineTitle/);
  expect(componentSource).toMatch(/pwaStatus\.offlineBody/);
  expect(componentSource).toMatch(/pwaStatus\.updateReadyTitle/);
  expect(componentSource).toMatch(/pwaStatus\.updateReadyBody/);
  expect(componentSource).toMatch(/pwaStatus\.backOnline/);
  expect(componentSource).toMatch(/pwaStatus\.dismiss/);
  expect(componentSource).not.toMatch(/You are offline/);
  expect(componentSource).not.toMatch(/Chat, files, and sync will resume/);
  expect(componentSource).not.toMatch(/Update ready/);
  expect(componentSource).not.toMatch(/A fresh LambChat version is ready/);
  expect(componentSource).not.toMatch(/Back online/);
  expect(componentSource).not.toMatch(/aria-label="Dismiss"/);
});
