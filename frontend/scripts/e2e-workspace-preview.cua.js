/** Run inside the Codex CUA browser runtime, with the workspace tree already open.
 * Uses the real page, image decoder, layout engine, and browser download event.
 * API byte/ZIP checks live in scripts/e2e_workspace_preview.py.
 */
async function runWorkspaceBrowserE2E(tab, { pngName, zipName }) {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const geometry = await tab.playwright.evaluate(() =>
    Array.from(document.querySelectorAll(".workspace-file-row")).map((row) => {
      const children = Array.from(row.children);
      const icon = children[1].getBoundingClientRect();
      const label = children[2].getBoundingClientRect();
      return {
        depth: getComputedStyle(row).paddingLeft,
        iconX: icon.x,
        iconWidth: icon.width,
        textX: label.x,
        text: label.textContent,
      };
    }),
  );
  assert(geometry.length >= 2, "Need directory and file rows to verify alignment");
  for (const row of geometry) {
    assert(row.iconWidth === 16, `Wrong icon width: ${row.text}`);
    for (const peer of geometry.filter((item) => item.depth === row.depth)) {
      assert(Math.abs(peer.iconX - row.iconX) < 0.5, "Same-depth icons are misaligned");
      assert(Math.abs(peer.textX - row.textX) < 0.5, "Same-depth filenames are misaligned");
    }
  }
  await tab.playwright.getByRole("button", { name: pngName, exact: true }).click();
  await tab.playwright.domSnapshot();
  const image = tab.playwright.locator(".workspace-preview img");
  await image.waitFor({ state: "visible", timeoutMs: 60000 });
  const decoded = await image.evaluate(async (element) => {
    await element.decode();
    return {
      complete: element.complete,
      width: element.naturalWidth,
      height: element.naturalHeight,
    };
  });
  assert(decoded.complete && decoded.width > 0 && decoded.height > 0, "PNG did not decode");
  if (!(await tab.playwright.getByRole("button", { name: zipName, exact: true }).isVisible())) {
    await tab.playwright.locator(".workspace-preview .document-preview-toolbar button").first().click();
    await tab.playwright.domSnapshot();
  }
  await tab.playwright.getByRole("button", { name: zipName, exact: true }).click();
  await tab.playwright.domSnapshot();
  const download = tab.playwright.waitForEvent("download", { timeoutMs: 60000 });
  await tab.playwright.locator(".workspace-preview").getByRole("button", { name: /下载文件|Download file/i }).click();
  const downloaded = await download;
  const path = await downloaded.path({ timeoutMs: 60000 });
  assert(path, "ZIP download did not complete");
  return { geometry, decoded, downloadedZipPath: path };
}
