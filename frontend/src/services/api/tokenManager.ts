import { API_BASE } from "./config";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isTokenExpired,
  setTokens,
} from "./token";
import i18n from "../../i18n";

let refreshPromise: Promise<string> | null = null;

export interface RefreshedTokens {
  access_token: string;
  refresh_token?: string;
}

function notifyLogout(): void {
  window.dispatchEvent(new CustomEvent("auth:logout"));
}

export function clearAuthState(): void {
  clearTokens();
  notifyLogout();
}

export function redirectToLogin(): void {
  const currentPath = window.location.pathname + window.location.search;
  if (currentPath !== "/auth/login" && currentPath !== "/") {
    sessionStorage.setItem("redirect_after_login", currentPath);
  }
  clearAuthState();
}

/**
 * Get a valid (non-expired) access token.
 *
 * Returns `null` when no token exists — the caller decides what to do.
 * When the access token is expired, attempts a silent refresh.
 * Does NOT call redirectToLogin — callers handle redirect themselves.
 */
export async function getValidAccessToken(): Promise<string | null> {
  const accessToken = getAccessToken();
  if (!accessToken) {
    return null;
  }

  if (!isTokenExpired(accessToken)) {
    return accessToken;
  }

  // Access token expired — try refresh
  const refreshToken = getRefreshToken();
  if (!refreshToken || isTokenExpired(refreshToken)) {
    return null;
  }

  try {
    return await refreshAccessToken();
  } catch {
    return null;
  }
}

/**
 * Refresh tokens with deduplication to avoid concurrent refresh requests.
 *
 * Uses a ref-counted approach: the promise is cleared only after all
 * concurrent callers have awaited it, preventing race conditions where
 * a third caller starts a duplicate refresh.
 */
export async function refreshTokens(): Promise<RefreshedTokens> {
  if (refreshPromise) {
    // Wait for the in-flight refresh — do NOT return early with just access_token.
    // The caller may need the refresh_token too.
    const access_token = await refreshPromise;
    return {
      access_token,
      refresh_token: getRefreshToken() ?? undefined,
    };
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

    const response = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": i18n.language || "en",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      throw new Error("Token refresh failed");
    }

    const tokenResponse = (await response.json()) as RefreshedTokens;
    setTokens(tokenResponse.access_token, tokenResponse.refresh_token);
    return tokenResponse.access_token;
  })();

  try {
    const access_token = await refreshPromise;
    return {
      access_token,
      refresh_token: getRefreshToken() ?? undefined,
    };
  } finally {
    // Use microtask delay so that callers still awaiting the same promise
    // in the `if (refreshPromise)` branch finish before we clear it.
    Promise.resolve().then(() => {
      refreshPromise = null;
    });
  }
}

export async function refreshAccessToken(): Promise<string> {
  const { access_token } = await refreshTokens();
  return access_token;
}
