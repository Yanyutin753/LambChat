import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const sitemap = readFileSync(
  resolve(import.meta.dirname, "../../public/sitemap.xml"),
  "utf8",
);

test("sitemap exposes public landing section routes for search sitelinks", () => {
  for (const path of [
    "/",
    "/features",
    "/architecture",
    "/dashboard",
    "/responsive",
    "/github",
  ]) {
    const url =
      path === "/" ? "https://lambchat.com/" : `https://lambchat.com${path}`;
    expect(sitemap).toMatch(new RegExp(`<loc>${url}</loc>`));
  }
});

test("sitemap prioritizes sitelink candidates over secondary interface routes", () => {
  expect(sitemap).not.toMatch(/<loc>https:\/\/lambchat\.com\/interface<\/loc>/);
  expect(sitemap).toMatch(
    /<loc>https:\/\/lambchat\.com\/features<\/loc>[\s\S]*<priority>0\.9<\/priority>/,
  );
});
