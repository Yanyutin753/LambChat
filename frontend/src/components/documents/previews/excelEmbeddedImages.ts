import JSZip, { type JSZipObject } from "jszip";

const OFFICE_RELATIONSHIP_NAMESPACE =
  "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

const OOXML_EXTENSIONS = new Set(["xlsx", "xlsm", "xltx", "xlam"]);

const MIME_BY_EXTENSION: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  bmp: "image/bmp",
  svg: "image/svg+xml",
};

interface PackageRelationship {
  target: string;
  external: boolean;
  type: string;
}

interface ParsedPictureAnchor
  extends Omit<ExcelEmbeddedImage, "blob" | "mimeType"> {
  relationshipId: string;
}

export interface ExcelImageAnchorPoint {
  col: number;
  row: number;
  colOffsetEmu: number;
  rowOffsetEmu: number;
}

export interface ExcelImageExtent {
  widthEmu: number;
  heightEmu: number;
}

export interface ExcelEmbeddedImage {
  id: string;
  name: string;
  description: string;
  mimeType: string;
  blob: Blob;
  from: ExcelImageAnchorPoint;
  to?: ExcelImageAnchorPoint;
  extent?: ExcelImageExtent;
  order: number;
}

function parseXml(xml: string): XMLDocument | null {
  const document = new DOMParser().parseFromString(xml, "application/xml");
  return elements(document, "parsererror").length > 0 ? null : document;
}

function elements(parent: Document | Element, localName: string): Element[] {
  return Array.from(parent.getElementsByTagNameNS("*", localName));
}

function pictureAnchors(document: XMLDocument): Element[] {
  const root = document.documentElement;
  return Array.from(root.children).filter(
    (element) =>
      element.localName === "oneCellAnchor" ||
      element.localName === "twoCellAnchor",
  );
}

function relationshipAttribute(
  element: Element | undefined,
  localName: "id" | "embed",
): string {
  if (!element) return "";
  return (
    element.getAttributeNS(OFFICE_RELATIONSHIP_NAMESPACE, localName) ??
    element.getAttribute(`r:${localName}`) ??
    ""
  );
}

function relationshipPartPath(sourcePart: string): string {
  const slash = sourcePart.lastIndexOf("/");
  const directory = slash >= 0 ? sourcePart.slice(0, slash + 1) : "";
  const fileName = slash >= 0 ? sourcePart.slice(slash + 1) : sourcePart;
  return `${directory}_rels/${fileName}.rels`;
}

function resolvePackageTarget(
  sourcePart: string,
  target: string,
): string | null {
  if (!target || /^[a-z][a-z\d+.-]*:/i.test(target) || target.startsWith("/")) {
    return null;
  }

  const parts = sourcePart.split("/").slice(0, -1);
  for (const segment of target.replace(/\\/g, "/").split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (parts.length === 0) return null;
      parts.pop();
    } else {
      parts.push(segment);
    }
  }
  return parts.join("/");
}

function parseRelationships(
  document: XMLDocument,
): Map<string, PackageRelationship> {
  return new Map(
    elements(document, "Relationship").flatMap((relationship) => {
      const id = relationship.getAttribute("Id") ?? "";
      const target = relationship.getAttribute("Target") ?? "";
      if (!id || !target) return [];
      return [
        [
          id,
          {
            target,
            external: relationship.getAttribute("TargetMode") === "External",
            type: relationship.getAttribute("Type") ?? "",
          },
        ] as const,
      ];
    }),
  );
}

function childInteger(parent: Element, localName: string): number | null {
  const text = elements(parent, localName)[0]?.textContent?.trim();
  if (!text) return null;
  const value = Number(text);
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function parseAnchorPoint(
  parent: Element,
  localName: "from" | "to",
): ExcelImageAnchorPoint | null {
  const anchor = elements(parent, localName)[0];
  if (!anchor) return null;
  const col = childInteger(anchor, "col");
  const row = childInteger(anchor, "row");
  const colOffsetEmu = childInteger(anchor, "colOff");
  const rowOffsetEmu = childInteger(anchor, "rowOff");
  if (
    col == null ||
    row == null ||
    colOffsetEmu == null ||
    rowOffsetEmu == null
  ) {
    return null;
  }
  return { col, row, colOffsetEmu, rowOffsetEmu };
}

function parsePictureAnchor(
  anchor: Element,
  drawingPath: string,
  order: number,
): ParsedPictureAnchor | null {
  const picture = elements(anchor, "pic")[0];
  const blip = picture ? elements(picture, "blip")[0] : undefined;
  const relationshipId = relationshipAttribute(blip, "embed");
  const from = parseAnchorPoint(anchor, "from");
  if (!picture || !relationshipId || !from) return null;

  const metadata = elements(picture, "cNvPr")[0];
  const base = {
    id: `${drawingPath}:${relationshipId}:${order}`,
    name: metadata?.getAttribute("name") ?? "Embedded image",
    description: metadata?.getAttribute("descr") ?? "",
    from,
    order,
    relationshipId,
  };

  if (anchor.localName === "twoCellAnchor") {
    const to = parseAnchorPoint(anchor, "to");
    return to ? { ...base, to } : null;
  }

  const extent = elements(anchor, "ext")[0];
  const widthEmu = Number(extent?.getAttribute("cx"));
  const heightEmu = Number(extent?.getAttribute("cy"));
  if (
    !Number.isSafeInteger(widthEmu) ||
    widthEmu <= 0 ||
    !Number.isSafeInteger(heightEmu) ||
    heightEmu <= 0
  ) {
    return null;
  }
  return { ...base, extent: { widthEmu, heightEmu } };
}

async function readXml(zip: JSZip, path: string): Promise<XMLDocument | null> {
  const entry = zip.file(path);
  if (!entry) return null;
  try {
    return parseXml(await entry.async("string"));
  } catch {
    return null;
  }
}

async function readBlob(entry: JSZipObject, mimeType: string): Promise<Blob> {
  const bytes = await entry.async("uint8array");
  const buffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  return new Blob([buffer], { type: mimeType });
}

export async function extractExcelEmbeddedImages(
  arrayBuffer: ArrayBuffer,
  fileName: string,
): Promise<Map<string, ExcelEmbeddedImage[]>> {
  const extension = fileName.split(".").pop()?.toLowerCase() ?? "";
  if (!OOXML_EXTENSIONS.has(extension)) return new Map();

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(arrayBuffer);
  } catch {
    return new Map();
  }
  const workbookPath = "xl/workbook.xml";
  const workbook = await readXml(zip, workbookPath);
  const workbookRelationships = await readXml(
    zip,
    relationshipPartPath(workbookPath),
  );
  if (!workbook || !workbookRelationships) return new Map();

  const imagesBySheet = new Map<string, ExcelEmbeddedImage[]>();
  const workbookRels = parseRelationships(workbookRelationships);

  for (const sheet of elements(workbook, "sheet")) {
    const name = sheet.getAttribute("name") ?? "";
    const sheetRelationship = workbookRels.get(
      relationshipAttribute(sheet, "id"),
    );
    if (!name || !sheetRelationship || sheetRelationship.external) continue;

    const worksheetPath = resolvePackageTarget(
      workbookPath,
      sheetRelationship.target,
    );
    if (!worksheetPath) continue;
    const worksheet = await readXml(zip, worksheetPath);
    const worksheetRelationships = await readXml(
      zip,
      relationshipPartPath(worksheetPath),
    );
    if (!worksheet || !worksheetRelationships) continue;

    const drawingElement = elements(worksheet, "drawing")[0];
    const drawingRelationship = parseRelationships(worksheetRelationships).get(
      relationshipAttribute(drawingElement, "id"),
    );
    if (!drawingRelationship || drawingRelationship.external) continue;

    const drawingPath = resolvePackageTarget(
      worksheetPath,
      drawingRelationship.target,
    );
    if (!drawingPath) continue;
    const drawing = await readXml(zip, drawingPath);
    const drawingRelationships = await readXml(
      zip,
      relationshipPartPath(drawingPath),
    );
    if (!drawing || !drawingRelationships) continue;

    const drawingRels = parseRelationships(drawingRelationships);
    const images: ExcelEmbeddedImage[] = [];
    for (const [order, anchor] of pictureAnchors(drawing).entries()) {
      const parsed = parsePictureAnchor(anchor, drawingPath, order);
      if (!parsed) continue;
      const mediaRelationship = drawingRels.get(parsed.relationshipId);
      if (
        !mediaRelationship ||
        mediaRelationship.external ||
        !mediaRelationship.type.endsWith("/image")
      ) {
        continue;
      }

      const mediaPath = resolvePackageTarget(
        drawingPath,
        mediaRelationship.target,
      );
      const mediaExtension = mediaPath?.split(".").pop()?.toLowerCase() ?? "";
      const mimeType = MIME_BY_EXTENSION[mediaExtension];
      const mediaEntry = mediaPath ? zip.file(mediaPath) : null;
      if (!mimeType || !mediaEntry) continue;

      const { relationshipId: _relationshipId, ...image } = parsed;
      try {
        images.push({
          ...image,
          mimeType,
          blob: await readBlob(mediaEntry, mimeType),
        });
      } catch {
        continue;
      }
    }
    if (images.length > 0) imagesBySheet.set(name, images);
  }

  return imagesBySheet;
}
