import { createSHA256 } from "hash-wasm";

/** Bound memory independently of video size; runs in the upload worker. */
export async function hashFileContents(file: Blob): Promise<string> {
  const hash = await createSHA256();
  for (let offset = 0; offset < file.size; offset += 2 * 1024 * 1024) {
    hash.update(
      new Uint8Array(
        await file.slice(offset, offset + 2 * 1024 * 1024).arrayBuffer(),
      ),
    );
  }
  return hash.digest("hex");
}
