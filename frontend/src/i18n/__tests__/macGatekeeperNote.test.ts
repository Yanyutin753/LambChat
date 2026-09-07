import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(currentDir, "../locales");
const locales = ["en", "zh", "ja", "ko", "ru"];

test("all locales describe the macOS Gatekeeper first-launch note", () => {
  for (const locale of locales) {
    const messages = JSON.parse(
      readFileSync(resolve(localesDir, `${locale}.json`), "utf8"),
    ) as { download: { macGatekeeper: Record<string, string> } };

    expect(messages.download.macGatekeeper.title).toBeTruthy();
    expect(messages.download.macGatekeeper.body).toBeTruthy();
  }
});
