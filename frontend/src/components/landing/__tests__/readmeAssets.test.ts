import { existsSync, readFileSync } from "node:fs";
import { expect, test } from "vitest";

const root = new URL("../../../../../", import.meta.url);

test.each(["README.md", "README_CN.md"])(
  "%s has complete light and dark image assets",
  (name) => {
    const source = readFileSync(new URL(name, root), "utf8");
    const images = [
      ...source.matchAll(
        /(?:src|srcset)="(docs\/images\/best-practice\/[^" ]+)"/g,
      ),
    ];
    expect(images.length).toBeGreaterThan(0);
    for (const [, path] of images) {
      expect(existsSync(new URL(path, root)), path).toBe(true);
      if (!path.endsWith("-dark.webp")) {
        expect(source).toContain(path.replace(".webp", "-dark.webp"));
      }
    }
  },
);
