const textCache = new Map<string, Promise<string>>();
const arrayBufferCache = new Map<string, Promise<ArrayBuffer>>();

async function fetchWithValidation(url: string): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch file: ${response.status}`);
  }
  return response;
}

export function fetchDocumentText(url: string): Promise<string> {
  const cached = textCache.get(url);
  if (cached) {
    return cached;
  }

  const request = fetchWithValidation(url)
    .then((response) => response.text())
    .catch((error) => {
      textCache.delete(url);
      throw error;
    });

  textCache.set(url, request);
  return request;
}

export function fetchDocumentArrayBuffer(url: string): Promise<ArrayBuffer> {
  const cached = arrayBufferCache.get(url);
  if (cached) {
    return cached;
  }

  const request = fetchWithValidation(url)
    .then((response) => response.arrayBuffer())
    .catch((error) => {
      arrayBufferCache.delete(url);
      throw error;
    });

  arrayBufferCache.set(url, request);
  return request;
}

export function clearDocumentFetchCaches(): void {
  textCache.clear();
  arrayBufferCache.clear();
}
