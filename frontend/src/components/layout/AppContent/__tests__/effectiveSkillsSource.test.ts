import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, "..", relativePath), "utf8");
}

test("chat skill selector receives session-effective skills and counts", () => {
  const source = readSource("ChatAppContent.tsx");

  expect(source).toMatch(/const effectiveSkills = useMemo\(/);
  expect(source).toMatch(/countEnabledSkills\(effectiveSkills\)/);
  expect(source).toMatch(/skills=\{effectiveSkills\}/);
  expect(source).toMatch(/enabledSkillsCount=\{effectiveEnabledSkillsCount\}/);
  expect(source).toMatch(/totalSkillsCount=\{effectiveSkills\.length\}/);
  expect(source).not.toMatch(/enabledSkillsCount=\{totalEnabledSkillCount\}/);
});
