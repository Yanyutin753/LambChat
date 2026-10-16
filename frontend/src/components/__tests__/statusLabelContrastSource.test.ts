import { readFileSync } from "node:fs";
import { join } from "node:path";

const tokens = readFileSync(
  join(import.meta.dirname, "../../styles/tokens.css"),
  "utf8",
);
const source = (file: string) =>
  readFileSync(join(import.meta.dirname, "..", file), "utf8");
type Color = number[];

function mix(a: Color, b: Color, weight: number): Color {
  return a.map((channel, index) => channel * weight + b[index] * (1 - weight));
}

function contrast(a: Color, b: Color): number {
  const luminance = (color: Color) =>
    color.reduce((sum, channel, index) => {
      const linear =
        channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4;
      return sum + linear * [0.2126, 0.7152, 0.0722][index];
    }, 0);
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

const labels = [
  {
    file: "common/CollapsiblePill.tsx",
    pattern: /success:\s*"(text-[^"]+)"/,
    status: "success",
    tint: 0,
  },
  {
    file: "common/CollapsiblePill.tsx",
    pattern: /error:\s*"(text-[^"]+)"/,
    status: "error",
    tint: 0,
  },
  {
    file: "pages/ChannelsPage.tsx",
    pattern: /"(bg-\[color-mix\(in_srgb,var\(--theme-success\)[^"]+)"/g,
    status: "success",
    tint: 0.14,
  },
  {
    file: "panels/ChannelPanel.tsx",
    pattern: /className="(min-w-0 \[overflow-wrap:anywhere\] text-14 [^"]+)"/,
    status: "error",
    tint: 0,
    background: "fef2f2",
  },
  {
    file: "panels/ConfigPanelErrorCallout.tsx",
    pattern: /className=\{`([^`]+)`\}/,
    status: "error",
    tint: 0,
  },
  {
    file: "panels/RolesPanel.tsx",
    pattern: /className="(panel-notice [^"]+)"/,
    status: "error",
    tint: 0.08,
  },
  {
    file: "panels/UsersPanel.tsx",
    pattern: /className="(panel-notice [^"]+)"/,
    status: "error",
    tint: 0.08,
  },
];

test.each(["light", "sepia"])(
  "status labels keep readable contrast in %s",
  (theme) => {
    const block =
      theme === "light"
        ? tokens.match(/:root\s*\{([\s\S]*?)\n\}/)![1]
        : tokens.slice(tokens.indexOf("/* ── Semantic Colors (降饱和"));
    const hex = (value: string): Color =>
      value.match(/../g)!.map((channel) => parseInt(channel, 16) / 255);
    const token = (name: string): Color =>
      hex(block.match(new RegExp(`--theme-${name}:\\s*#([a-fA-F0-9]{6})`))![1]);

    for (const label of labels) {
      const matches = [
        ...source(label.file).matchAll(new RegExp(label.pattern.source, "g")),
      ];
      expect(
        matches.length,
        `find status labels in ${label.file}`,
      ).toBeGreaterThan(0);
      for (const match of matches) {
        const classes = match[1].split(/\s+/);
        const foregroundClass = classes.find((value) =>
          /^text-(?:theme-(?:success|error|text-secondary)|\[color-mix)/.test(
            value,
          ),
        );
        expect(
          foregroundClass,
          `find status foreground in ${label.file}`,
        ).toBeDefined();
        let foreground: Color;
        if (foregroundClass!.startsWith("text-theme-")) {
          foreground = token(foregroundClass!.slice("text-theme-".length));
        } else {
          const mixture = foregroundClass!.match(
            /var\(--theme-(success|error)\)_(\d+)%?,var\(--theme-text\)/,
          );
          expect(
            mixture,
            `resolve foreground ${foregroundClass}`,
          ).not.toBeNull();
          foreground = mix(
            token(mixture![1]),
            token("text"),
            Number(mixture![2]) / 100,
          );
        }
        const surface = label.background
          ? hex(label.background)
          : token("bg-card");
        const background = mix(token(label.status), surface, label.tint);
        expect(
          contrast(foreground, background),
          `${theme}: ${label.file}: ${foregroundClass}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  },
);
