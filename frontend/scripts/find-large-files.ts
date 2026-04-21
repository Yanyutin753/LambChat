import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import { glob } from "glob";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "../..");
const FRONTEND_SRC = path.join(PROJECT_ROOT, "frontend/src");
const BACKEND_SRC = path.join(PROJECT_ROOT, "src");

const LINE_THRESHOLD = 1000;

async function findLargeFiles(
  pattern: string,
  cwd: string,
  label: string,
): Promise<{ file: string; lines: number }[]> {
  const files = await glob(pattern, { cwd, absolute: true });
  const results: { file: string; lines: number }[] = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf-8");
    const lines = content.split("\n").length;

    if (lines > LINE_THRESHOLD) {
      const rel = path.relative(PROJECT_ROOT, file);
      results.push({ file: rel, lines });
    }
  }

  results.sort((a, b) => b.lines - a.lines);

  console.log(`\n--- ${label} (>${LINE_THRESHOLD} lines) ---`);

  if (results.length === 0) {
    console.log("No files found.");
  } else {
    for (const { file, lines } of results) {
      console.log(`${lines.toString().padStart(5)} ${file}`);
    }
    console.log(`Subtotal: ${results.length} file(s)`);
  }

  return results;
}

async function main() {
  console.log(`Files with more than ${LINE_THRESHOLD} lines:`);
  console.log("========================================");

  const frontendResults = await findLargeFiles(
    "**/*.{ts,tsx,js,jsx}",
    FRONTEND_SRC,
    "Frontend",
  );

  const backendResults = await findLargeFiles(
    "**/*.py",
    BACKEND_SRC,
    "Backend",
  );

  const total = frontendResults.length + backendResults.length;
  console.log("\n========================================");
  console.log(`Total: ${total} file(s)`);
}

main().catch(console.error);
