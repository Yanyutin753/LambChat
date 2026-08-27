import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const sitemap = readFileSync(
  resolve(import.meta.dirname, "../../public/sitemap.xml"),
  "utf8",
);

test("sitemap exposes real public routes for search indexing", () => {
  for (const url of [
    "https://lambchat.com/",
    "https://lambchat.com/features",
    "https://lambchat.com/docs/en/",
    "https://lambchat.com/docs/zh/",
  ]) {
    expect(sitemap).toMatch(new RegExp(`<loc>${url}</loc>`));
  }
});

test("sitemap omits routes that do not exist in the SPA router", () => {
  for (const path of ["/architecture", "/dashboard", "/responsive"]) {
    expect(sitemap).not.toMatch(
      new RegExp(`<loc>https://lambchat\\.com${path}</loc>`),
    );
  }
});

test("sitemap prioritizes sitelink candidates over secondary interface routes", () => {
  expect(sitemap).not.toMatch(/<loc>https:\/\/lambchat\.com\/interface<\/loc>/);
  expect(sitemap).toMatch(
    /<loc>https:\/\/lambchat\.com\/features<\/loc>[\s\S]*<priority>0\.9<\/priority>/,
  );
});
