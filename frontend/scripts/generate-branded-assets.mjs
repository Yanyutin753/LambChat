import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { deflateSync, inflateSync } from "node:zlib";

const checkOnly = process.argv.includes("--check");
const brandIconPath = resolve("public/icons/icon-512.png");
const brandIcon = readFileSync(brandIconPath);
// App icons use an opaque tile; splash images keep the existing web artwork.
const mobileIcon = readFileSync(resolve("resources/mobile-icon.png"));
const IOS_APP_ICON_SIZE = 1024;
const crcTable = createCrcTable();
const iosAppIcon = scalePngNearest(mobileIcon, IOS_APP_ICON_SIZE / 512);

const targets = [
  "resources/splash.png",
  "android/app/src/main/res/drawable/splash.png",
  "android/app/src/main/res/drawable-land-hdpi/splash.png",
  "android/app/src/main/res/drawable-land-mdpi/splash.png",
  "android/app/src/main/res/drawable-land-xhdpi/splash.png",
  "android/app/src/main/res/drawable-land-xxhdpi/splash.png",
  "android/app/src/main/res/drawable-land-xxxhdpi/splash.png",
  "android/app/src/main/res/drawable-port-hdpi/splash.png",
  "android/app/src/main/res/drawable-port-mdpi/splash.png",
  "android/app/src/main/res/drawable-port-xhdpi/splash.png",
  "android/app/src/main/res/drawable-port-xxhdpi/splash.png",
  "android/app/src/main/res/drawable-port-xxxhdpi/splash.png",
  "ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732.png",
  "ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732-1.png",
  "ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732-2.png",
];

const mobileIconTargets = [
  "resources/icon.png",
  "android/app/src/main/res/mipmap-hdpi/ic_launcher.png",
  "android/app/src/main/res/mipmap-hdpi/ic_launcher_foreground.png",
  "android/app/src/main/res/mipmap-hdpi/ic_launcher_round.png",
  "android/app/src/main/res/mipmap-mdpi/ic_launcher.png",
  "android/app/src/main/res/mipmap-mdpi/ic_launcher_foreground.png",
  "android/app/src/main/res/mipmap-mdpi/ic_launcher_round.png",
  "android/app/src/main/res/mipmap-xhdpi/ic_launcher.png",
  "android/app/src/main/res/mipmap-xhdpi/ic_launcher_foreground.png",
  "android/app/src/main/res/mipmap-xhdpi/ic_launcher_round.png",
  "android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png",
  "android/app/src/main/res/mipmap-xxhdpi/ic_launcher_foreground.png",
  "android/app/src/main/res/mipmap-xxhdpi/ic_launcher_round.png",
  "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png",
  "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher_foreground.png",
  "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher_round.png",
];

const generatedTargets = new Map([
  ...mobileIconTargets.map((target) => [target, mobileIcon]),
  [
    "ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png",
    iosAppIcon,
  ],
]);

function ensureSameContent(targetPath, expectedContent) {
  const fullPath = resolve(targetPath);
  if (!existsSync(fullPath)) {
    return false;
  }
  return readFileSync(fullPath).equals(expectedContent);
}

let invalidCount = 0;

for (const target of targets) {
  if (checkOnly) {
    if (!ensureSameContent(target, brandIcon)) {
      console.error(`Brand asset is missing or stale: ${target}`);
      invalidCount += 1;
    }
    continue;
  }

  const fullPath = resolve(target);
  mkdirSync(dirname(fullPath), { recursive: true });
  writeFileSync(fullPath, brandIcon);
}

for (const [target, content] of generatedTargets) {
  if (checkOnly) {
    if (!ensureSameContent(target, content)) {
      console.error(`Brand asset is missing or stale: ${target}`);
      invalidCount += 1;
    }
    continue;
  }

  const fullPath = resolve(target);
  mkdirSync(dirname(fullPath), { recursive: true });
  writeFileSync(fullPath, content);
}

if (invalidCount > 0) {
  console.error(
    `Found ${invalidCount} native image asset(s) that do not use the LambChat brand icon.`,
  );
  process.exit(1);
}

if (!checkOnly) {
  console.log(
    `Generated ${
      targets.length + generatedTargets.size
    } LambChat branded native assets.`,
  );
}

function scalePngNearest(source, factor) {
  if (factor !== 2) {
    throw new Error("Only 2x PNG scaling is supported.");
  }

  const signature = Buffer.from([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  ]);
  if (!source.subarray(0, 8).equals(signature)) {
    throw new Error("Brand icon must be a PNG file.");
  }

  const width = source.readUInt32BE(16);
  const height = source.readUInt32BE(20);
  const bitDepth = source[24];
  const colorType = source[25];

  if (width !== 512 || height !== 512 || bitDepth !== 8 || colorType !== 6) {
    throw new Error("Brand icon must be a 512x512 8-bit RGBA PNG.");
  }

  const chunks = [];
  let offset = 8;
  const idatChunks = [];

  while (offset < source.length) {
    const length = source.readUInt32BE(offset);
    const type = source.subarray(offset + 4, offset + 8).toString("ascii");
    const data = source.subarray(offset + 8, offset + 8 + length);
    offset += 12 + length;

    if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type !== "IEND") {
      chunks.push({ type, data });
    }
  }

  const raw = unfilterPngScanlines(
    inflateSync(Buffer.concat(idatChunks)),
    width,
    height,
  );
  const sourceStride = 1 + width * 4;
  const outputWidth = width * factor;
  const outputHeight = height * factor;
  // iOS's primary marketing icon is exported as RGB, without an alpha channel.
  const outputStride = 1 + outputWidth * 3;
  const scaled = Buffer.alloc(outputStride * outputHeight);

  for (let y = 0; y < height; y += 1) {
    const sourceRow = raw.subarray(
      y * sourceStride + 1,
      (y + 1) * sourceStride,
    );

    for (let repeatY = 0; repeatY < factor; repeatY += 1) {
      const targetOffset = (y * factor + repeatY) * outputStride;
      scaled[targetOffset] = 0;

      for (let x = 0; x < width; x += 1) {
        if (sourceRow[x * 4 + 3] !== 255) {
          throw new Error("Mobile app icon must be fully opaque.");
        }
        const pixel = sourceRow.subarray(x * 4, x * 4 + 3);
        const targetPixelOffset = targetOffset + 1 + x * factor * 3;
        pixel.copy(scaled, targetPixelOffset);
        pixel.copy(scaled, targetPixelOffset + 3);
      }
    }
  }

  const nextChunks = [];
  for (const chunk of chunks) {
    if (chunk.type !== "IHDR") {
      nextChunks.push(chunk);
      continue;
    }

    const nextIhdr = Buffer.from(chunk.data);
    nextIhdr.writeUInt32BE(outputWidth, 0);
    nextIhdr.writeUInt32BE(outputHeight, 4);
    nextIhdr[9] = 2;
    nextChunks.push({ type: chunk.type, data: nextIhdr });
  }
  nextChunks.push({ type: "IDAT", data: deflateSync(scaled) });

  return writePngChunks(signature, nextChunks);
}

function writePngChunks(signature, chunks) {
  const parts = [signature];
  for (const chunk of chunks) {
    const type = Buffer.from(chunk.type, "ascii");
    const length = Buffer.alloc(4);
    length.writeUInt32BE(chunk.data.length, 0);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([type, chunk.data])), 0);
    parts.push(length, type, chunk.data, crc);
  }

  const iendType = Buffer.from("IEND", "ascii");
  const iendLength = Buffer.alloc(4);
  const iendCrc = Buffer.alloc(4);
  iendCrc.writeUInt32BE(crc32(iendType), 0);
  parts.push(iendLength, iendType, Buffer.alloc(0), iendCrc);

  return Buffer.concat(parts);
}

function createCrcTable() {
  return new Uint32Array(256).map((_, index) => {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    return value >>> 0;
  });
}

function unfilterPngScanlines(raw, width, height) {
  const bytesPerPixel = 4;
  const rowLength = width * bytesPerPixel;
  const stride = 1 + rowLength;
  const output = Buffer.alloc(raw.length);

  for (let y = 0; y < height; y += 1) {
    const rowStart = y * stride;
    const previousRowStart = y === 0 ? -1 : (y - 1) * stride;
    const filter = raw[rowStart];
    output[rowStart] = 0;

    for (let x = 0; x < rowLength; x += 1) {
      const rawValue = raw[rowStart + 1 + x];
      const left =
        x >= bytesPerPixel ? output[rowStart + 1 + x - bytesPerPixel] : 0;
      const up = previousRowStart >= 0 ? output[previousRowStart + 1 + x] : 0;
      const upLeft =
        previousRowStart >= 0 && x >= bytesPerPixel
          ? output[previousRowStart + 1 + x - bytesPerPixel]
          : 0;

      output[rowStart + 1 + x] =
        (rawValue + pngFilterValue(filter, left, up, upLeft)) & 0xff;
    }
  }

  return output;
}

function pngFilterValue(filter, left, up, upLeft) {
  switch (filter) {
    case 0:
      return 0;
    case 1:
      return left;
    case 2:
      return up;
    case 3:
      return Math.floor((left + up) / 2);
    case 4:
      return paethPredictor(left, up, upLeft);
    default:
      throw new Error(`Unsupported PNG scanline filter: ${filter}`);
  }
}

function paethPredictor(left, up, upLeft) {
  const estimate = left + up - upLeft;
  const leftDistance = Math.abs(estimate - left);
  const upDistance = Math.abs(estimate - up);
  const upLeftDistance = Math.abs(estimate - upLeft);

  if (leftDistance <= upDistance && leftDistance <= upLeftDistance) {
    return left;
  }
  if (upDistance <= upLeftDistance) {
    return up;
  }
  return upLeft;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
