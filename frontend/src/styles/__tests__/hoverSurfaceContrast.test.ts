import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

test.each([":root", ".dark", ".theme-sepia"])(
  "%s hover differs from page and card surfaces",
  (selector) => {
    const block = css.slice(css.indexOf(`${selector} {`)).split("}")[0];
    const rgb = (name: string) =>
      block
        .match(new RegExp(`--theme-${name}: #([a-fA-F0-9]{6});`))![1]
        .match(/../g)!
        .map((value) => parseInt(value, 16));
    const text = rgb("text");
    const card = rgb("bg-card");
    const hover = card.map((value, index) =>
      Math.round(value * 0.91 + text[index] * 0.09),
    );
    for (const surface of [card, rgb("bg")]) {
      expect(
        Math.max(
          ...hover.map((value, index) => Math.abs(value - surface[index])),
        ),
      ).toBeGreaterThan(4);
    }
    expect(css.replace(/\s+/g, "")).toContain(
      "--theme-bg-hover:color-mix(insrgb,var(--theme-text)9%,var(--theme-bg-card));",
    );
  },
);
