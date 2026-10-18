import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const panel = readFileSync(
  new URL(
    "../../components/panels/AgentModelPanel/AgentModelPanel.tsx",
    import.meta.url,
  ),
  "utf8",
);
const models = readFileSync(
  new URL(
    "../../components/panels/ModelPanel/tabs/ModelConfigTab.tsx",
    import.meta.url,
  ),
  "utf8",
);
const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

test("unselected agent/model tabs retain readable actionable labels", () => {
  const inactive = panel.match(/isActive\s*\?\s*"[^"]*"\s*:\s*"([^"]*)"/)?.[1];
  expect(inactive).toBeDefined();
  expect(inactive?.split(/\s+/)).toContain("text-theme-text-secondary");
  expect(inactive).not.toContain("text-theme-text-tertiary");
});

test("both model edit controls retain visible actionable icons", () => {
  const editClasses = [
    ...models.matchAll(/onClick=\{handleEdit\}\s+className="([^"]*)"/g),
  ].map((match) => match[1]);
  expect(editClasses).toHaveLength(2);
  for (const classes of editClasses) {
    expect(classes.split(/\s+/)).toContain("text-theme-text-secondary");
    expect(classes).not.toContain("text-theme-text-tertiary");
  }
});

test.each([":root", ".dark", ".theme-sepia"])(
  "%s actionable secondary text meets AA contrast on shared surfaces",
  (selector) => {
    const block = tokens.slice(tokens.indexOf(`${selector} {`)).split("}")[0];
    const luminance = (name: string) => {
      const hex = block.match(new RegExp(`--theme-${name}: (#\\w{6});`))![1];
      const rgb = hex.match(/[a-f\d]{2}/gi)!.map((channel) => {
        const value = parseInt(channel, 16) / 255;
        return value <= 0.04045
          ? value / 12.92
          : ((value + 0.055) / 1.055) ** 2.4;
      });
      return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
    };
    for (const surface of ["bg", "bg-card", "bg-elevated"]) {
      const foreground = luminance("text-secondary");
      const background = luminance(surface);
      expect(
        (Math.max(foreground, background) + 0.05) /
          (Math.min(foreground, background) + 0.05),
        `${selector} secondary text on ${surface}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  },
);
