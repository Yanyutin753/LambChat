import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { mkdir } from "node:fs/promises";

export function assertImageCase(data) {
  assert(data.publicLoaded, "public image did not load");
  assert(data.directRequests > 0, "no direct request was attempted");
  if (data.blocked) {
    assert(
      data.proxyUrls.length === 1,
      "blocked storage must use exactly one proxy",
    );
    const proxy = new URL(data.proxyUrls[0]);
    assert(
      proxy.searchParams.has("thumb") || proxy.searchParams.has("cover"),
      "fallback must use a small-image proxy",
    );
  } else {
    assert(data.proxyUrls.length === 0, "normal images must use zero proxies");
    assert(data.storageRequests > 0, "no actual storage request was observed");
  }
  assert(
    data.privateLoaded && data.privateBlob,
    "private image must use an authenticated blob",
  );
  assert(
    data.privateRequests.length > 0 &&
      data.privateRequests.every((r) => r.authorized),
    "private request missing authentication",
  );
  assert(
    data.privateStorageRequests === 0,
    "private storage redirect observed",
  );
  assert(data.credentialLeaks === 0, "account credentials reached storage");
  assert(data.errors.length === 0, "browser exception occurred");
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  const metadata = JSON.parse(input);
  const require = createRequire(import.meta.url);
  const { chromium, devices } = require("/usr/lib/node_modules/playwright");
  const browser = await chromium.launch({ headless: true });
  const origin = new URL(metadata.base).origin;
  const hasKey = (request, key) => {
    try {
      return decodeURIComponent(new URL(request.url).pathname).includes(key);
    } catch {
      return false;
    }
  };
  const proxyRequests = (requests) =>
    requests.filter(
      (r) =>
        hasKey(r, metadata.publicKey) &&
        new URL(r.url).origin === origin &&
        new URL(r.url).searchParams.get("proxy") === "true",
    );
  const imageReady = async (
    page,
    selector,
    width = null,
    blob = false,
    root = null,
  ) => {
    await page.waitForFunction(
      ({ selector, width, blob, root }) => {
        const image = (root || document).querySelector(selector);
        return (
          image?.complete &&
          image.naturalWidth > 0 &&
          (!width || image.naturalWidth === width) &&
          (!blob || image.src.startsWith("blob:"))
        );
      },
      { selector, width, blob, root },
      { timeout: 45000 },
    );
  };
  let number = 7;
  try {
    for (const [platform, device] of [
      ["desktop", null],
      ["Android", devices["Pixel 7"]],
      ["iOS", devices["iPhone 13"]],
    ]) {
      for (const blocked of [false, true]) {
        const name = `I${number++}-${platform}图片${
          blocked ? "存储故障回退" : "正常直连"
        }`;
        const context = await browser.newContext(
          device ? { ...device } : { viewport: { width: 1280, height: 900 } },
        );
        const page = await context.newPage();
        const requests = [],
          errors = [];
        page.on("request", (request) =>
          requests.push({
            url: request.url(),
            method: request.method(),
            authorized: !!request.headers()["authorization"],
          }),
        );
        page.on("pageerror", (error) => errors.push(error.message));
        await context.addInitScript(
          (token) => localStorage.setItem("access_token", token),
          metadata.token,
        );
        const cdp = await context.newCDPSession(page);
        await cdp.send("Network.enable");
        await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
        if (blocked)
          await cdp.send("Network.setBlockedURLs", {
            urls: [`*://${metadata.storageHost}/*`],
          });
        try {
          await page.goto(metadata.base + "/chat/" + metadata.session, {
            waitUntil: "domcontentloaded",
            timeout: 30000,
          });
          const publicImage = page
            .getByAltText(metadata.publicAlt, { exact: true })
            .first();
          const privateImage = page
            .getByAltText(metadata.privateAlt, { exact: true })
            .first();
          await publicImage.waitFor({ state: "visible", timeout: 45000 });
          await publicImage.scrollIntoViewIfNeeded();
          await privateImage.scrollIntoViewIfNeeded();
          await imageReady(page, `img[alt="${metadata.publicAlt}"]`);
          await imageReady(page, `img[alt="${metadata.privateAlt}"]`);
          const gallery = {
            blocked,
            publicLoaded: await publicImage.evaluate(
              (i) => i.complete && i.naturalWidth > 0,
            ),
            privateLoaded: await privateImage.evaluate(
              (i) => i.complete && i.naturalWidth > 0,
            ),
            privateBlob: (await privateImage.getAttribute("src")).startsWith(
              "blob:",
            ),
            directRequests: requests.filter(
              (r) =>
                hasKey(r, metadata.publicKey) &&
                new URL(r.url).origin === origin &&
                new URL(r.url).searchParams.get("proxy") !== "true",
            ).length,
            storageRequests: requests.filter(
              (r) =>
                hasKey(r, metadata.publicKey) &&
                new URL(r.url).hostname === metadata.storageHost,
            ).length,
            proxyUrls: proxyRequests(requests).map((r) => r.url),
            privateRequests: requests.filter(
              (r) =>
                hasKey(r, metadata.privateKey) &&
                new URL(r.url).origin === origin &&
                r.method === "GET",
            ),
            privateStorageRequests: requests.filter(
              (r) =>
                hasKey(r, metadata.privateKey) &&
                new URL(r.url).hostname === metadata.storageHost,
            ).length,
            credentialLeaks: requests.filter(
              (r) =>
                new URL(r.url).hostname === metadata.storageHost &&
                r.authorized,
            ).length,
            errors,
          };
          assertImageCase(gallery);
          assert(
            (await publicImage.evaluate((i) => i.naturalWidth)) <= 560,
            "gallery did not use the small image",
          );
          let start = requests.length;
          await publicImage.click();
          const dialog = page.getByRole("dialog");
          await dialog.waitFor({ state: "visible" });
          await imageReady(
            page,
            "img",
            1280,
            false,
            await dialog.elementHandle(),
          );
          assert.equal(
            await dialog.locator("img").evaluate((i) => i.naturalWidth),
            1280,
            "viewer must load the original",
          );
          assert.equal(
            proxyRequests(requests.slice(start)).length,
            blocked ? 1 : 0,
            "viewer proxy retry count mismatch",
          );
          await page.keyboard.press("Escape");
          await dialog.waitFor({ state: "hidden" });
          start = requests.length;
          await privateImage.click();
          await dialog.waitFor({ state: "visible" });
          await imageReady(
            page,
            "img",
            1280,
            true,
            await dialog.elementHandle(),
          );
          assert(
            (await dialog.locator("img").getAttribute("src")).startsWith(
              "blob:",
            ),
            "private viewer must render a blob",
          );
          const privateReads = requests
            .slice(start)
            .filter(
              (r) =>
                hasKey(r, metadata.privateKey) &&
                new URL(r.url).origin === origin &&
                r.method === "GET",
            );
          assert(
            privateReads.length > 0 && privateReads.every((r) => r.authorized),
            "private viewer did not use authentication",
          );
          assert(
            !requests.some(
              (r) =>
                new URL(r.url).hostname === metadata.storageHost &&
                (r.authorized || hasKey(r, metadata.privateKey)),
            ),
            "private image or credentials reached storage",
          );
          assert.equal(errors.length, 0, "browser exception occurred");
          console.log(
            JSON.stringify({
              test: name,
              ok: true,
              detail: `Chromium${
                platform === "desktop" ? "桌面" : " " + platform + "视口模拟"
              }；缩略图代理=${gallery.proxyUrls.length}，查看器代理=${
                blocked ? 1 : 0
              }；私有缩略图/查看器均鉴权blob`,
            }),
          );
        } catch (error) {
          await mkdir("/root/disttest-image-failures", {
            recursive: true,
            mode: 0o700,
          });
          await page
            .screenshot({
              path: `/root/disttest-image-failures/${metadata.session}-${platform}-${blocked}.png`,
            })
            .catch(() => {});
          const images = await page
            .getByRole("dialog")
            .locator("img")
            .evaluateAll((images) =>
              images.map((i) => ({
                complete: i.complete,
                width: i.naturalWidth,
                src: i.currentSrc.split("?")[0],
              })),
            )
            .catch(() => []);
          const detail = (
            String(error.message) +
            "; images=" +
            JSON.stringify(images)
          )
            .replace(/https?:\/\/[^\s)]+/g, (url) => url.split("?")[0])
            .slice(0, 260);
          console.log(JSON.stringify({ test: name, ok: false, detail }));
          process.exitCode = 1;
          return;
        } finally {
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
  }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.log(
      JSON.stringify({
        test: "I0-浏览器回归启动",
        ok: false,
        detail: error.name + ": browser harness failed",
      }),
    );
    process.exitCode = 1;
  });
}
