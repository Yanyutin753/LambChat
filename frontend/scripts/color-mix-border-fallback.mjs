import postcss from "postcss";

function replaceThemeMix(value) {
  let result = "";
  let cursor = 0;
  let start;
  while ((start = value.indexOf("color-mix(", cursor)) !== -1) {
    let end = start + "color-mix".length;
    let depth = 0;
    do {
      if (value[end] === "(") depth++;
      else if (value[end] === ")") depth--;
      end++;
    } while (end < value.length && depth > 0);
    if (depth !== 0) return value;
    const color = value.slice(start, end);
    result +=
      value.slice(cursor, start) +
      (color.includes("var(--theme-border)") ? "var(--theme-border)" : color);
    cursor = end;
  }
  return result + value.slice(cursor);
}

// Tailwind may fall back to the first mixed color, which is near-white in dark mode.
export default function colorMixBorderFallback() {
  return {
    postcssPlugin: "lambchat-color-mix-border-fallback",
    OnceExit(root) {
      root.walkDecls(
        /^border(?:-(?:top|right|bottom|left|inline|block|start|end))*?(?:-color)?$/,
        (decl) => {
          if (
            !decl.value.includes("color-mix(") ||
            !decl.value.includes("var(--theme-border)")
          )
            return;
          const container = decl.parent;
          const nestedSupport =
            container.type === "atrule" &&
            container.name === "supports" &&
            container.params.includes("color-mix");
          if (nestedSupport && container.params.trim().startsWith("not"))
            return;
          const rule = nestedSupport ? container.parent : container;
          if (rule.type !== "rule") return;
          const siblings = container.nodes;
          const index = siblings.indexOf(decl);
          if (
            siblings.some(
              (node, i) =>
                node.type === "decl" && node.prop === decl.prop && i > index,
            )
          )
            return;
          const authoredFallback = siblings
            .slice(0, index)
            .reverse()
            .find(
              (node) =>
                node.type === "decl" &&
                node.prop === decl.prop &&
                !node.value.includes("color-mix("),
            );

          const fallback = postcss.atRule({
            name: "supports",
            params: "not (color: color-mix(in srgb, black, white))",
          });
          fallback.append(
            decl.clone({
              value: authoredFallback?.value ?? replaceThemeMix(decl.value),
            }),
          );
          (nestedSupport ? container : decl).after(fallback);
        },
      );
    },
  };
}

colorMixBorderFallback.postcss = true;
