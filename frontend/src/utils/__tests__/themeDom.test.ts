import {
  applyThemeToDocument,
  getInitialThemePreference,
  isTheme,
  readThemeMode,
  resolveNextTheme,
  themeExportBackground,
} from "../themeDom.ts";

test("getInitialThemePreference prefers persisted theme over system preference", () => {
  const env = {
    localStorage: {
      getItem: (key: string) => (key === "lambchat-theme" ? "light" : null),
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

test("isTheme accepts the sepia eye-care theme", () => {
  expect(isTheme("sepia")).toBe(true);
  expect(isTheme("beige")).toBe(false);
});

test("getInitialThemePreference restores persisted sepia theme", () => {
  const env = {
    localStorage: {
      getItem: (key: string) => (key === "lambchat-theme" ? "sepia" : null),
    },
    matchMedia: () => ({ matches: true }),
  };

  expect(getInitialThemePreference(env)).toBe("sepia");
});

test("readThemeMode maps html classes to the three theme modes", () => {
  const modeOf = (classNames: string[]) =>
    readThemeMode({
      documentElement: { classList: { contains: (name: string) => classNames.includes(name) } },
    });

  expect(modeOf([])).toBe("light");
  expect(modeOf(["dark"])).toBe("dark");
  expect(modeOf(["theme-sepia"])).toBe("sepia");
});

test("readThemeMode treats dark as the winner when both theme classes linger", () => {
  expect(
    readThemeMode({
      documentElement: {
        classList: { contains: (name: string) => name === "dark" || name === "theme-sepia" },
      },
    }),
  ).toBe("dark");
});

test("resolveNextTheme cycles light → dark → sepia → light", () => {
  expect(resolveNextTheme("light")).toBe("dark");
  expect(resolveNextTheme("dark")).toBe("sepia");
  expect(resolveNextTheme("sepia")).toBe("light");
});

test("themeExportBackground maps each theme to its canvas export color", () => {
  expect(themeExportBackground("light")).toBe("#ffffff");
  expect(themeExportBackground("dark")).toBe("#1c1917");
  expect(themeExportBackground("sepia")).toBe("#faf6ea");
});


test("applyThemeToDocument applies theme-sepia class without dark for sepia theme", () => {
  const classes = new Set<string>(["dark"]);
  const metaValues: string[] = [];
  const documentLike = {
    documentElement: {
      classList: {
        add: (name: string) => classes.add(name),
        remove: (name: string) => classes.delete(name),
      },
    },
    querySelector: () => null,
    querySelectorAll: (selector: string) =>
      selector === 'meta[name="theme-color"]'
        ? [0, 1, 2].map((index) => ({
            setAttribute: (_name: string, value: string) => {
              metaValues[index] = value;
            },
          }))
        : [],
  };

  applyThemeToDocument("sepia", documentLike);

  expect(classes.has("theme-sepia")).toBe(true);
  expect(classes.has("dark")).toBe(false);
  expect(metaValues).toEqual(["#f3edde", "#f3edde", "#f3edde"]);
});

test("applyThemeToDocument removes theme-sepia when returning to light", () => {
  const classes = new Set<string>(["theme-sepia"]);
  const rootStyle = new Map<string, string>();
  const documentLike = {
    documentElement: {
      classList: {
        add: (name: string) => classes.add(name),
        remove: (name: string) => classes.delete(name),
      },
      style: {
        setProperty: (name: string, value: string) => {
          rootStyle.set(name, value);
        },
      },
    },
    querySelector: () => null,
    querySelectorAll: () => [],
  };

  applyThemeToDocument("light", documentLike);

  expect(classes.has("theme-sepia")).toBe(false);
  expect(classes.has("dark")).toBe(false);
  expect(rootStyle.get("color-scheme")).toBe("light");
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
