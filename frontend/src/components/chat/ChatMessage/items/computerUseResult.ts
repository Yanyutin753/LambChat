export function computerUseRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function parseComputerUseResult(
  result?: string | Record<string, unknown>,
) {
  let data = computerUseRecord(result);
  let structured = typeof result !== "string";
  const original = typeof result === "string" ? result : "";
  if (original) {
    try {
      data = computerUseRecord(JSON.parse(original));
      structured = true;
    } catch {
      // Older status results are Python repr; read known scalars, never evaluate them.
      if (original.startsWith("{")) {
        for (const key of ["platform", "accessibility", "screen_recording"]) {
          const match = original.match(new RegExp(`'${key}':\\s*'([^']*)'`));
          if (match) data[key] = match[1];
        }
        const ready = original.match(/'ready':\s*(True|False)/);
        if (ready) data.ready = ready[1] === "True";
      }
    }
  }

  const screenshot = computerUseRecord(data.screenshot);
  const screenshotSrc =
    typeof screenshot.url === "string" &&
    /^\/api\/upload\/file\//.test(screenshot.url)
      ? screenshot.url
      : typeof screenshot.mime === "string" &&
          /^image\/(jpeg|png|webp)$/.test(screenshot.mime) &&
          typeof screenshot.data_b64 === "string" &&
          /^[A-Za-z0-9+/]+={0,2}$/.test(screenshot.data_b64)
        ? `data:${screenshot.mime};base64,${screenshot.data_b64}`
        : undefined;
  const screenshotInfo = Object.fromEntries(
    Object.entries(screenshot).filter(([key]) => key !== "data_b64"),
  );
  const text =
    Object.keys(data).length && structured
      ? JSON.stringify(
          {
            ...data,
            ...(data.screenshot ? { screenshot: screenshotInfo } : {}),
          },
          null,
          2,
        )
      : original;
  const error =
    typeof data.error === "string"
      ? data.error
      : (original.match(/^ERROR\s+(\w+)/)?.[1] ?? "");
  return { data, text, error, screenshotSrc };
}
