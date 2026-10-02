import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("public conversation titles and identity metadata wrap inside their reading column", () => {
  const title = source.match(
    /<h1 className="([^"]+)">\s*\{sessionTitle\}/,
  )?.[1];
  expect(title).toContain("px-4");
  expect(title).toContain("[overflow-wrap:anywhere]");
  expect(source).toMatch(
    /data-share-author[\s\S]*?min-w-0[\s\S]*?\[overflow-wrap:anywhere\]/,
  );
  expect(source).toMatch(
    /const metadataClassName\s*=\s*"[^"]*max-w-full[^"]*\[overflow-wrap:anywhere\]/,
  );
});

test("secondary share information uses readable theme tokens without repeated decorative pills", () => {
  const meta = source.split("{/* Meta")[1]?.split("{/* Status badge */}")[0];
  expect(meta).toBeTruthy();
  expect(meta).not.toMatch(
    /className="inline-flex[^"]*(rounded-full|bg-stone)/,
  );
  expect(source).toMatch(
    /data-share-footer-meta[\s\S]*?text-theme-text-secondary/,
  );
});
