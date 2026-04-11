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

export async function getValidAccessToken(): Promise<string | null> {
  const accessToken = getAccessToken();
  if (!accessToken) {
    return null;
  }

  if (!isTokenExpired(accessToken)) {
    return accessToken;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken || isTokenExpired(refreshToken)) {
    redirectToLogin();
    return null;
  }

  try {
    return await refreshAccessToken();
  } catch {
    redirectToLogin();
    return null;
  }
}

export async function refreshTokens(): Promise<RefreshedTokens> {
  if (refreshPromise) {
    const access_token = await refreshPromise;
    return { access_token };
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
    refreshPromise = null;
  }
}

export async function refreshAccessToken(): Promise<string> {
  const { access_token } = await refreshTokens();
  return access_token;
}
