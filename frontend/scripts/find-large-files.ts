import fs from "fs";
import { glob } from "glob";

const LINE_THRESHOLD = 1000;

const BACKEND_SRC = "src";

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
      const rel = file.includes("/frontend/")
        ? file.split("/frontend/")[1]
        : file.includes("/LambChat/")
          ? file.split("/LambChat/")[1]
          : file;
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
    "src/**/*.{ts,tsx,js,jsx}",
    process.cwd(),
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
