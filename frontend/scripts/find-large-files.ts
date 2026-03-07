import fs from "fs";
import { glob } from "glob";

const LINE_THRESHOLD = 1000;

async function findLargeFiles() {
  console.log(`Files in src with more than ${LINE_THRESHOLD} lines:`);
  console.log("========================================");

  const files = await glob("src/**/*.{ts,tsx,js,jsx}", { cwd: process.cwd() });
  const results: { file: string; lines: number }[] = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf-8");
    const lines = content.split("\n").length;

    if (lines > LINE_THRESHOLD) {
      results.push({ file, lines });
    }
  }

  results.sort((a, b) => b.lines - a.lines);

  if (results.length === 0) {
    console.log("No files found.");
  } else {
    for (const { file, lines } of results) {
      console.log(`${lines.toString().padStart(5)} ${file}`);
    }
  }

  console.log("");
  console.log(`Total: ${results.length} file(s)`);
}

findLargeFiles().catch(console.error);
