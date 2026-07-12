import JSZip from "jszip";

import { extractPptxSlideTexts } from "../pptTextPreview.ts";

test("extracts visible text from pptx slide XML in slide order", async () => {
  const zip = new JSZip();
  zip.file(
    "ppt/slides/slide2.xml",
    `<p:sld><p:cSld><p:spTree><a:t>Second</a:t></p:spTree></p:cSld></p:sld>`,
  );
  zip.file(
    "ppt/slides/slide1.xml",
    `<p:sld><p:cSld><p:spTree><a:t>First</a:t><a:t>&amp; Title</a:t></p:spTree></p:cSld></p:sld>`,
  );

  const buffer = await zip.generateAsync({ type: "arraybuffer" });

  const slides = await extractPptxSlideTexts(buffer);

  expect(slides).toEqual([
    { index: 1, text: "First & Title" },
    { index: 2, text: "Second" },
  ]);
});

test("returns an empty list when pptx has no readable slide text", async () => {
  const zip = new JSZip();
  zip.file("ppt/slides/slide1.xml", `<p:sld><p:cSld /></p:sld>`);

  const buffer = await zip.generateAsync({ type: "arraybuffer" });

  const slides = await extractPptxSlideTexts(buffer);

  expect(slides).toEqual([]);
});
