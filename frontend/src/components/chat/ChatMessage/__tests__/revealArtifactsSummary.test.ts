import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("reveal artifacts summary mirrors the file tree view row details", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    summarySource,
    /const imageSrc = isImageFile\(ext\)/,
    "file rows should detect image thumbnails the same way FileTreeView does",
  );
  assert.match(
    summarySource,
    /<ImageWithSkeleton[\s\S]*src=\{imageSrc\}/,
    "image file rows should render a thumbnail from the artifact preview URL",
  );
  assert.match(
    summarySource,
    /formatSize\(dirSize\)/,
    "directory rows should show the aggregated size like FileTreeView",
  );
});

test("all files image rows open an ImageViewer gallery with navigation", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    summarySource,
    /import\s+\{[^}]*ImageViewer[^}]*\}\s+from\s+"..\/..\/common"/,
    "all files panel should use the shared fullscreen image viewer",
  );
  assert.match(
    summarySource,
    /getRevealArtifactImagePreviewItems/,
    "all files panel should derive image gallery items from reveal artifacts",
  );
  assert.match(
    summarySource,
    /onOpenImagePreview=/,
    "image file rows should open the local image gallery",
  );
  assert.match(
    summarySource,
    /<ImageViewer[\s\S]*?\bonPrevious=/,
    "gallery should wire previous navigation",
  );
  assert.match(
    summarySource,
    /<ImageViewer[\s\S]*?\bonNext=/,
    "gallery should wire next navigation",
  );
  assert.match(
    summarySource,
    /<ImageViewer[\s\S]*?\bpositionLabel=/,
    "gallery should show the image position",
  );
});

test("all files summary waits until the message stops streaming", () => {
  const summarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    summarySource,
    /if\s*\(\s*isStreaming\s*\|\|\s*artifacts\.length\s*===\s*0\s*\)/,
    "artifact delivery events should keep the all files entry hidden until the message is idle",
  );
});
