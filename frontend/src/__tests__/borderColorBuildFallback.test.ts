import { fileURLToPath } from "node:url";
import postcss from "postcss";
import { transform } from "lightningcss";
import { expect, test } from "vitest";

async function buildCss(source: string) {
  const configUrl = new URL("../../postcss.config.js", import.meta.url);
  const config = (await import(configUrl.href)).default;
  const plugins = await Promise.all(
    Object.entries(config.plugins).map(async ([name, options]) => {
      const pluginUrl = name.startsWith(".")
        ? new URL(name, configUrl).href
        : name;
      const factory = (await import(pluginUrl)).default;
      return factory(options);
    }),
  );
  const result = await postcss(plugins).process(source, {
    from: fileURLToPath(new URL("./border-probe.css", import.meta.url)),
  });
  return postcss.parse(
    transform({
      filename: "border-probe.css",
      code: Buffer.from(result.css),
      minify: true,
      targets: { chrome: 111 << 16, safari: (16 << 16) | (4 << 8) },
    }).code.toString(),
  );
}

function unsupportedBorderValues(css: postcss.Root, selector?: string) {
  const values: string[] = [];
  css.walkRules((rule) => {
    if (selector && rule.selector !== selector) return;
    for (let parent = rule.parent; parent; parent = parent.parent) {
      if (
        parent.type === "atrule" &&
        parent.name === "supports" &&
        parent.params.includes("color-mix") &&
        !parent.params.trim().startsWith("not")
      )
        return;
    }
    rule.walkDecls("border-color", (decl) => {
      values.push(decl.value);
    });
  });
  return values;
}

for (const color of ["primary", "text", "text-secondary"]) {
  test(`packaged mixed borders fall back to the border token rather than ${color}`, async () => {
    const css = await buildCss(
      `.probe { border-color: color-mix(in srgb, var(--theme-${color}) 16%, var(--theme-border)); }`,
    );
    expect(unsupportedBorderValues(css).at(-1)).toBe("var(--theme-border)");
    expect(css.toString()).toContain("color-mix(");
  });
}

test("an explicit border fallback and intentional primary borders survive the pipeline", async () => {
  const css = await buildCss(`
    .explicit { border-color: #123456; border-color: color-mix(in srgb, var(--theme-primary) 16%, var(--theme-border)); }
    .intentional { border-color: var(--theme-primary); }
  `);
  expect(css.toString()).toContain("#123456");
  expect(unsupportedBorderValues(css, ".explicit").at(-1)).toBe("#123456");
  expect(css.toString()).toContain(
    ".intentional{border-color:var(--theme-primary)}",
  );
});

test("generated Tailwind arbitrary border colors receive the same fallback", async () => {
  const css = await buildCss(`
    @reference "../styles/tailwind.css";
    .probe { @apply border-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))]; }
  `);
  expect(unsupportedBorderValues(css).at(-1)).toBe("var(--theme-border)");
});

test("mixed border fallbacks preserve later side overrides and media scope", async () => {
  const css = await buildCss(`
    @media (min-width: 800px) {
      .probe { border-color: color-mix(in srgb, var(--theme-text) 12%, var(--theme-border)); border-left-color: #123456; }
    }
  `);
  let left = "";
  css.walkDecls(/^border(?:-left)?-color$/, (decl) => {
    for (let parent = decl.parent; parent; parent = parent.parent) {
      if (
        parent.type === "atrule" &&
        parent.name === "supports" &&
        parent.params.includes("color-mix") &&
        !parent.params.startsWith("not")
      )
        return;
    }
    left = decl.value;
  });
  expect(left).toBe("#123456");
  css.walkAtRules("supports", (rule) => {
    if (!rule.params.startsWith("not")) return;
    expect(rule.parent?.type).toBe("atrule");
    expect(rule.parent).toHaveProperty("name", "media");
  });
});

test("mixed border shorthands retain width and style in the unsupported-color branch", async () => {
  const css = await buildCss(`
    .all { border: 1px solid color-mix(in srgb, var(--theme-primary) 16%, var(--theme-border)); }
    .edge { border-left: 2px dashed color-mix(in srgb, var(--theme-text) 12%, var(--theme-border)); }
  `);
  const fallbacks: string[] = [];
  css.walkAtRules("supports", (rule) => {
    if (
      rule.params.trim().startsWith("not") &&
      rule.params.includes("color-mix")
    ) {
      rule.walkDecls(/^border(?:-left)?$/, (decl) => {
        fallbacks.push(decl.value);
      });
    }
  });
  expect(fallbacks).toContain("1px solid var(--theme-border)");
  expect(fallbacks).toContain("2px dashed var(--theme-border)");
});

test("shorthand fallbacks preserve later single-side overrides and surrounding media conditions", async () => {
  const css = await buildCss(`
    @media (min-width: 800px) {
      .probe { border: 1px solid color-mix(in srgb, var(--theme-primary) 16%, var(--theme-border)); border-left: 2px dashed #123456; }
    }
  `);
  const supported: string[] = [];
  css.walkAtRules("supports", (rule) => {
    if (!rule.params.trim().startsWith("not")) return;
    expect(rule.parent).toHaveProperty("name", "media");
    rule.walkDecls("border", (decl) => {
      supported.push(decl.value);
    });
  });
  expect(supported).toContain("1px solid var(--theme-border)");
  expect(css.toString()).toContain("border-left:2px dashed #123456");
});
