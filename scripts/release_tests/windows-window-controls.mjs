export async function exerciseMaximizeRestore(page, windowControls) {
  const initiallyMaximized = await page.evaluate(() =>
    window.__TAURI_INTERNALS__.invoke("plugin:window|is_maximized", {
      label: window.__TAURI_INTERNALS__.metadata.currentWindow.label,
    }),
  );
  const maximize = windowControls.getByRole("button", { name: "最大化", exact: true });
  const restore = windowControls.getByRole("button", { name: "还原", exact: true });
  // Window-state restoration can start the packaged app maximized.
  await (initiallyMaximized ? restore : maximize).waitFor({ state: "visible", timeout: 5000 });
  if (initiallyMaximized) await restore.click();
  await maximize.click();
  await restore.waitFor({ state: "visible", timeout: 5000 });
  await restore.click();
  await maximize.waitFor({ state: "visible", timeout: 5000 });
}
