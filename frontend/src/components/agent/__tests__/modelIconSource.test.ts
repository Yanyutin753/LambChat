import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../modelIcon.ts", import.meta.url),
  "utf8",
);
const componentSource = readFileSync(
  new URL("../modelIcon.tsx", import.meta.url),
  "utf8",
);

test("model icon resolver accepts an explicit icon before provider fallback", () => {
  expect(source).toMatch(/explicitIcon\?:\s*string/);
  expect(source).toMatch(
    /if\s*\(\s*explicitIcon\s*&&\s*providerMap\[explicitIcon\]\s*\)/,
  );
  expect(componentSource).toMatch(/icon\?:\s*string/);
  expect(componentSource).toMatch(
    /getModelIconUrl\(model,\s*provider,\s*icon\)/,
  );
});
