import {
  applyThemeToDocument,
  getInitialThemePreference,
} from "../themeDom.ts";

test("getInitialThemePreference prefers persisted theme over system preference", () => {
  const env = {
    localStorage: {
      getItem: (key: string) => (key === "lamb-agent-theme" ? "light" : null),
    },
    matchMedia: () => ({ matches: true }),
  };

  expect(getInitialThemePreference(env)).toBe("light");
});

test("getInitialThemePreference falls back to dark system preference", () => {
  const env = {
    localStorage: {
      getItem: () => null,
    },
    matchMedia: () => ({ matches: true }),
  };

  expect(getInitialThemePreference(env)).toBe("dark");
});

test("applyThemeToDocument synchronously toggles dark class and browser chrome", () => {
  const classes = new Set<string>(["dark"]);
  const metaValues = new Map<string, string>();
  const themeColorElements = [
    {
      setAttribute: (_name: string, value: string) => {
        metaValues.set('meta[name="theme-color"]:default', value);
      },
    },
  ];
  const documentLike = {
    documentElement: {
      classList: {
        add: (name: string) => classes.add(name),
        remove: (name: string) => classes.delete(name),
      },
    },
    querySelector: (selector: string) =>
      selector === 'meta[name="theme-color"]' ||
      selector === 'meta[name="apple-mobile-web-app-status-bar-style"]'
        ? {
            setAttribute: (_name: string, value: string) => {
              metaValues.set(selector, value);
            },
          }
        : null,
    querySelectorAll: (selector: string) =>
      selector === 'meta[name="theme-color"]' ? themeColorElements : [],
  };

  applyThemeToDocument("light", documentLike);

  expect(classes.has("dark")).toBe(false);
  expect(metaValues.get('meta[name="theme-color"]:default')).toBe("#f5f5f4");
  expect(
    metaValues.get('meta[name="apple-mobile-web-app-status-bar-style"]'),
  ).toBe("default");
});

test("applyThemeToDocument updates every theme-color meta tag", () => {
  const metaValues: string[] = [];
  const documentLike = {
    documentElement: {
      classList: {
        add: () => {},
        remove: () => {},
      },
    },
    querySelector: (selector: string) =>
      selector === 'meta[name="apple-mobile-web-app-status-bar-style"]'
        ? {
            setAttribute: () => {},
          }
        : null,
    querySelectorAll: (selector: string) =>
      selector === 'meta[name="theme-color"]'
        ? [0, 1, 2].map((index) => ({
            setAttribute: (_name: string, value: string) => {
              metaValues[index] = value;
            },
          }))
        : [],
  };

  applyThemeToDocument("dark", documentLike);

  expect(metaValues).toEqual(["#151210", "#151210", "#151210"]);
});

test("applyThemeToDocument keeps the page background in sync for system bars", () => {
  const rootStyle = new Map<string, string>();
  const bodyStyle = new Map<string, string>();
  const documentLike = {
    documentElement: {
      classList: {
        add: () => {},
        remove: () => {},
      },
      style: {
        setProperty: (name: string, value: string) => {
          rootStyle.set(name, value);
        },
      },
    },
    body: {
      style: {
        setProperty: (name: string, value: string) => {
          bodyStyle.set(name, value);
        },
      },
    },
    querySelector: () => null,
    querySelectorAll: () => [],
  };

  applyThemeToDocument("dark", documentLike);

  expect(rootStyle.get("background-color")).toBe("#151210");
  expect(rootStyle.get("color-scheme")).toBe("dark");
  expect(bodyStyle.get("background-color")).toBe("#151210");
  expect(bodyStyle.get("color-scheme")).toBe("dark");
});
