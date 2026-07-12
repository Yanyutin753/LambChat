import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, "..", relativePath), "utf8");
}

test("chat app uses stable skill list params to avoid refetch loops", () => {
  const source = readSource("ChatAppContent.tsx");

  expect(source).toMatch(
    /const CHAT_SKILL_LIST_PARAMS\s*=\s*\{\s*limit:\s*100\s*\}/,
  );
  expect(source).not.toMatch(
    /useSkills\(\{\s*enabled:\s*enableSkills,\s*listParams:\s*\{\s*limit:\s*100\s*\}/,
  );
});
