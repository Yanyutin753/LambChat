import {
  rewriteProjectFileContent,
  rewriteProjectTextFiles,
} from "../projectRevealAssetUtils.ts";

test("rewrites relative css asset urls against the source file path", () => {
  const content = '.hero { background-image: url("../assets/icon.png"); }';

  const rewritten = rewriteProjectFileContent("/src/styles/app.css", content, {
    "/src/assets/icon.png": "https://cdn.example.com/icon.png",
  });

  expect(rewritten).toMatch(/https:\/\/cdn\.example\.com\/icon\.png/);
});

test("rewrites default static asset imports to string urls", () => {
  const content = 'import logo from "../assets/logo.png";\nconsole.log(logo);';

  const rewritten = rewriteProjectFileContent("/src/App.tsx", content, {
    "/assets/logo.png": "https://cdn.example.com/logo.png",
  });

  expect(rewritten).toMatch(
    /const logo = "https:\/\/cdn\.example\.com\/logo\.png";/,
  );
});

test("rewrites new URL asset lookups while preserving usage shape", () => {
  const content =
    'const iconHref = new URL("./assets/icon.png", import.meta.url).href;';

  const rewritten = rewriteProjectFileContent("/src/main.ts", content, {
    "/src/assets/icon.png": "https://cdn.example.com/icon.png",
  });

  expect(rewritten).toBe(
    'const iconHref = "https://cdn.example.com/icon.png";',
  );
});

test("rewrites project text files without touching unresolved imports", () => {
  const files = {
    "/src/App.tsx":
      'import logo from "../assets/logo.png";\nimport "./styles.css";\nexport { logo };',
    "/src/styles.css": '.hero { background-image: url("./bg.png"); }',
  };

  const rewritten = rewriteProjectTextFiles(files, {
    "/assets/logo.png": "https://cdn.example.com/logo.png",
  });

  expect(rewritten["/src/App.tsx"]).toMatch(
    /const logo = "https:\/\/cdn\.example\.com\/logo\.png";/,
  );
  expect(rewritten["/src/App.tsx"]).toMatch(/import "\.\/styles\.css";/);
  expect(rewritten["/src/styles.css"]).toMatch(/url\("\.\/bg\.png"\)/);
});
