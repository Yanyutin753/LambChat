/**
 * migrate-node-tests-to-vitest.ts
 *
 * Migrates all frontend test files from Node.js built-in `node:test` + `node:assert/strict`
 * to Vitest globals (test, describe, expect, vi).
 *
 * Usage:
 *   pnpm migrate-vitest           # migrate all files
 *   pnpm migrate-vitest --dry-run # preview changes without writing
 */

import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SRC_DIR = join(process.cwd(), "src");
const DRY_RUN = process.argv.includes("--dry-run");

// ── helpers ──────────────────────────────────────────────────────────

function findMatchingParen(src: string, openIdx: number): number {
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    const ch = src[i];

    // Skip single-char string literals
    if (ch === '"' || ch === "'") {
      const q = ch;
      i++;
      while (i < src.length) {
        if (src[i] === "\\") {
          i += 2;
          continue;
        }
        if (src[i] === q) break;
        i++;
      }
      continue;
    }

    // Skip template literals
    if (ch === "`") {
      i++;
      while (i < src.length) {
        if (src[i] === "\\") {
          i += 2;
          continue;
        }
        if (src[i] === "`") break;
        if (src[i] === "$" && i + 1 < src.length && src[i + 1] === "{") {
          i += 2;
          let exprDepth = 1;
          while (i < src.length && exprDepth > 0) {
            if (src[i] === "{") exprDepth++;
            else if (src[i] === "}") exprDepth--;
            if (src[i] === '"' || src[i] === "'") {
              const tq = src[i];
              i++;
              while (i < src.length && src[i] !== tq) {
                if (src[i] === "\\") i++;
                i++;
              }
            }
            i++;
          }
          i--;
        }
        i++;
      }
      continue;
    }

    // Skip regex literals — heuristic: / preceded by operator/comma/paren/line-start
    if (ch === "/") {
      const prev = src.slice(0, i).trimEnd();
      const last = prev[prev.length - 1];
      if (i === 0 || /[(,=[!&|?{};\n:>~^%+*/-]$/.test(last ?? "\n")) {
        i++;
        while (i < src.length && src[i] !== "/") {
          if (src[i] === "\\") {
            i += 2;
            continue;
          }
          if (src[i] === "[") {
            i++;
            while (i < src.length && src[i] !== "]") {
              if (src[i] === "\\") i++;
              i++;
            }
          }
          i++;
        }
        // skip flags
        while (i + 1 < src.length && /[gimsuyv]/.test(src[i + 1])) i++;
        continue;
      }
    }

    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * Split arguments at depth-0 commas, respecting strings, template literals,
 * regex literals, and nested brackets/parens.
 */
function splitArgs(src: string, start: number, end: number): string[] {
  const args: string[] = [];
  let current = "";
  let depth = 0;
  for (let i = start; i < end; i++) {
    const ch = src[i];

    // Skip string literals
    if (ch === '"' || ch === "'") {
      const q = ch;
      current += ch;
      i++;
      while (i < end) {
        current += src[i];
        if (src[i] === "\\") {
          i++;
          if (i < end) current += src[i];
          i++;
          continue;
        }
        if (src[i] === q) break;
        i++;
      }
      continue;
    }

    // Skip template literals
    if (ch === "`") {
      current += ch;
      i++;
      while (i < end) {
        current += src[i];
        if (src[i] === "\\") {
          i++;
          if (i < end) current += src[i];
          i++;
          continue;
        }
        if (src[i] === "`") break;
        i++;
      }
      continue;
    }

    // Skip regex literals
    if (ch === "/") {
      const prev = current.trimEnd();
      const last = prev[prev.length - 1];
      if (
        current.length === 0 ||
        prev === "" ||
        /[(,=[!&|?{};\n:>~^%+*/-]$/.test(last ?? "\n")
      ) {
        // Entire regex is part of this argument
        current += ch;
        i++;
        while (i < end && src[i] !== "/") {
          current += src[i];
          if (src[i] === "\\") {
            i++;
            if (i < end) current += src[i];
            i++;
            continue;
          }
          if (src[i] === "[") {
            i++; // "[" already added by current += src[i] above
            while (i < end && src[i] !== "]") {
              current += src[i];
              if (src[i] === "\\") {
                i++;
                if (i < end) current += src[i];
                i++;
                continue;
              }
              i++;
            }
            // Add the closing ] to current
            if (i < end) {
              current += src[i];
              i++;
            }
            continue; // skip outer i++ since we already advanced past ]
          }
          i++;
        }
        if (i < end) current += src[i]; // closing /
        // skip flags
        while (i + 1 < end && /[gimsuyv]/.test(src[i + 1])) {
          i++;
          current += src[i];
        }
        continue;
      }
    }

    if (ch === "(" || ch === "[" || ch === "{") depth++;
    else if (ch === ")" || ch === "]" || ch === "}") depth--;

    if (ch === "," && depth === 0) {
      args.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  const last = current.trim();
  if (last) args.push(last);
  return args;
}

// ── file discovery ──────────────────────────────────────────────────

function findTestFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (entry === "node_modules" || entry === ".git" || entry === "dist")
        continue;
      results.push(...findTestFiles(full));
    } else if (/\.(?:test|spec)\.(?:ts|tsx|js|jsx)$/.test(entry)) {
      results.push(full);
    }
  }
  return results;
}

// ── single-file migration ───────────────────────────────────────────

interface MigrationResult {
  changed: boolean;
  warnings: string[];
}

function migrateFile(filePath: string): MigrationResult {
  let src = readFileSync(filePath, "utf8");
  const warnings: string[] = [];
  let changed = false;

  // 1. Remove node:test imports (default + named + mixed)
  const beforeTest = src;
  src = src.replace(/^import\s+.*?\s+from\s+"node:test";\s*\n?/gm, "");
  if (src !== beforeTest) changed = true;

  // 2. Remove node:assert imports (default + named + mixed)
  const beforeAssert = src;
  src = src.replace(
    /^import\s+.*?\s+from\s+"node:assert(?:\/strict)?";\s*\n?/gm,
    "",
  );
  if (src !== beforeAssert) changed = true;

  // 3. Transform assert.* calls → expect.*
  const CALL_RE =
    /assert\.(match|doesNotMatch|equal|deepEqual|strictEqual|deepStrictEqual|ok|notEqual|fail)\s*\(/g;
  const replacements: { from: number; to: number; text: string }[] = [];

  let m: RegExpExecArray | null;
  while ((m = CALL_RE.exec(src)) !== null) {
    const method = m[1];
    const openParen = m.index + m[0].length - 1;
    const closeParen = findMatchingParen(src, openParen);

    if (closeParen === -1) {
      warnings.push(
        `Unmatched paren for assert.${method} at offset ${m.index}`,
      );
      continue;
    }

    const args = splitArgs(src, openParen + 1, closeParen);
    let replacement: string;

    switch (method) {
      case "match":
      case "doesNotMatch": {
        if (args.length < 2) {
          warnings.push(
            `assert.${method} with ${args.length} args at offset ${m.index}`,
          );
          continue;
        }
        const not = method === "doesNotMatch" ? "not." : "";
        replacement = `expect(${args[0]}).${not}toMatch(${args[1]})`;
        break;
      }
      case "equal":
      case "strictEqual":
        if (args.length < 2) {
          warnings.push(
            `assert.${method} with ${args.length} args at offset ${m.index}`,
          );
          continue;
        }
        replacement = `expect(${args[0]}).toBe(${args[1]})`;
        break;
      case "deepEqual":
      case "deepStrictEqual":
        if (args.length < 2) {
          warnings.push(
            `assert.${method} with ${args.length} args at offset ${m.index}`,
          );
          continue;
        }
        replacement = `expect(${args[0]}).toEqual(${args[1]})`;
        break;
      case "ok":
        replacement = `expect(${args[0] || "undefined"}).toBeTruthy()`;
        break;
      case "notEqual":
        if (args.length < 2) {
          warnings.push(
            `assert.notEqual with ${args.length} args at offset ${m.index}`,
          );
          continue;
        }
        replacement = `expect(${args[0]}).not.toBe(${args[1]})`;
        break;
      case "fail":
        replacement =
          args.length > 0
            ? `throw new Error(${args[0]})`
            : `throw new Error("assert.fail()")`;
        break;
      default:
        warnings.push(`Unknown assert method: ${method}`);
        continue;
    }

    replacements.push({ from: m.index, to: closeParen + 1, text: replacement });
  }

  // Apply replacements in reverse to keep offsets valid
  for (let i = replacements.length - 1; i >= 0; i--) {
    const r = replacements[i];
    src = src.substring(0, r.from) + r.text + src.substring(r.to);
  }
  if (replacements.length > 0) changed = true;

  if (changed && !DRY_RUN) {
    writeFileSync(filePath, src);
  }

  return { changed, warnings };
}

// ── main ────────────────────────────────────────────────────────────

const files = findTestFiles(SRC_DIR);
let changedCount = 0;
let unchangedCount = 0;
const allWarnings: string[] = [];

console.log(
  DRY_RUN
    ? "🔍 DRY RUN — no files will be modified\n"
    : "🔄 Migrating node:test → Vitest\n",
);
console.log(
  `Found ${files.length} test files in ${relative(process.cwd(), SRC_DIR)}/\n`,
);

for (const file of files) {
  const rel = relative(process.cwd(), file);
  const result = migrateFile(file);
  if (result.changed) {
    changedCount++;
    console.log(`  ✅ ${rel}`);
  } else {
    unchangedCount++;
  }
  for (const w of result.warnings) allWarnings.push(`${rel}: ${w}`);
}

console.log(`\n${"─".repeat(60)}`);
console.log(`  Migrated:  ${changedCount}`);
console.log(`  Unchanged: ${unchangedCount}`);
console.log(`  Total:     ${files.length}`);
if (allWarnings.length > 0) {
  console.log(`\n⚠️  Warnings (${allWarnings.length}):`);
  for (const w of allWarnings) console.log(`    ${w}`);
}
console.log(
  DRY_RUN
    ? "\n🔒 DRY RUN complete — run without --dry-run to apply."
    : "\n✅ Migration complete.",
);
