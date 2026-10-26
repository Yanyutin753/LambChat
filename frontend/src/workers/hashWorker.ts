import { hashFileContents } from "../utils/hashFileContents";

self.onmessage = async (e: MessageEvent<{ file: File }>) => {
  try {
    self.postMessage({ hash: await hashFileContents(e.data.file) });
  } catch (error) {
    self.postMessage({
      error: error instanceof Error ? error.message : "Hash computation failed",
    });
  }
};
