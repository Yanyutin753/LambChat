/** Run in the Codex CUA browser runtime with the Markdown file fixture open. */
export async function runMarkdownPreviewScrollE2E(tab) {
  const geometry = await tab.playwright.evaluate(() => {
    const body = document.querySelector(".tool-console-body");
    const preview = body?.querySelector(".markdown-preview.overflow-auto");
    const labels = Array.from(
      preview?.querySelectorAll(".ai-comparison-value .sr-only") || [],
    );
    return {
      outerHeight: body?.clientHeight,
      outerScrollHeight: body?.scrollHeight,
      innerHeight: preview?.clientHeight,
      innerScrollHeight: preview?.scrollHeight,
      labelCount: labels.length,
    };
  });
  if (
    !geometry.labelCount ||
    geometry.innerScrollHeight <= geometry.innerHeight
  ) {
    throw new Error(
      "Need a long Markdown comparison table to exercise scrolling",
    );
  }
  if (geometry.outerScrollHeight > geometry.outerHeight + 1) {
    throw new Error(
      `Markdown preview creates an empty outer scroll region: ${JSON.stringify(
        geometry,
      )}`,
    );
  }
  return geometry;
}
