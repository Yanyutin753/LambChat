import {
  createWordPreviewRendererOptions,
  measureDocxPreview,
  renderDocxPreviewHtml,
} from "../wordPreviewRenderer.ts";

test("preserves DOCX page geometry while disabling unsafe altChunk rendering", () => {
  const options = createWordPreviewRendererOptions();

  expect(options).toMatchObject({
    inWrapper: true,
    ignoreWidth: false,
    ignoreHeight: false,
    renderAltChunks: false,
  });
});

test("measures generated DOCX page width and continuous wrapper height", () => {
  const page = { offsetWidth: 816 } as HTMLElement;
  const wrapper = { scrollHeight: 2112 } as HTMLElement;
  const container = {
    querySelector: (selector: string) =>
      selector === "section.docx" ? page : wrapper,
  } as unknown as HTMLElement;

  expect(measureDocxPreview(container)).toEqual({
    width: 816,
    height: 2112,
  });
});

test("renders with docx-preview before using mammoth fallback", async () => {
  const calls: string[] = [];
  const container = {
    innerHTML: "",
    textContent: "",
  } as unknown as HTMLElement;
  const styleContainer = {} as HTMLElement;
  const arrayBuffer = new ArrayBuffer(8);

  const result = await renderDocxPreviewHtml({
    arrayBuffer,
    container,
    styleContainer,
    renderAsync: async (input, output, styles, options) => {
      calls.push("docx-preview");
      expect(input).toBe(arrayBuffer);
      expect(output).toBe(container);
      expect(styles).toBe(styleContainer);
      expect(options).toBeTruthy();
      expect(options.renderAltChunks).toBe(false);
      output.innerHTML = "<section>Rendered DOCX</section>";
    },
    convertToHtml: async () => {
      calls.push("mammoth");
      return { value: "<p>Fallback</p>" };
    },
  });

  expect(calls).toEqual(["docx-preview"]);
  expect(result).toEqual({ kind: "docx-preview" });
  expect(container.innerHTML).toBe("<section>Rendered DOCX</section>");
});

test("falls back to mammoth when docx-preview cannot render", async () => {
  const calls: string[] = [];
  const container = {
    innerHTML: "<section>stale</section>",
    textContent: "stale",
  } as unknown as HTMLElement;
  const styleContainer = {} as HTMLElement;

  const result = await renderDocxPreviewHtml({
    arrayBuffer: new ArrayBuffer(8),
    container,
    styleContainer,
    renderAsync: async () => {
      calls.push("docx-preview");
      throw new Error("docx-preview failed");
    },
    convertToHtml: async () => {
      calls.push("mammoth");
      return { value: "<p>Fallback</p>" };
    },
    onDocxPreviewError: () => undefined,
  });

  expect(calls).toEqual(["docx-preview", "mammoth"]);
  expect(result).toEqual({ kind: "html", html: "<p>Fallback</p>" });
  expect(container.innerHTML).toBe("");
});
