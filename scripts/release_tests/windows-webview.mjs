import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { assertImageCase } from "./image-loading-browser.mjs";
const root = process.argv[2].replace(/\/$/, "") + "/";
const candidate = JSON.parse(await readFile(root + "candidate.json", "utf8"));
const metadata = JSON.parse(await readFile(root + "metadata.json", "utf8"));
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const browser = await chromium.connectOverCDP(process.argv[3]);
const results = [];
let page, environment;
try {
  const pages = browser.contexts().flatMap((c) => c.pages());
  assert.equal(pages.length, 1, "expected only the isolated native WebView");
  page = pages[0];
  assert.equal(
    new URL(page.url()).origin,
    "http://tauri.localhost",
    "must attach to the packaged Tauri app",
  );
  environment = await page.evaluate(() => ({
    origin: location.origin,
    tauri: !!window.__TAURI_INTERNALS__,
    userAgent: navigator.userAgent,
    priorToken: !!localStorage.getItem("access_token"),
  }));
  assert(
    environment.tauri && /Edg\//.test(environment.userAgent),
    "real Tauri/WebView2 bindings missing",
  );
  assert.equal(
    environment.priorToken,
    false,
    "profile isolation failed; preserve original login",
  );
  await writeFile(
    root + "windows-native-runtime.json",
    JSON.stringify(environment, null, 2),
  );
  const nativeOrigin = environment.origin,
    origin = new URL(metadata.base).origin;
  await page.addInitScript(
    ({ token, base }) => {
      localStorage.setItem("lambchat_server_url", base);
      localStorage.setItem("access_token", token);
      localStorage.setItem("i18nextLng", "zh");
    },
    { token: metadata.token, base: metadata.base },
  );
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  const requests = [],
    errors = [],
    missing = [],
    scripts = new Set();
  page.on("request", (r) =>
    requests.push({
      url: r.url(),
      method: r.method(),
      authorized: !!r.headers()["authorization"],
    }),
  );
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/assets/")) {
      if (r.status() >= 400) missing.push(r.status() + " " + path);
      if (path.endsWith(".js")) scripts.add(path);
    }
  });
  const hasKey = (r, k) => {
    try {
      return decodeURIComponent(new URL(r.url).pathname).includes(k);
    } catch {
      return false;
    }
  };
  const proxyRequests = (rs) =>
    rs.filter(
      (r) =>
        hasKey(r, metadata.publicKey) &&
        new URL(r.url).origin === origin &&
        new URL(r.url).searchParams.get("proxy") === "true",
    );
  const ready = async (locator, width = null, blob = false) => {
    await locator.waitFor({ state: "visible", timeout: 45000 });
    await locator.evaluate(
      (image, { width, blob }) =>
        new Promise((resolve, reject) => {
          const deadline = Date.now() + 45000;
          const check = () => {
            if (
              image.complete &&
              image.naturalWidth > 0 &&
              (!width || image.naturalWidth === width) &&
              (!blob || image.src.startsWith("blob:"))
            )
              resolve();
            else if (Date.now() > deadline)
              reject(new Error("native image failed to decode"));
            else setTimeout(check, 100);
          };
          check();
        }),
      { width, blob },
    );
  };
  for (const blocked of [false, true]) {
    requests.length = 0;
    errors.length = 0;
    missing.length = 0;
    await cdp.send("Network.clearBrowserCache");
    await cdp.send("Network.setBlockedURLs", {
      urls: blocked ? [`*://${metadata.storageHost}/*`] : [],
    });
    await page.goto(nativeOrigin + "/chat/" + metadata.session, {
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    const publicImage = page
      .getByAltText(metadata.publicAlt, { exact: true })
      .first();
    const privateImage = page
      .getByAltText(metadata.privateAlt, { exact: true })
      .first();
    await ready(publicImage);
    await publicImage.scrollIntoViewIfNeeded();
    await ready(privateImage);
    await privateImage.scrollIntoViewIfNeeded();
    const gallery = {
      blocked,
      publicLoaded: await publicImage.evaluate(
        (i) => i.complete && i.naturalWidth > 0,
      ),
      privateLoaded: await privateImage.evaluate(
        (i) => i.complete && i.naturalWidth > 0,
      ),
      privateBlob: (await privateImage.getAttribute("src")).startsWith("blob:"),
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
        (r) => new URL(r.url).hostname === metadata.storageHost && r.authorized,
      ).length,
      errors,
    };
    assertImageCase(gallery);
    assert(
      (await publicImage.evaluate((i) => i.naturalWidth)) <= 560,
      "native gallery must use a small image",
    );
    await page.screenshot({
      path:
        root + `windows-native-${blocked ? "fallback" : "direct"}-gallery.png`,
    });
    let start = requests.length;
    await publicImage.click();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor({ state: "visible" });
    await ready(dialog.locator("img"), 1280);
    assert.equal(
      proxyRequests(requests.slice(start)).length,
      blocked ? 1 : 0,
      "native original viewer proxy count",
    );
    await page.screenshot({
      path:
        root + `windows-native-${blocked ? "fallback" : "direct"}-viewer.png`,
    });
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    start = requests.length;
    await privateImage.click();
    await dialog.waitFor({ state: "visible" });
    await ready(dialog.locator("img"), 1280, true);
    const reads = requests
      .slice(start)
      .filter(
        (r) =>
          hasKey(r, metadata.privateKey) &&
          new URL(r.url).origin === origin &&
          r.method === "GET",
      );
    assert(
      reads.length > 0 && reads.every((r) => r.authorized),
      "native private viewer must authenticate",
    );
    assert(
      !requests.some(
        (r) =>
          new URL(r.url).hostname === metadata.storageHost &&
          (r.authorized || hasKey(r, metadata.privateKey)),
      ),
      "private data or account credentials reached storage",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(missing, []);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    results.push({
      case: blocked ? "real-native-storage-failure" : "real-native-direct",
      passed: true,
      galleryProxies: gallery.proxyUrls.length,
      viewerProxies: blocked ? 1 : 0,
      privateAuthenticatedBlob: true,
      credentialLeaks: 0,
      pageErrors: 0,
    });
    console.log(
      "PASS real Windows WebView2 " +
        (blocked ? "blocked storage silent fallback" : "normal zero proxy") +
        "; gallery/viewer/private authentication",
    );
  }
  await cdp.send("Network.setBlockedURLs", { urls: [] });
  for (const route of ["/settings", "/files", "/chat"]) {
    errors.length = 0;
    missing.length = 0;
    scripts.clear();
    await page.goto(nativeOrigin + route, {
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    if (route === "/chat")
      await page
        .locator('[contenteditable="true"]')
        .first()
        .waitFor({ timeout: 45000 });
    else
      await page
        .locator("main[data-panel] h1:visible,main[data-panel] h2:visible")
        .first()
        .waitFor({ timeout: 45000 });
    assert.equal(new URL(page.url()).pathname, route);
    assert(
      ![...scripts].some((p) => /\/ProfileModal-[^/]+\.js$/.test(p)),
      "closed profile loaded eagerly",
    );
    if (route !== "/chat")
      assert(
        ![...scripts].some((p) => /\/ChatAppContent-[^/]+\.js$/.test(p)),
        "management route loaded chat workspace",
      );
    if (route === "/chat") {
      const editor = page.locator('[contenteditable="true"]').first();
      await editor.fill("真机验收 draft");
      assert.match(await editor.innerText(), /真机验收/);
      await editor.fill("");
      const locale = JSON.parse(
        await readFile(
          new URL("../../frontend/src/i18n/locales/zh.json", import.meta.url),
          "utf8",
        ),
      );
      await page
        .getByRole("button", { name: locale.profile.title, exact: true })
        .first()
        .click();
      await page
        .getByRole("menuitem", { name: locale.users.user, exact: true })
        .click();
      const profile = page.locator(".profile-dialog");
      await profile.waitFor({ state: "visible", timeout: 30000 });
      await profile
        .locator(".profile-page-title")
        .waitFor({ state: "visible" });
      assert(
        [...scripts].some((p) => /\/ProfileModal-[^/]+\.js$/.test(p)),
        "profile did not load on open",
      );
      await page.screenshot({ path: root + "windows-native-lazy-profile.png" });
      await page.keyboard.press("Escape");
      await profile.waitFor({ state: "hidden" });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(missing, []);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
    );
    results.push({
      case: "real-native-route" + route,
      passed: true,
      lazyProfileOpened: route === "/chat",
      missingChunks: 0,
      pageErrors: 0,
    });
    console.log(
      "PASS real Windows packaged page " +
        route +
        (route === "/chat" ? " + draft + deferred profile" : ""),
    );
  }
  assert.equal(results.length, 5);
  await page.goto(nativeOrigin + "/chat/" + metadata.session, {
    waitUntil: "domcontentloaded",
  });
  await ready(page.getByAltText(metadata.publicAlt, { exact: true }).first());
  console.log("PASS 5/5 real Windows native cases");
} catch (error) {
  await page
    ?.screenshot({ path: root + "windows-native-failure.png" })
    .catch(() => {});
  results.push({ passed: false, error: String(error.message).slice(0, 350) });
  throw error;
} finally {
  await writeFile(
    root + "native.json",
    JSON.stringify(
      {
        tag: candidate.tag,
        sha: candidate.sha,
        run_id: candidate.run_id,
        environment,
        cases: results,
      },
      null,
      2,
    ),
  );
  await browser.close();
}
