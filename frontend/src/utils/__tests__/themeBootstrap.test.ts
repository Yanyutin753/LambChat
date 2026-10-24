import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { applyThemeToDocument, type Theme } from "../themeDom";

const html = readFileSync(
  new URL("../../../index.html", import.meta.url),
  "utf8",
);
const bootstrap = html.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
const tokens = readFileSync(
  new URL("../../styles/tokens.css", import.meta.url),
  "utf8",
);

for (const [theme, color] of Object.entries({
  light: "#f5f5f4",
  dark: "#171819",
  sepia: "#f3edde",
})) {
  test(`boot and runtime keep ${theme} page and browser backgrounds aligned`, () => {
    const values = new Map<string, string>();
    const style = () => ({
      setProperty(name: string, value: string) {
        values.set(name, value);
      },
      backgroundColor: "",
      colorScheme: "",
    });
    const metas = [0, 1, 2].map((index) => ({
      setAttribute(_name: string, value: string) {
        values.set(`meta${index}`, value);
      },
    }));
    const statusBar = {
      setAttribute(_name: string, value: string) {
        values.set("status", value);
      },
    };
    const document = {
      documentElement: {
        classList: { toggle() {}, add() {}, remove() {} },
        style: style(),
      },
      body: { style: style() },
      querySelectorAll: () => metas,
      querySelector: () => statusBar,
      getElementById: () => statusBar,
    };
    expect(bootstrap).toBeTruthy();
    runInNewContext(bootstrap!, {
      document,
      localStorage: {
        getItem: (key: string) => (key === "lambchat-theme" ? theme : null),
      },
      window: { matchMedia: () => ({ matches: theme !== "dark" }) },
    });
    expect(tokens).toContain(`--theme-bg: ${color};`);
    expect(document.documentElement.style.backgroundColor).toBe(color);
    expect(document.body.style.backgroundColor).toBe(color);
    expect(values.get("meta0")).toBe(color);
    expect(values.get("status")).toBe("default");
    // A restored preference must also replace a different boot-time theme.
    applyThemeToDocument(theme === "light" ? "dark" : "light", document);
    applyThemeToDocument(theme as Theme, document);
    expect(values.get("background-color")).toBe(color);
    expect(values.get("meta0")).toBe(color);
    expect(values.get("status")).toBe("default");
  });
}
