import { getRefreshToken } from "./token";
import {
  getValidAccessToken,
  redirectToLogin,
  refreshAccessToken,
} from "./tokenManager";

interface AuthenticatedRequestOptions extends RequestInit {
  retryOn401?: boolean;
}

export async function createAuthHeaders(
  headers: HeadersInit = {},
): Promise<Headers> {
  const finalHeaders = new Headers(headers);
  const token = await getValidAccessToken();
  if (token) {
    finalHeaders.set("Authorization", `Bearer ${token}`);
  }
  return finalHeaders;
}

/**
 * Authenticated request with automatic 401 retry.
 * Behavior is consistent with authFetch: throws on auth failure.
 */
export async function authenticatedRequest(
  input: RequestInfo | URL,
  init: AuthenticatedRequestOptions = {},
): Promise<Response> {
  const { retryOn401 = true, headers = {}, ...rest } = init;
  const finalHeaders = await createAuthHeaders(headers);
  const response = await fetch(input, {
    ...rest,
    headers: finalHeaders,
  });

  if (response.status !== 401 || !retryOn401) {
    return response;
  }

  if (!getRefreshToken()) {
    redirectToLogin();
    throw new Error("Unauthorized: no refresh token");
  }

  try {
    await refreshAccessToken();
  } catch (error) {
    redirectToLogin();
    throw error;
  }

  const retryHeaders = await createAuthHeaders(headers);
  const retryResponse = await fetch(input, {
    ...rest,
    headers: retryHeaders,
  });

  if (retryResponse.status === 401) {
    redirectToLogin();
    throw new Error("Unauthorized after token refresh");
  }

  return retryResponse;
}
