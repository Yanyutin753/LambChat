import { readFileSync } from "node:fs";

const filesSkeletonSource = readFileSync(
  new URL("../FilesSkeletons.tsx", import.meta.url),
  "utf8",
);
const emptyStateSource = readFileSync(
  new URL("../../fileLibrary/components/EmptyState.tsx", import.meta.url),
  "utf8",
);
const skeletonIndexSource = readFileSync(
  new URL("../index.ts", import.meta.url),
  "utf8",
);

function exportedComponentBody(source: string, name: string): string {
  const start = source.indexOf(`export function ${name}(`);
  if (start === -1) return "";
  const nextExport = source.indexOf("export function", start + 1);
  return source.slice(start, nextExport === -1 ? undefined : nextExport);
}

test("files list skeleton renders session groups without a toolbar", () => {
  const body = exportedComponentBody(filesSkeletonSource, "FilesListSkeleton");
  expect(body).not.toBe("");
  // Real Toolbar is already mounted when the list skeleton shows, so the
  // skeleton must not render a second (sticky) toolbar strip.
  expect(body).not.toMatch(/sticky/);
  expect(body).not.toMatch(/skeleton-line h-9/);
  // It still previews session groups with cards.
  expect(body).toMatch(/FileCardSkeleton/);
});

test("full files content skeleton keeps toolbar for page-level fallback", () => {
  const body = exportedComponentBody(
    filesSkeletonSource,
    "FilesContentSkeleton",
  );
  expect(body).not.toBe("");
  expect(body).toMatch(/FilesToolbarSkeleton/);
  expect(body).toMatch(/FilesListSkeleton/);
});

test("files loading state inside the panel uses the toolbar-less skeleton", () => {
  expect(emptyStateSource).toMatch(/FilesListSkeleton/);
  expect(emptyStateSource).not.toMatch(/FilesContentSkeleton/);
  expect(skeletonIndexSource).toMatch(/FilesListSkeleton/);
});
